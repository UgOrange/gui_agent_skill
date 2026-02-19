"""GUI Agent core executor."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import SkillConfig, load_skill_config, get_forge_config
from .session_manager import SessionManager
from .model_providers import validate_provider, seed_provider_env_from_config


class ExecutorError(RuntimeError):
    """Executor-level runtime error."""
    pass


class OperationTimeoutError(TimeoutError):
    """Timeout with best-effort subprocess cleanup metadata."""

    def __init__(self, message: str, terminated_subprocesses: int = 0):
        super().__init__(message)
        self.terminated_subprocesses = terminated_subprocesses


_SUBPROCESS_PATCHED = False
_TRACKED_SUBPROCESSES: set[subprocess.Popen] = set()
_TRACKED_SUBPROCESSES_LOCK = threading.Lock()


def _register_subprocess(proc: subprocess.Popen) -> None:
    with _TRACKED_SUBPROCESSES_LOCK:
        _TRACKED_SUBPROCESSES.add(proc)


def _collect_live_subprocesses() -> list[subprocess.Popen]:
    with _TRACKED_SUBPROCESSES_LOCK:
        live: list[subprocess.Popen] = []
        stale: list[subprocess.Popen] = []
        for proc in _TRACKED_SUBPROCESSES:
            if proc.poll() is None:
                live.append(proc)
            else:
                stale.append(proc)
        for proc in stale:
            _TRACKED_SUBPROCESSES.discard(proc)
        return live


def _terminate_process(proc: subprocess.Popen, force: bool) -> None:
    try:
        if os.name == "nt":
            cmd = f"taskkill /PID {proc.pid} /T"
            if force:
                cmd += " /F"
            cmd += " >NUL 2>NUL"
            os.system(cmd)
            return

        if force:
            try:
                pgid = os.getpgid(proc.pid)
                if pgid != os.getpgrp():
                    os.killpg(pgid, signal.SIGKILL)
                    return
            except Exception:
                pass
            proc.kill()
            return

        try:
            pgid = os.getpgid(proc.pid)
            if pgid != os.getpgrp():
                os.killpg(pgid, signal.SIGTERM)
                return
        except Exception:
            pass
        proc.terminate()
    except Exception:
        return


def cleanup_tracked_subprocesses(grace_sec: float = 1.5) -> int:
    """
    Best-effort cleanup for subprocesses spawned by adapters.
    Returns the number of live subprocesses observed before cleanup.
    """
    live = _collect_live_subprocesses()
    if not live:
        return 0

    for proc in live:
        _terminate_process(proc, force=False)

    deadline = time.time() + max(0.0, grace_sec)
    for proc in live:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            proc.wait(timeout=remaining)
        except Exception:
            continue

    for proc in live:
        if proc.poll() is None:
            _terminate_process(proc, force=True)

    _collect_live_subprocesses()
    return len(live)


def _patch_subprocess_text_decode() -> None:
    """
    On Windows, avoid subprocess text-mode decode crashes in reader threads.

    gui_agent_forge can spawn subprocesses whose output may include bytes
    that cannot be decoded by the current locale; this patches defaults.
    """
    global _SUBPROCESS_PATCHED
    if _SUBPROCESS_PATCHED:
        return

    original_popen_cls = subprocess.Popen

    # Keep subprocess.Popen as a class so stdlib (e.g. asyncio on Windows)
    # can still subclass it safely.
    class PatchedPopen(original_popen_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            text_mode = kwargs.get("text") or kwargs.get("universal_newlines")
            if os.name == "nt" and text_mode and "errors" not in kwargs:
                kwargs["errors"] = "ignore"
            super().__init__(*args, **kwargs)
            _register_subprocess(self)

    subprocess.Popen = PatchedPopen  # type: ignore[assignment]
    _SUBPROCESS_PATCHED = True


class GUIAgentExecutor:
    """GUI Agent task executor wrapping gui_agent_forge core capabilities."""

    _COMPLETE_AND_STOP_GUARD = (
        "Strict rule: after completing the goal, output COMPLETE immediately and stop.\n"
        "After completing the goal, output COMPLETE immediately and stop; do not continue exploring."
    )
    _NO_DEVICE_HINT = (
        "No ADB devices found. Connect a phone/emulator, enable USB debugging, "
        "and approve the device authorization prompt. You can run `adb devices` to verify."
    )
    _TAP_ONLY_HINT = (
        "Tap-only mode is enabled. `execute`/`continue` are disabled because no model provider is configured. "
        "Use `tap`/`click` for coordinate control, or run `python install.py --provider <name>` to enable planner mode."
    )

    def __init__(self, config_path: str | Path | None = None):
        _patch_subprocess_text_decode()
        self.skill_config = load_skill_config(config_path)
        seed_provider_env_from_config(self.skill_config)
        self.session_manager = SessionManager(
            storage_dir=self.skill_config.session.storage_dir,
            expire_seconds=self.skill_config.session.expire_seconds,
        )
        self._ensure_forge_path()
        self._registry = None
        self._collector = None
        self._captioner = None

    def _ensure_forge_path(self) -> None:
        """Ensure gui_agent_forge is available in sys.path."""
        forge_path = self.skill_config.gui_agent_forge_path
        if forge_path is None:
            raise ExecutorError(
                "Cannot find gui_agent_forge. Please set GUI_AGENT_FORGE_PATH "
                "environment variable or configure gui_agent_forge_path in config."
            )
        forge_path_str = str(forge_path)
        if forge_path_str not in sys.path:
            sys.path.insert(0, forge_path_str)
        # Also add parent directory so import gui_agent_forge works reliably.
        parent_str = str(forge_path.parent)
        if parent_str not in sys.path:
            sys.path.insert(0, parent_str)

    def _get_registry(self, provider: str):
        """Get adapter registry."""
        from gui_agent_forge.adapters import AdapterRegistry
        forge_config = get_forge_config(self.skill_config, provider)
        return AdapterRegistry(forge_config)

    def _get_collector(self):
        """Get state collector."""
        if self._collector is None:
            from gui_agent_forge.state.collector import StateCollector
            self._collector = StateCollector(
                self.skill_config.device,
                self.skill_config.state,
            )
        return self._collector

    def _get_captioner(self):
        """Get state captioner."""
        if self._captioner is None:
            from gui_agent_forge.state.captioner import StateCaptioner
            forge_path = self.skill_config.gui_agent_forge_path
            # Use default provider model settings for captioning when available.
            provider_config = self.skill_config.providers.get(
                self.skill_config.default_provider, {}
            )
            model_config = None
            if provider_config.get("adapter") == "gelab_local":
                model_config = {
                    "model_name": provider_config.get("model_name", "gelab-zero-4b-preview"),
                    "model_provider": provider_config.get("model_provider", "local"),
                }
            self._captioner = StateCaptioner(
                self.skill_config.state,
                model_config,
                forge_path,
                )
        return self._captioner

    def _resolve_adb_command(self) -> str:
        device_cfg = self.skill_config.device or {}
        adb_cmd = str(device_cfg.get("adb_path") or "adb").strip()
        return adb_cmd or "adb"

    def _ensure_adb_available(self) -> None:
        adb_cmd = self._resolve_adb_command()
        adb_path = Path(adb_cmd)
        if adb_path.is_absolute() or adb_path.parent != Path("."):
            exists = adb_path.exists()
        else:
            exists = shutil.which(adb_cmd) is not None
        if exists:
            return
        raise ExecutorError(
            f"ADB not found: `{adb_cmd}`. Install Android platform-tools and make sure adb is in PATH, "
            "or set `device.adb_path` to a valid adb executable."
        )

    def list_devices(self) -> list[str]:
        """List all connected ADB devices."""
        self._ensure_adb_available()
        collector = self._get_collector()
        try:
            return collector.list_devices()
        except Exception as e:
            msg = str(e).lower()
            if "adb" in msg and ("not found" in msg or "no such file" in msg):
                raise ExecutorError(
                    "ADB command failed. Ensure adb is installed and executable."
                ) from e
            raise

    def _ensure_device_connected(self, device_id: str) -> None:
        devices = self.list_devices()
        if not devices:
            raise ExecutorError(self._NO_DEVICE_HINT)
        if device_id not in devices:
            raise ExecutorError(
                f"Device `{device_id}` is not connected or not authorized. Available devices: {', '.join(devices)}. "
                "Ensure USB debugging is enabled and debugging authorization is approved on the device."
            )

    def _select_device(self, device_id: str | None) -> str:
        """Select one device for operation."""
        if device_id:
            self._ensure_device_connected(device_id)
            return device_id
        if self.skill_config.default_device_id:
            default_device = self.skill_config.default_device_id
            self._ensure_device_connected(default_device)
            return default_device
        devices = self.list_devices()
        if not devices:
            raise ExecutorError(self._NO_DEVICE_HINT)
        if len(devices) > 1:
            raise ExecutorError(
                f"Multiple devices found: {', '.join(devices)}. Use --device-id to choose one."
            )
        return devices[0]

    def _is_tap_only_mode(self) -> bool:
        return bool(getattr(self.skill_config, "tap_only_mode", False))

    def _tap_only_error_result(self, command: str) -> dict[str, Any]:
        return {
            "success": False,
            "error": "tap_only_mode_enabled",
            "message": f"`{command}` is unavailable in tap-only mode. {self._TAP_ONLY_HINT}",
            "session_mode": "direct_coordinate_only",
            "session_persisted": False,
            "continuation_supported": False,
            "allowed_commands": ["tap", "click", "status", "devices"],
        }

    def _write_screenshot(self, output_dir: Path, screenshot_info: dict) -> dict | None:
        """Save screenshot to local file and return metadata."""
        b64_data = screenshot_info.get("b64")
        if not b64_data:
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "screenshot.png"
        image_bytes = base64.b64decode(b64_data)
        path.write_bytes(image_bytes)
        return {
            "sha1": screenshot_info.get("sha1"),
            "content_type": screenshot_info.get("content_type"),
            "file": str(path),
        }

    def _fallback_caption(self, post_state: dict) -> str:
        """Generate fallback caption when model caption is unavailable."""
        current_app = post_state.get("current_app") or "unknown"
        parts = [f"current_app={current_app}"]
        notifications = post_state.get("notifications", {}).get("parsed") or []
        if notifications:
            first = notifications[0]
            title = first.get("title") or ""
            text = first.get("text") or first.get("ticker") or ""
            summary = "notification=" + " - ".join([item for item in [title, text] if item])
            if summary != "notification=":
                parts.append(summary)
        return "; ".join(parts)

    def _determine_next_action(self, result: dict) -> str:
        """Infer next action from adapter result payload."""
        if isinstance(result, dict):
            action_type = result.get("action_type") or result.get("type")
            if action_type == "INFO_ACTION_NEEDS_REPLY":
                return "needs_reply"
            # Check completion status.
            status = result.get("status") or result.get("state")
            if status in ("completed", "done", "success"):
                return "complete"
        return "continue"

    def _ensure_complete_and_stop_guard(self, task: str) -> str:
        """Ensure task text contains strict COMPLETE-and-stop instruction."""
        normalized = (task or "").strip()
        if not normalized:
            return self._COMPLETE_AND_STOP_GUARD
        if "output COMPLETE immediately and stop" in normalized:
            return normalized
        return f"{normalized}\n\n{self._COMPLETE_AND_STOP_GUARD}"

    def _build_stateless_task(self, task: str) -> str:
        """Build a fresh-task prompt that keeps current app state."""
        prefix = (
            "Execution mode: stateless minimal task.\n"
            "Requirement: continue from the current screen; do not press Home; do not reset app/environment.\n"
            "Only perform the minimum actions needed for this request."
        )
        guarded_task = self._ensure_complete_and_stop_guard(task)
        return f"{prefix}\nUser task: {guarded_task}"

    def _build_stateless_extra_info(self, extra_info: dict | None) -> dict[str, Any]:
        merged = dict(extra_info or {})
        # Best-effort hints for adapters/servers that support runtime options.
        merged.setdefault("execution_mode", "stateless")
        merged.setdefault("new_conversation", True)
        merged.setdefault("preserve_current_app_state", True)
        merged.setdefault("minimal_actions", True)
        merged.setdefault("reset_environment", False)
        merged.setdefault("reflush_app", False)
        return merged

    def _extract_png_size(self, screenshot_b64: str | None) -> tuple[int, int] | None:
        if not screenshot_b64:
            return None
        try:
            image_bytes = base64.b64decode(screenshot_b64)
        except Exception:
            return None
        if len(image_bytes) < 24:
            return None
        if image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        if image_bytes[12:16] != b"IHDR":
            return None
        width = int.from_bytes(image_bytes[16:20], "big")
        height = int.from_bytes(image_bytes[20:24], "big")
        if width <= 0 or height <= 0:
            return None
        return width, height

    def _get_screen_size_from_wm(self, device_id: str) -> tuple[int, int] | None:
        collector = self._get_collector()
        try:
            result = collector.adb.run(["shell", "wm", "size"], device_id=device_id)
        except Exception:
            return None
        output = result.stdout or ""
        override_match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
        if override_match:
            return int(override_match.group(1)), int(override_match.group(2))
        physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
        if physical_match:
            return int(physical_match.group(1)), int(physical_match.group(2))
        return None

    def _resolve_tap_coordinate(
        self,
        x: float,
        y: float,
        coord_space: str,
        screen_width: int,
        screen_height: int,
    ) -> dict[str, Any]:
        if screen_width <= 0 or screen_height <= 0:
            raise ExecutorError("Invalid screen size. Width/height must be > 0.")
        effective_space = coord_space
        if coord_space == "auto":
            # Treat 0..1 as ratio only when both axes are in ratio range.
            effective_space = "ratio" if (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) else "pixel"

        if effective_space == "ratio":
            raw_x = x * (screen_width - 1)
            raw_y = y * (screen_height - 1)
        elif effective_space == "pixel":
            raw_x = x
            raw_y = y
        else:
            raise ExecutorError(f"Unsupported coord_space: {coord_space}")

        rounded_x = int(round(raw_x))
        rounded_y = int(round(raw_y))
        tap_x = max(0, min(screen_width - 1, rounded_x))
        tap_y = max(0, min(screen_height - 1, rounded_y))

        return {
            "input": {"x": x, "y": y, "coord_space": coord_space},
            "effective_coord_space": effective_space,
            "screen_size": {"width": screen_width, "height": screen_height},
            "computed": {"x": rounded_x, "y": rounded_y},
            "tap": {"x": tap_x, "y": tap_y},
            "clamped": (tap_x != rounded_x) or (tap_y != rounded_y),
        }

    def _start_adapter_task(
        self,
        adapter: Any,
        device_id: str,
        task: str,
        max_steps: int,
        extra_info: dict | None = None,
        reset_environment: bool | None = None,
    ) -> dict[str, Any]:
        if reset_environment is None:
            return adapter.start_task(
                device_id=device_id,
                task=task,
                max_steps=max_steps,
                extra_info=extra_info,
            )

        run_loop = getattr(adapter, "_run_loop", None)
        if callable(run_loop):
            try:
                return run_loop(
                    device_id=device_id,
                    task=task,
                    session_id=None,
                    reply_from_client=None,
                    max_steps=max_steps,
                    extra_info=extra_info,
                    reset_environment=reset_environment,
                )
            except TypeError:
                # Adapter internals changed; fallback to public API below.
                pass

        merged_extra_info = dict(extra_info or {})
        merged_extra_info.setdefault("reset_environment", reset_environment)
        merged_extra_info.setdefault("reflush_app", reset_environment)
        return adapter.start_task(
            device_id=device_id,
            task=task,
            max_steps=max_steps,
            extra_info=merged_extra_info,
        )

    def execute_coordinate_tap(
        self,
        x: float,
        y: float,
        coord_space: str = "auto",
        device_id: str | None = None,
        timeout_sec: int | None = None,
        post_delay_ms: int = 350,
    ) -> dict[str, Any]:
        timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else self.skill_config.default_operation_timeout_sec
        )
        if post_delay_ms < 0:
            return {
                "success": False,
                "error": "Invalid post_delay_ms: must be >= 0",
                "message": "Invalid post_delay_ms: must be >= 0",
            }

        try:
            device_id = self._select_device(device_id)
        except ExecutorError as e:
            return {
                "success": False,
                "error": str(e),
                "message": str(e),
            }

        def _tap_once() -> dict[str, Any]:
            collector = self._get_collector()
            pre_state = collector.get_state(device_id, detail_level="snapshot")
            screenshot_info = pre_state.get("screenshot") or {}
            size = self._extract_png_size(screenshot_info.get("b64"))
            if size is None:
                size = self._get_screen_size_from_wm(device_id)
            if size is None:
                raise ExecutorError(
                    "Cannot determine screen size. Ensure screenshot/state collection is enabled."
                )
            coord_detail = self._resolve_tap_coordinate(
                x=x,
                y=y,
                coord_space=coord_space,
                screen_width=size[0],
                screen_height=size[1],
            )
            tap_point = coord_detail["tap"]
            collector.adb.run(
                ["shell", "input", "tap", str(tap_point["x"]), str(tap_point["y"])],
                device_id=device_id,
            )
            if post_delay_ms > 0:
                time.sleep(post_delay_ms / 1000.0)
            post_state = collector.get_state(device_id, detail_level="snapshot")
            return {
                "coord_detail": coord_detail,
                "post_state": post_state,
            }

        try:
            tap_result = self._run_with_timeout(
                _tap_once,
                timeout_sec=timeout_sec,
                operation_name="tap",
            )
        except Exception as e:
            error_result = {
                "success": False,
                "provider": "direct_adb",
                "device_id": device_id,
                "error": str(e),
                "message": f"Coordinate tap failed: {e}",
                "timed_out": isinstance(e, TimeoutError),
                "session_mode": "direct_coordinate",
                "session_persisted": False,
                "continuation_supported": False,
            }
            if isinstance(e, OperationTimeoutError):
                error_result["terminated_subprocesses"] = e.terminated_subprocesses
            if timeout_sec is not None:
                error_result["timeout_sec"] = timeout_sec
            return error_result

        session_id = str(uuid.uuid4())[:8]
        post_state = tap_result["post_state"]
        coord_detail = tap_result["coord_detail"]
        screenshot_info = post_state.get("screenshot") or {}
        screenshot_path = None
        if self.skill_config.output.save_screenshot and screenshot_info.get("b64"):
            output_dir = self.skill_config.output.dir / session_id
            file_info = self._write_screenshot(output_dir, screenshot_info)
            if file_info:
                screenshot_path = file_info.get("file")
                post_state["screenshot"] = file_info

        caption = self._fallback_caption(post_state)

        return {
            "success": True,
            "session_id": session_id,
            "task": "direct_coordinate_tap",
            "provider": "direct_adb",
            "device_id": device_id,
            "step_count": 1,
            "caption": caption,
            "screenshot_path": screenshot_path,
            "next_action": "continue",
            "current_app": post_state.get("current_app"),
            "message": "Tap executed. Review screenshot and run another tap if needed.",
            "session_mode": "direct_coordinate",
            "session_persisted": False,
            "continuation_supported": False,
            "timed_out": False,
            "coordinate": coord_detail,
            "raw_result": {
                "action": "tap",
                "tap": coord_detail.get("tap"),
                "effective_coord_space": coord_detail.get("effective_coord_space"),
                "clamped": coord_detail.get("clamped"),
            },
        }

    def _run_with_timeout(
        self,
        func: Callable[[], dict[str, Any]],
        timeout_sec: int | None,
        operation_name: str,
    ) -> dict[str, Any]:
        if timeout_sec is None:
            return func()
        if timeout_sec <= 0:
            raise ExecutorError("timeout_sec must be greater than 0.")

        result_holder: dict[str, dict[str, Any]] = {}
        error_holder: dict[str, BaseException] = {}

        def _target() -> None:
            try:
                result_holder["value"] = func()
            except BaseException as exc:
                error_holder["error"] = exc

        worker = threading.Thread(
            target=_target,
            name=f"gui-agent-{operation_name}-runner",
            daemon=True,
        )
        worker.start()
        worker.join(timeout_sec)

        if worker.is_alive():
            cleaned = cleanup_tracked_subprocesses()
            raise OperationTimeoutError(
                f"{operation_name} timed out after {timeout_sec} seconds.",
                terminated_subprocesses=cleaned,
            )
        if "error" in error_holder:
            raise error_holder["error"]
        if "value" not in result_holder:
            raise ExecutorError(f"{operation_name} failed without returning a result.")
        return result_holder["value"]

    def execute_task(
        self,
        task: str,
        provider: str | None = None,
        device_id: str | None = None,
        max_steps: int | None = None,
        timeout_sec: int | None = None,
        extra_info: dict | None = None,
        stateless: bool = False,
    ) -> dict[str, Any]:
        """Execute a GUI task."""
        if self._is_tap_only_mode():
            return self._tap_only_error_result("execute")

        provider = provider or self.skill_config.default_provider
        provider = str(provider or "").strip()
        timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else self.skill_config.default_operation_timeout_sec
        )
        if not provider:
            return {
                "success": False,
                "error": "No provider configured",
                "message": (
                    "No provider configured for execute. Set --provider or configure default_provider. "
                    "If you only need coordinate control, use `tap`/`click`."
                ),
            }
        if stateless:
            max_steps = max_steps or min(self.skill_config.default_max_steps, 4)
        else:
            max_steps = max_steps or self.skill_config.default_max_steps
        if max_steps <= 0:
            return {
                "success": False,
                "error": "Invalid max_steps: must be > 0",
                "message": "Invalid max_steps: must be > 0",
            }

        valid, msg = validate_provider(provider, self.skill_config)
        if not valid:
            return {
                "success": False,
                "error": msg,
                "message": f"Provider validation failed: {msg}",
            }

        try:
            device_id = self._select_device(device_id)
        except ExecutorError as e:
            return {
                "success": False,
                "error": str(e),
                "message": str(e),
            }

        task_to_run = self._ensure_complete_and_stop_guard(task)
        adapter_extra_info = extra_info
        session_id = None

        if stateless:
            session_id = str(uuid.uuid4())[:8]
            task_to_run = self._build_stateless_task(task)
            adapter_extra_info = self._build_stateless_extra_info(extra_info)
        else:
            session = self.session_manager.create_session(
                device_id=device_id,
                provider=provider,
                task=task,
            )
            session_id = session.session_id

        try:
            registry = self._get_registry(provider)
            adapter = registry.get(provider)
            result = self._run_with_timeout(
                lambda: self._start_adapter_task(
                    adapter=adapter,
                    device_id=device_id,
                    task=task_to_run,
                    max_steps=max_steps,
                    extra_info=adapter_extra_info,
                    reset_environment=False if stateless else None,
                ),
                timeout_sec=timeout_sec,
                operation_name="execute",
            )
        except Exception as e:
            error_result = {
                "success": False,
                "session_id": session_id,
                "error": str(e),
                "message": f"Task execution failed: {e}",
                "timed_out": isinstance(e, TimeoutError),
            }
            if isinstance(e, OperationTimeoutError):
                error_result["terminated_subprocesses"] = e.terminated_subprocesses
            if timeout_sec is not None:
                error_result["timeout_sec"] = timeout_sec
            if stateless:
                error_result.update({
                    "session_mode": "stateless",
                    "session_persisted": False,
                    "continuation_supported": False,
                })
            return error_result

        output = self._process_result(
            session_id=session_id,
            provider=provider,
            device_id=device_id,
            result=result,
            task=task,
            persist_session=not stateless,
        )
        return output

    def continue_session(
        self,
        session_id: str | None = None,
        reply: str | None = None,
        task: str | None = None,
        device_id: str | None = None,
        max_steps: int | None = None,
        timeout_sec: int | None = None,
    ) -> dict[str, Any]:
        """Continue an existing stateful session."""
        if self._is_tap_only_mode():
            return self._tap_only_error_result("continue")

        # If session_id is omitted, continue the latest active session.
        if session_id is None:
            session = self.session_manager.get_latest_session(device_id)
            if session is None:
                return {
                    "success": False,
                    "error": "No active session found",
                    "message": "No active session to continue. Start a new task first.",
                }
        else:
            session = self.session_manager.get_session(session_id)
            if session is None:
                return {
                    "success": False,
                    "error": f"Session not found: {session_id}",
                    "message": f"Session {session_id} not found or expired.",
                }

        if session.status != "active":
            return {
                "success": False,
                "error": f"Session is {session.status}",
                "message": f"Cannot continue session: status is {session.status}.",
            }

        max_steps = max_steps or self.skill_config.default_max_steps
        if max_steps <= 0:
            return {
                "success": False,
                "session_id": session.session_id,
                "error": "Invalid max_steps: must be > 0",
                "message": "Invalid max_steps: must be > 0",
            }
        timeout_sec = (
            timeout_sec
            if timeout_sec is not None
            else self.skill_config.default_operation_timeout_sec
        )
        device_id = session.device_id
        provider = session.provider

        # Resolve adapter and continue the task.
        try:
            self._ensure_device_connected(device_id)
            registry = self._get_registry(provider)
            adapter = registry.get(provider)
            continue_task = self._ensure_complete_and_stop_guard(task or session.task)

            # Prefer adapter-owned session id when returned from previous step.
            adapter_session_id = session.last_result.get("session_id")

            result = self._run_with_timeout(
                lambda: adapter.continue_task(
                    device_id=device_id,
                    session_id=adapter_session_id or session.session_id,
                    reply=reply,
                    task=continue_task,
                    max_steps=max_steps,
                ),
                timeout_sec=timeout_sec,
                operation_name="continue",
            )
        except Exception as e:
            error_result = {
                "success": False,
                "session_id": session.session_id,
                "error": str(e),
                "message": f"Continue task failed: {e}",
                "timed_out": isinstance(e, TimeoutError),
            }
            if isinstance(e, OperationTimeoutError):
                error_result["terminated_subprocesses"] = e.terminated_subprocesses
            if timeout_sec is not None:
                error_result["timeout_sec"] = timeout_sec
            return error_result

        # Normalize adapter result.
        output = self._process_result(
            session_id=session.session_id,
            provider=session.provider,
            device_id=session.device_id,
            result=result,
            task=task or session.task,
            persist_session=True,
        )
        return output

    def _process_result(
        self,
        session_id: str,
        provider: str,
        device_id: str,
        result: dict,
        task: str,
        persist_session: bool = True,
    ) -> dict[str, Any]:
        """Process adapter output and normalize the response."""
        collector = self._get_collector()
        captioner = self._get_captioner()

        try:
            post_state = collector.get_state(device_id, detail_level="snapshot")
        except Exception:
            post_state = {}

        screenshot_info = post_state.get("screenshot") or {}
        screenshot_path = None
        if self.skill_config.output.save_screenshot and screenshot_info.get("b64"):
            output_dir = self.skill_config.output.dir / session_id
            file_info = self._write_screenshot(output_dir, screenshot_info)
            if file_info:
                screenshot_path = file_info.get("file")
                post_state["screenshot"] = file_info

        caption = None
        if self.skill_config.output.enable_caption and screenshot_info.get("b64"):
            try:
                caption = captioner.caption(task, screenshot_info.get("b64"))
            except Exception:
                pass
        if not caption:
            caption = self._fallback_caption(post_state)

        next_action = self._determine_next_action(result)

        if persist_session:
            status = "completed" if next_action == "complete" else "active"
            updated_session = self.session_manager.update_session(
                session_id,
                result=result,
                status=status,
            )
            step_count = updated_session.step_count if updated_session else 1
        else:
            step_count = 1

        return {
            "success": True,
            "session_id": session_id,
            "task": task,
            "provider": provider,
            "device_id": device_id,
            "step_count": step_count,
            "caption": caption,
            "screenshot_path": screenshot_path,
            "next_action": next_action,
            "current_app": post_state.get("current_app"),
            "message": self._generate_message(
                next_action,
                caption,
                continuation_supported=persist_session,
            ),
            "session_mode": "stateful" if persist_session else "stateless",
            "session_persisted": persist_session,
            "continuation_supported": persist_session,
            "timed_out": False,
            "raw_result": result,
        }

    def _generate_message(
        self,
        next_action: str,
        caption: str,
        continuation_supported: bool = True,
    ) -> str:
        """Generate a human-friendly summary message."""
        if next_action == "complete":
            message = f"Task completed. {caption}"
        elif next_action == "needs_reply":
            message = f"User reply required. Current state: {caption}"
        else:
            message = f"Task in progress. Current state: {caption}"

        if not continuation_supported and next_action != "complete":
            message += " Stateless mode is active; run execute --stateless for the next independent call."
        return message

    def get_device_status(self, device_id: str | None = None) -> dict[str, Any]:
        """Get basic device status snapshot."""
        try:
            device_id = self._select_device(device_id)
        except ExecutorError as e:
            devices: list[str] = []
            try:
                devices = self.list_devices()
            except Exception:
                devices = []
            return {
                "success": False,
                "error": str(e),
                "devices": devices,
            }

        collector = self._get_collector()
        try:
            state = collector.get_state(device_id, detail_level="lite")
            return {
                "success": True,
                "device_id": device_id,
                "current_app": state.get("current_app"),
                "notifications": state.get("notifications", {}).get("parsed", [])[:5],
                "timestamp": state.get("timestamp"),
            }
        except Exception as e:
            return {
                "success": False,
                "device_id": device_id,
                "error": str(e),
            }

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all active sessions."""
        sessions = self.session_manager.list_active_sessions()
        return [
            {
                "session_id": s.session_id,
                "device_id": s.device_id,
                "provider": s.provider,
                "task": s.task,
                "status": s.status,
                "step_count": s.step_count,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ]

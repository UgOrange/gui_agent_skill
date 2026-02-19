#!/usr/bin/env python3
"""GUI Agent Skill CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path


def _ensure_path() -> None:
    """Ensure local module path is available."""
    skill_root = Path(__file__).resolve().parent
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))


_ensure_path()

from core.executor import GUIAgentExecutor, ExecutorError, cleanup_tracked_subprocesses
from core.config import load_skill_config
from core.model_providers import list_providers, validate_provider


def _add_common_cli_options(
    parser: argparse.ArgumentParser,
    *,
    for_subcommand: bool = False,
) -> None:
    """Add options that should work both before and after subcommands."""
    config_default = argparse.SUPPRESS if for_subcommand else None
    output_default = argparse.SUPPRESS if for_subcommand else True
    parser.add_argument(
        "--config",
        default=config_default,
        help="Path to config file.",
    )
    parser.add_argument(
        "--json",
        "-json",
        action="store_true",
        dest="output_json",
        default=output_default,
        help="Output result in JSON format (default).",
    )
    parser.add_argument(
        "--text",
        "-text",
        action="store_false",
        dest="output_json",
        default=output_default,
        help="Output results in human-readable format",
    )


def _configure_stdio() -> None:
    """
    Avoid Windows console encode crashes (e.g., argparse --help).
    Keep current encoding and relax error handling to replacement mode.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except Exception:
                continue


def _force_exit(code: int = 130) -> None:
    try:
        cleanup_tracked_subprocesses()
    except Exception:
        pass
    os._exit(code)


def _start_windows_parent_watchdog(parent_pid: int) -> None:
    """Windows parent-process watchdog."""
    try:
        import ctypes
        import time

        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        WAIT_OBJECT_0 = 0x00000000
        INFINITE = 0xFFFFFFFF
        STILL_ACTIVE = 259

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
    except Exception:
        return

    def _watch_parent_exit() -> None:
        # Fast path: wait on parent handle when available.
        parent_handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
        if parent_handle:
            try:
                wait_result = kernel32.WaitForSingleObject(parent_handle, INFINITE)
                if wait_result == WAIT_OBJECT_0:
                    _force_exit(130)
            finally:
                try:
                    kernel32.CloseHandle(parent_handle)
                except Exception:
                    pass
            return

        # Fallback: poll parent process liveness.
        while True:
            probe = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
                False,
                parent_pid,
            )
            if not probe:
                err = ctypes.get_last_error()
                if err in (87, 1168):  # invalid PID / not found
                    _force_exit(130)
                time.sleep(1.0)
                continue
            try:
                exit_code = ctypes.c_uint32(0)
                ok = kernel32.GetExitCodeProcess(probe, ctypes.byref(exit_code))
                if ok and exit_code.value != STILL_ACTIVE:
                    _force_exit(130)
            finally:
                kernel32.CloseHandle(probe)
            time.sleep(1.0)

    threading.Thread(
        target=_watch_parent_exit,
        name="gui-agent-parent-watchdog",
        daemon=True,
    ).start()


def _try_enable_linux_parent_death_signal(parent_pid: int) -> None:
    """
    On Linux, request SIGTERM when parent exits via prctl(PR_SET_PDEATHSIG).
    Polling watchdog is still kept as a fallback.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_PDEATHSIG = 1
        result = libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
        if result != 0:
            return
        # Avoid the race where parent exits before prctl is set.
        if os.getppid() != parent_pid:
            _force_exit(130)
    except Exception:
        return


def _start_posix_parent_watchdog(parent_pid: int) -> None:
    """POSIX parent-process watchdog (Linux/macOS)."""
    import time

    _try_enable_linux_parent_death_signal(parent_pid)

    def _watch_parent_exit() -> None:
        while True:
            current_ppid = os.getppid()
            # Parent changed or process got reparented to init/supervisor.
            if current_ppid in (0, 1) or current_ppid != parent_pid:
                _force_exit(130)
            time.sleep(1.0)

    threading.Thread(
        target=_watch_parent_exit,
        name="gui-agent-parent-watchdog",
        daemon=True,
    ).start()


def _start_parent_watchdog() -> None:
    """
    Exit this process when the direct parent process exits.
    This prevents orphaned `cli.py execute/continue` runs when
    the outer shell/tool is interrupted.
    """
    parent_pid = os.getppid()
    if parent_pid <= 0:
        return

    if os.name == "nt":
        _start_windows_parent_watchdog(parent_pid)
        return
    if os.name == "posix":
        _start_posix_parent_watchdog(parent_pid)


def _install_signal_handlers() -> None:
    """Normalize interruption signals so execute/continue can stop promptly."""

    def _handle_interrupt(signum, frame):
        raise KeyboardInterrupt()

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_interrupt)
        except Exception:
            continue


def cmd_execute(args: argparse.Namespace) -> dict:
    """Execute a GUI task."""
    executor = GUIAgentExecutor(args.config)

    if args.timeout_sec is not None and args.timeout_sec <= 0:
        return {"success": False, "error": "Invalid --timeout-sec: must be > 0"}
    if args.max_steps is not None and args.max_steps <= 0:
        return {"success": False, "error": "Invalid --max-steps: must be > 0"}

    extra_info = None
    if args.extra_info:
        try:
            extra_info = json.loads(args.extra_info)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid --extra-info JSON: {e}"}
        if not isinstance(extra_info, dict):
            return {"success": False, "error": "Invalid --extra-info JSON: must be an object"}

    return executor.execute_task(
        task=args.task,
        provider=args.provider,
        device_id=args.device_id,
        max_steps=args.max_steps,
        timeout_sec=args.timeout_sec,
        extra_info=extra_info,
        stateless=args.stateless,
    )


def cmd_continue(args: argparse.Namespace) -> dict:
    """Continue an existing session."""
    executor = GUIAgentExecutor(args.config)
    if args.timeout_sec is not None and args.timeout_sec <= 0:
        return {"success": False, "error": "Invalid --timeout-sec: must be > 0"}
    if args.max_steps is not None and args.max_steps <= 0:
        return {"success": False, "error": "Invalid --max-steps: must be > 0"}
    return executor.continue_session(
        session_id=args.session_id,
        reply=args.reply,
        task=args.task,
        device_id=args.device_id,
        max_steps=args.max_steps,
        timeout_sec=args.timeout_sec,
    )


def cmd_status(args: argparse.Namespace) -> dict:
    """Get device status."""
    executor = GUIAgentExecutor(args.config)
    return executor.get_device_status(args.device_id)


def cmd_tap(args: argparse.Namespace) -> dict:
    """Direct coordinate tap without model planning."""
    executor = GUIAgentExecutor(args.config)
    if args.timeout_sec is not None and args.timeout_sec <= 0:
        return {"success": False, "error": "Invalid --timeout-sec: must be > 0"}
    if args.post_delay_ms is not None and args.post_delay_ms < 0:
        return {"success": False, "error": "Invalid --post-delay-ms: must be >= 0"}
    return executor.execute_coordinate_tap(
        x=args.x,
        y=args.y,
        coord_space=args.coord_space,
        device_id=args.device_id,
        timeout_sec=args.timeout_sec,
        post_delay_ms=args.post_delay_ms,
    )


def cmd_devices(args: argparse.Namespace) -> dict:
    """List connected devices."""
    executor = GUIAgentExecutor(args.config)
    devices = executor.list_devices()
    if not devices:
        return {
            "success": False,
            "devices": [],
            "count": 0,
            "error": (
                "No ADB devices found. Connect a phone/emulator, enable USB debugging, "
                "and approve the debugging authorization prompt on the device."
            ),
        }
    return {
        "success": True,
        "devices": devices,
        "count": len(devices),
    }


def cmd_sessions(args: argparse.Namespace) -> dict:
    """List active sessions."""
    executor = GUIAgentExecutor(args.config)
    sessions = executor.list_sessions()
    return {
        "success": True,
        "sessions": sessions,
        "count": len(sessions),
    }


def cmd_providers(args: argparse.Namespace) -> dict:
    """List available model providers."""
    providers = list_providers()
    skill_config = None
    try:
        skill_config = load_skill_config(args.config)
    except Exception:
        # Keep providers command usable even if config loading fails.
        pass

    # Check provider configuration status.
    for p in providers:
        valid, msg = validate_provider(p["name"], skill_config)
        p["configured"] = valid
        if not valid:
            p["config_error"] = msg

    return {
        "success": True,
        "providers": providers,
        "tap_only_mode": bool(getattr(skill_config, "tap_only_mode", False)) if skill_config else False,
        "default_provider": getattr(skill_config, "default_provider", None) if skill_config else None,
    }


def main() -> int:
    _configure_stdio()
    _start_parent_watchdog()
    _install_signal_handlers()

    parser = argparse.ArgumentParser(
        prog="gui-agent",
        description="GUI Agent Skill CLI for mobile GUI automation",
    )
    _add_common_cli_options(parser)

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # execute subcommand
    exec_parser = subparsers.add_parser(
        "execute",
        aliases=["exec", "run"],
        help="Execute a GUI task",
    )
    _add_common_cli_options(exec_parser, for_subcommand=True)
    exec_parser.add_argument(
        "--task",
        "-t",
        required=True,
        help="Task description to execute.",
    )
    exec_parser.add_argument(
        "--provider",
        "-p",
        default=None,
        help="Model provider (local/stepfun/zhipu/qwen).",
    )
    exec_parser.add_argument(
        "--device-id",
        "-d",
        default=None,
        help="ADB device ID.",
    )
    exec_parser.add_argument(
        "--max-steps",
        "-m",
        type=int,
        default=None,
        help="Maximum execution steps",
    )
    exec_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=None,
        help="Operation timeout in seconds. If omitted, use config default.",
    )
    exec_parser.add_argument(
        "--stateless",
        "--no-session",
        action="store_true",
        dest="stateless",
        help=(
            "Use one-shot stateless mode: new conversation each call, "
            "no local session persistence, no forced Home reset."
        ),
    )
    exec_parser.add_argument(
        "--extra-info",
        "-e",
        default=None,
        help="Extra JSON payload forwarded to adapter.",
    )
    exec_parser.set_defaults(func=cmd_execute)

    # continue subcommand
    cont_parser = subparsers.add_parser(
        "continue",
        aliases=["cont"],
        help="Continue an existing session",
    )
    _add_common_cli_options(cont_parser, for_subcommand=True)
    cont_parser.add_argument(
        "--session-id",
        "-s",
        default=None,
        help="Session ID (use latest active session when omitted).",
    )
    cont_parser.add_argument(
        "--reply",
        "-r",
        default=None,
        help="User reply content.",
    )
    cont_parser.add_argument(
        "--task",
        "-t",
        default=None,
        help="New task description (optional).",
    )
    cont_parser.add_argument(
        "--device-id",
        "-d",
        default=None,
        help="ADB device ID.",
    )
    cont_parser.add_argument(
        "--max-steps",
        "-m",
        type=int,
        default=None,
        help="Maximum execution steps",
    )
    cont_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=None,
        help="Operation timeout in seconds. If omitted, use config default.",
    )
    cont_parser.set_defaults(func=cmd_continue)

    # status subcommand
    status_parser = subparsers.add_parser(
        "status",
        help="Get device status",
    )
    _add_common_cli_options(status_parser, for_subcommand=True)
    status_parser.add_argument(
        "--device-id",
        "-d",
        default=None,
        help="ADB device ID.",
    )
    status_parser.set_defaults(func=cmd_status)

    # tap subcommand
    tap_parser = subparsers.add_parser(
        "tap",
        aliases=["click"],
        help="Direct coordinate tap without model planning",
    )
    _add_common_cli_options(tap_parser, for_subcommand=True)
    tap_parser.add_argument(
        "--x",
        type=float,
        required=True,
        help="X coordinate. In auto mode, 0..1 is treated as ratio if both x/y are in range.",
    )
    tap_parser.add_argument(
        "--y",
        type=float,
        required=True,
        help="Y coordinate. In auto mode, 0..1 is treated as ratio if both x/y are in range.",
    )
    tap_parser.add_argument(
        "--coord-space",
        choices=["auto", "pixel", "ratio"],
        default="auto",
        help="Coordinate space for x/y: auto, pixel, or ratio.",
    )
    tap_parser.add_argument(
        "--device-id",
        "-d",
        default=None,
        help="ADB device ID",
    )
    tap_parser.add_argument(
        "--post-delay-ms",
        type=int,
        default=350,
        help="Delay after tap before capturing post-state screenshot (milliseconds).",
    )
    tap_parser.add_argument(
        "--timeout-sec",
        type=int,
        default=None,
        help="Operation timeout in seconds. If omitted, use config default.",
    )
    tap_parser.set_defaults(func=cmd_tap)

    # devices subcommand
    devices_parser = subparsers.add_parser(
        "devices",
        help="List connected devices",
    )
    _add_common_cli_options(devices_parser, for_subcommand=True)
    devices_parser.set_defaults(func=cmd_devices)

    # sessions subcommand
    sessions_parser = subparsers.add_parser(
        "sessions",
        help="List active sessions",
    )
    _add_common_cli_options(sessions_parser, for_subcommand=True)
    sessions_parser.set_defaults(func=cmd_sessions)

    # providers subcommand
    providers_parser = subparsers.add_parser(
        "providers",
        help="List available model providers",
    )
    _add_common_cli_options(providers_parser, for_subcommand=True)
    providers_parser.set_defaults(func=cmd_providers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    result: dict
    try:
        result = args.func(args)
    except KeyboardInterrupt:
        cleaned = cleanup_tracked_subprocesses()
        result = {
            "success": False,
            "error": "Execution interrupted",
            "message": "Execution interrupted by user; task stopped.",
        }
        if cleaned > 0:
            result["terminated_subprocesses"] = cleaned
    except ExecutorError as e:
        result = {"success": False, "error": str(e)}
    except Exception as e:
        result = {"success": False, "error": f"Unexpected error: {e}"}
    finally:
        tail_cleaned = cleanup_tracked_subprocesses()
        if tail_cleaned > 0:
            already = int(result.get("terminated_subprocesses", 0))
            result["terminated_subprocesses"] = already + tail_cleaned

    # Output result
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human_readable(result)

    return 0 if result.get("success", False) else 1


def _print_human_readable(result: dict) -> None:
    """Print result in human-readable format."""
    if result.get("success"):
        print("[OK] Success")
        if "caption" in result:
            print(f"  State: {result['caption']}")
        if "session_id" in result:
            print(f"  Session: {result['session_id']}")
        if "next_action" in result:
            print(f"  Next action: {result['next_action']}")
        if "screenshot_path" in result:
            print(f"  Screenshot: {result['screenshot_path']}")
    else:
        print("[ERROR] Failed")
        if "error" in result:
            print(f"  Error: {result['error']}")
        if "message" in result:
            print(f"  Message: {result['message']}")


if __name__ == "__main__":
    sys.exit(main())

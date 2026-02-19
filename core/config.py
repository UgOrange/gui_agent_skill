"""Configuration management for GUI Agent Skill."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SessionConfig:
    storage_dir: Path = field(default_factory=lambda: Path.home() / ".gui_agent_skill" / "sessions")
    expire_seconds: int = 3600


@dataclass
class OutputConfig:
    dir: Path = field(default_factory=lambda: Path.home() / ".gui_agent_skill" / "outputs")
    save_screenshot: bool = True
    enable_caption: bool = True


@dataclass
class SkillConfig:
    default_provider: str = "local"
    tap_only_mode: bool = False
    default_device_id: str | None = None
    default_max_steps: int = 20
    default_operation_timeout_sec: int | None = None
    session: SessionConfig = field(default_factory=SessionConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    gui_agent_forge_path: Path | None = None
    device: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)


def _expand_env(value: Any) -> Any:
    """Recursively expand environment variables like ${VAR_NAME}."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        return pattern.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def _resolve_path(path_str: str | None) -> Path | None:
    """Resolve path and support ~ expansion."""
    if not path_str:
        return None
    path = Path(path_str)
    if str(path).startswith("~"):
        path = path.expanduser()
    return path.resolve()


def _find_gui_agent_forge_path() -> Path | None:
    """Auto-discover gui_agent_forge project root."""

    def is_forge_root(path: Path) -> bool:
        return (
            path.is_dir()
            and (path / "__init__.py").exists()
            and (path / "adapters").is_dir()
            and (path / "state").is_dir()
        )

    def normalize_candidate(path: Path) -> Path | None:
        if is_forge_root(path):
            return path.resolve()
        nested = path / "gui_agent_forge"
        if is_forge_root(nested):
            return nested.resolve()
        return None

    # 1) Environment variable has highest priority.
    env_path = os.environ.get("GUI_AGENT_FORGE_PATH")
    if env_path:
        candidate = normalize_candidate(Path(env_path).expanduser())
        if candidate:
            return candidate

    # 2) Walk upward from current file to support both standalone and nested layouts.
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        candidate = normalize_candidate(parent)
        if candidate:
            return candidate

    return None


def load_skill_config(config_path: str | Path | None = None) -> SkillConfig:
    """Load skill configuration."""
    if config_path is None:
        # Fallback order: user config, then bundled default config.
        default_paths = [
            Path.home() / ".gui_agent_skill" / "config.yaml",
            Path(__file__).parent.parent / "config" / "skill_config.yaml",
        ]
        for path in default_paths:
            if path.exists():
                config_path = path
                break

    if config_path is None:
        return SkillConfig(gui_agent_forge_path=_find_gui_agent_forge_path())

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    raw_config = _expand_env(raw_config)

    session_cfg = raw_config.get("session", {})
    session = SessionConfig(
        storage_dir=_resolve_path(session_cfg.get("storage_dir")) or SessionConfig().storage_dir,
        expire_seconds=session_cfg.get("expire_seconds", 3600),
    )

    output_cfg = raw_config.get("output", {})
    output = OutputConfig(
        dir=_resolve_path(output_cfg.get("dir")) or OutputConfig().dir,
        save_screenshot=output_cfg.get("save_screenshot", True),
        enable_caption=output_cfg.get("enable_caption", True),
    )

    forge_path = _resolve_path(raw_config.get("gui_agent_forge_path"))
    if forge_path is None:
        forge_path = _find_gui_agent_forge_path()

    return SkillConfig(
        default_provider=raw_config.get("default_provider", "local"),
        tap_only_mode=bool(raw_config.get("tap_only_mode", False)),
        default_device_id=raw_config.get("default_device_id"),
        default_max_steps=raw_config.get("default_max_steps", 20),
        default_operation_timeout_sec=raw_config.get("default_operation_timeout_sec"),
        session=session,
        output=output,
        providers=raw_config.get("providers", {}),
        gui_agent_forge_path=forge_path,
        device=raw_config.get("device", {}),
        state=raw_config.get("state", {}),
    )


def get_forge_config(skill_config: SkillConfig, provider_name: str) -> dict[str, Any]:
    """Build gui_agent_forge-compatible adapter config."""
    provider = skill_config.providers.get(provider_name, {})
    adapter_type = provider.get("adapter", "gelab_local")

    adapter_config = {
        "name": provider_name,
        "type": adapter_type,
    }

    if adapter_type == "gelab_local":
        adapter_config.update({
            "working_dir": "vendor/gelab_zero",
            "reply_mode": "pass_to_client",
            "enable_intermediate_logs": False,
            "enable_final_screenshot": False,
            "agent_loop_config": {
                "task_type": "parser_0922_summary",
                "model_config": {
                    "model_name": provider.get("model_name", "gelab-zero-4b-preview"),
                    "model_provider": provider.get("model_provider", "local"),
                    "args": {
                        "temperature": 0.1,
                        "top_p": 0.95,
                        "max_tokens": 4096,
                        "timeout_sec": 55,
                    },
                    "image_preprocess": {
                        "is_resize": True,
                        "target_image_size": [728, 728],
                    },
                },
            },
            "server_config": {
                "log_dir": "running_log/server_log/traces",
                "image_dir": "running_log/server_log/images",
            },
        })
    elif adapter_type == "open_autoglm":
        adapter_config.update({
            "mode": "python",
            "model_config": {
                "model_name": provider.get("model_name", "glm-4.5v"),
                "api_key": provider.get("api_key", ""),
                "base_url": provider.get("base_url", "https://open.bigmodel.cn/api/paas/v4/"),
            },
            "agent_config": {
                "max_steps": skill_config.default_max_steps,
            },
        })
    elif adapter_type == "http":
        adapter_config.update({
            "base_url": provider.get("base_url", ""),
            "start_endpoint": "/start_task",
            "continue_endpoint": "/continue_task",
        })

    return {
        "default_adapter": provider_name,
        "adapters": [adapter_config],
        "device": skill_config.device,
        "state": skill_config.state,
    }

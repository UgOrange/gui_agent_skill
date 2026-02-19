"""Model provider configuration."""

from __future__ import annotations

import os
from typing import Any


# Predefined provider configurations.
PROVIDERS: dict[str, dict[str, Any]] = {
    "local": {
        "adapter": "gelab_local",
        "model_provider": "local",
        "model_name": "gelab-zero-4b-preview",
        "description": "Local GELab-Zero model served by Ollama",
        "requires_api_key": False,
        "api_base": "http://localhost:11434/v1",
    },
    "stepfun": {
        "adapter": "gelab_local",
        "model_provider": "stepfun",
        "model_name": "step-1v-8k",
        "description": "StepFun Step-1V vision model",
        "requires_api_key": True,
        "api_key_env": "STEPFUN_API_KEY",
        "api_base": "https://api.stepfun.com/v1",
    },
    "zhipu": {
        "adapter": "open_autoglm",
        "model_name": "glm-4.5v",
        "description": "Zhipu AI GLM-4.5V vision model",
        "requires_api_key": True,
        "api_key_env": "ZHIPUAI_API_KEY",
        "api_base": "https://open.bigmodel.cn/api/paas/v4/",
    },
    "qwen": {
        "adapter": "http",
        "model_name": "qwen-vl-max",
        "description": "Alibaba Tongyi Qwen-VL vision model",
        "requires_api_key": True,
        "api_key_env": "DASHSCOPE_API_KEY",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
}


def _get_configured_api_key(provider_name: str, skill_config: Any | None = None) -> str:
    """Read provider API key from skill config."""
    if skill_config is None:
        return ""
    providers = getattr(skill_config, "providers", {}) or {}
    provider_cfg = providers.get(provider_name, {}) or {}
    api_key = provider_cfg.get("api_key", "")
    return str(api_key).strip() if api_key else ""


def seed_provider_env_from_config(
    skill_config: Any | None = None,
    provider_name: str | None = None,
) -> None:
    """Inject API keys from config into environment variables for adapters."""
    if skill_config is None:
        return

    targets = [provider_name] if provider_name else list(PROVIDERS.keys())
    for name in targets:
        provider_cfg = PROVIDERS.get(name, {})
        api_key_env = provider_cfg.get("api_key_env", "")
        if not api_key_env:
            continue
        if os.environ.get(api_key_env):
            continue
        api_key = _get_configured_api_key(name, skill_config)
        if api_key:
            os.environ[api_key_env] = api_key


def get_provider_config(provider_name: str) -> dict[str, Any] | None:
    """Get provider configuration."""
    return PROVIDERS.get(provider_name)


def list_providers() -> list[dict[str, Any]]:
    """List all available providers."""
    result = []
    for name, config in PROVIDERS.items():
        result.append({
            "name": name,
            "description": config.get("description", ""),
            "adapter": config.get("adapter", ""),
            "model_name": config.get("model_name", ""),
            "requires_api_key": config.get("requires_api_key", False),
            "api_key_env": config.get("api_key_env", ""),
        })
    return result


def validate_provider(
    provider_name: str,
    skill_config: Any | None = None,
) -> tuple[bool, str]:
    """Validate whether provider configuration is usable."""
    config = PROVIDERS.get(provider_name)
    if not config:
        # Allow custom providers declared only in skill config.
        providers = getattr(skill_config, "providers", {}) if skill_config else {}
        if provider_name in providers:
            return True, "OK"
        return False, f"Unknown provider: {provider_name}"

    if config.get("requires_api_key"):
        api_key_env = config.get("api_key_env", "")
        env_api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""
        cfg_api_key = _get_configured_api_key(provider_name, skill_config)
        if api_key_env and not env_api_key and not cfg_api_key:
            return (
                False,
                f"Missing API key: set {api_key_env} env var "
                f"or configure providers.{provider_name}.api_key in config",
            )

    return True, "OK"


def get_adapter_type(provider_name: str) -> str | None:
    """Get adapter type for a provider."""
    config = PROVIDERS.get(provider_name)
    if config:
        return config.get("adapter")
    return None

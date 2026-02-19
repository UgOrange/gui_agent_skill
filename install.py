#!/usr/bin/env python3
"""GUI Agent Skill installer.

Claude Code: install slash commands + agents.
Codex: install custom prompts + skills.
"""

from __future__ import annotations

import argparse
import getpass
import shutil
import sys
from pathlib import Path

import yaml


SUPPORTED_PROVIDERS = ("local", "stepfun", "zhipu", "qwen")
PROVIDER_API_ENV = {
    "stepfun": "STEPFUN_API_KEY",
    "zhipu": "ZHIPUAI_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
}


def get_claude_config_dir() -> Path:
    """Return Claude Code config directory."""
    return Path.home() / ".claude"


def get_codex_config_dir() -> Path:
    """Return Codex config directory."""
    return Path.home() / ".codex"


def install_commands(skill_dir: Path, target_dir: Path, force: bool = False) -> int:
    """Install Claude slash commands."""
    src_commands = skill_dir / "commands"
    dst_commands = target_dir / "commands"

    if not src_commands.exists():
        print(f"Error: commands directory not found: {src_commands}")
        return 1

    installed = 0
    for namespace_dir in src_commands.iterdir():
        if not namespace_dir.is_dir():
            continue

        dst_namespace = dst_commands / namespace_dir.name
        dst_namespace.mkdir(parents=True, exist_ok=True)

        for cmd_file in namespace_dir.glob("*.md"):
            dst_file = dst_namespace / cmd_file.name
            if dst_file.exists() and not force:
                print(f"Skip (already exists): {dst_file}")
                continue

            shutil.copy2(cmd_file, dst_file)
            print(f"Installed: {dst_file}")
            installed += 1

    return installed


def install_agents(skill_dir: Path, target_dir: Path, force: bool = False) -> int:
    """Install Claude custom agents."""
    src_agents = skill_dir / "agents"
    dst_agents = target_dir / "agents"

    if not src_agents.exists():
        print(f"Error: agents directory not found: {src_agents}")
        return 0

    installed = 0
    for namespace_dir in src_agents.iterdir():
        if not namespace_dir.is_dir():
            continue

        dst_namespace = dst_agents / namespace_dir.name
        dst_namespace.mkdir(parents=True, exist_ok=True)

        for agent_file in namespace_dir.glob("*.md"):
            dst_file = dst_namespace / agent_file.name
            if dst_file.exists() and not force:
                print(f"Skip (already exists): {dst_file}")
                continue

            shutil.copy2(agent_file, dst_file)
            print(f"Installed: {dst_file}")
            installed += 1

    return installed


def install_codex_prompts(skill_dir: Path, target_dir: Path, force: bool = False) -> int:
    """Install Codex custom prompts."""
    src_prompts = skill_dir / "codex" / "prompts"
    dst_prompts = target_dir / "prompts"

    if not src_prompts.exists():
        print(f"Error: Codex prompts directory not found: {src_prompts}")
        return 0

    dst_prompts.mkdir(parents=True, exist_ok=True)
    installed = 0
    for prompt_file in sorted(src_prompts.glob("*.md")):
        dst_file = dst_prompts / prompt_file.name
        if dst_file.exists() and not force:
            print(f"Skip (already exists): {dst_file}")
            continue

        shutil.copy2(prompt_file, dst_file)
        print(f"Installed: {dst_file}")
        installed += 1

    return installed


def install_codex_skills(skill_dir: Path, target_dir: Path, force: bool = False) -> int:
    """Install Codex skills (each directory must include SKILL.md)."""
    src_skills = skill_dir / "skills"
    dst_skills = target_dir / "skills"

    if not src_skills.exists():
        print(f"Error: Codex skills directory not found: {src_skills}")
        return 0

    dst_skills.mkdir(parents=True, exist_ok=True)
    installed = 0
    for skill_dir_item in sorted(src_skills.iterdir()):
        if not skill_dir_item.is_dir():
            continue

        skill_md = skill_dir_item / "SKILL.md"
        if not skill_md.exists():
            print(f"Skip (missing SKILL.md): {skill_dir_item}")
            continue

        dst_skill_dir = dst_skills / skill_dir_item.name
        if dst_skill_dir.exists():
            if not force:
                print(f"Skip (already exists): {dst_skill_dir}")
                continue
            shutil.rmtree(dst_skill_dir)

        shutil.copytree(skill_dir_item, dst_skill_dir)
        print(f"Installed: {dst_skill_dir}")
        installed += 1

    return installed


def create_user_config(skill_dir: Path) -> None:
    """Create/update user configuration directory."""
    user_config_dir = Path.home() / ".gui_agent_skill"
    user_config_dir.mkdir(parents=True, exist_ok=True)

    src_config = skill_dir / "config" / "skill_config.yaml"
    dst_config = user_config_dir / "config.yaml"

    if not dst_config.exists() and src_config.exists():
        shutil.copy2(src_config, dst_config)
        print(f"Created user config: {dst_config}")

    (user_config_dir / "sessions").mkdir(exist_ok=True)
    (user_config_dir / "outputs").mkdir(exist_ok=True)
    print(f"Created data directories under: {user_config_dir}")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def _resolve_adb_command_for_install(skill_dir: Path) -> str:
    user_cfg_path = Path.home() / ".gui_agent_skill" / "config.yaml"
    cfg = _load_yaml(user_cfg_path)
    if not cfg:
        cfg = _load_yaml(skill_dir / "config" / "skill_config.yaml")
    device_cfg = cfg.get("device", {}) or {}
    adb_cmd = str(device_cfg.get("adb_path") or "adb").strip()
    return adb_cmd or "adb"


def check_adb_environment(skill_dir: Path) -> None:
    """Validate adb availability and show actionable hints if missing."""
    adb_cmd = _resolve_adb_command_for_install(skill_dir)
    adb_path = Path(adb_cmd)
    if adb_path.is_absolute() or adb_path.parent != Path("."):
        adb_ready = adb_path.exists()
    else:
        adb_ready = shutil.which(adb_cmd) is not None

    print("=== ADB Environment Check ===")
    if adb_ready:
        print(f"ADB check passed: {adb_cmd}")
        return

    print(
        "ADB was not found. Install Android platform-tools and make sure adb is in PATH, "
        "or set device.adb_path in ~/.gui_agent_skill/config.yaml."
    )
    print("Download: https://developer.android.com/tools/releases/platform-tools")


def _mask_secret(secret: str) -> str:
    if len(secret) <= 6:
        return "*" * len(secret)
    return f"{secret[:3]}{'*' * (len(secret) - 5)}{secret[-2:]}"


def _prompt_provider(default_provider: str, default_tap_only: bool) -> str | None:
    print("\n=== Install Configuration Wizard ===")
    print("Available providers:")
    print("  0. tap-only (no provider, only tap/click mode)")
    for idx, name in enumerate(SUPPORTED_PROVIDERS, start=1):
        print(f"  {idx}. {name}")

    default_label = "tap-only" if default_tap_only else default_provider
    choice = input(f"Select default provider [{default_label}]: ").strip().lower()
    if not choice:
        return None if default_tap_only else default_provider
    if choice in {"0", "none", "tap-only", "tap_only", "tap"}:
        return None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(SUPPORTED_PROVIDERS):
            return SUPPORTED_PROVIDERS[idx]
    if choice in SUPPORTED_PROVIDERS:
        return choice

    print(f"Invalid input. Keep default provider: {default_label}")
    return None if default_tap_only else default_provider


def _prompt_api_key(provider: str, env_name: str) -> str:
    prompt = f"Input API key for {provider} (leave blank to skip, equivalent to env {env_name}): "
    return getpass.getpass(prompt).strip()


def update_user_config(
    skill_dir: Path,
    provider: str | None,
    tap_only: bool,
    api_keys: dict[str, str],
    interactive: bool,
) -> dict[str, object]:
    """Update provider and API key settings in user config during install."""
    user_config_dir = Path.home() / ".gui_agent_skill"
    user_config_dir.mkdir(parents=True, exist_ok=True)

    src_config = skill_dir / "config" / "skill_config.yaml"
    dst_config = user_config_dir / "config.yaml"
    if not dst_config.exists() and src_config.exists():
        shutil.copy2(src_config, dst_config)
        print(f"Created user config: {dst_config}")

    cfg = _load_yaml(dst_config)
    cfg.setdefault("providers", {})

    current_default = str(cfg.get("default_provider", "") or "").strip() or "local"
    current_tap_only = bool(cfg.get("tap_only_mode", False))

    selected_provider: str | None = provider
    tap_only_mode = tap_only

    if provider is not None:
        tap_only_mode = False
    elif tap_only:
        tap_only_mode = True
    elif interactive and sys.stdin.isatty():
        prompted = _prompt_provider(current_default, current_tap_only)
        if prompted is None:
            tap_only_mode = True
            selected_provider = None
        else:
            tap_only_mode = False
            selected_provider = prompted
    else:
        tap_only_mode = current_tap_only
        selected_provider = None if current_tap_only else current_default

    if tap_only_mode:
        cfg["tap_only_mode"] = True
        cfg["default_provider"] = ""
    else:
        selected_provider = selected_provider or current_default
        cfg["tap_only_mode"] = False
        cfg["default_provider"] = selected_provider

    provider_keys = {k: v.strip() for k, v in api_keys.items() if v and v.strip()}

    if not tap_only_mode and selected_provider is not None:
        required_env = PROVIDER_API_ENV.get(selected_provider)
        existing_cfg_key = str(
            (cfg.get("providers", {}).get(selected_provider, {}) or {}).get("api_key", "")
        ).strip()
        if (
            required_env
            and selected_provider not in provider_keys
            and not existing_cfg_key
            and interactive
            and sys.stdin.isatty()
        ):
            prompted_key = _prompt_api_key(selected_provider, required_env)
            if prompted_key:
                provider_keys[selected_provider] = prompted_key

    for name, key in provider_keys.items():
        cfg["providers"].setdefault(name, {})
        cfg["providers"][name]["api_key"] = key

    _save_yaml(dst_config, cfg)

    print("\n=== Configuration Summary ===")
    if tap_only_mode:
        print("Mode: tap-only (providerless)")
    else:
        print(f"Default provider: {selected_provider}")
    if provider_keys:
        for name, key in provider_keys.items():
            print(f"{name} API key: {_mask_secret(key)}")
    else:
        print("API key: not written by installer (you can set config/env later)")

    return {
        "tap_only_mode": tap_only_mode,
        "default_provider": None if tap_only_mode else selected_provider,
    }


def uninstall(skill_dir: Path, target_dir: Path, target_name: str) -> None:
    """Uninstall GUI Agent Skill artifacts from one target."""
    if target_name == "claude":
        cmd_dir = target_dir / "commands" / "gui-agent"
        if cmd_dir.exists():
            shutil.rmtree(cmd_dir)
            print(f"[{target_name}] Removed: {cmd_dir}")

        agent_dir = target_dir / "agents" / "gui-agent"
        if agent_dir.exists():
            shutil.rmtree(agent_dir)
            print(f"[{target_name}] Removed: {agent_dir}")

    elif target_name == "codex":
        src_prompts = skill_dir / "codex" / "prompts"
        dst_prompts = target_dir / "prompts"
        if src_prompts.exists() and dst_prompts.exists():
            for prompt_file in sorted(src_prompts.glob("*.md")):
                dst_file = dst_prompts / prompt_file.name
                if dst_file.exists():
                    dst_file.unlink()
                    print(f"[{target_name}] Removed: {dst_file}")

        src_skills = skill_dir / "skills"
        dst_skills = target_dir / "skills"
        if src_skills.exists() and dst_skills.exists():
            for skill_dir_item in sorted(src_skills.iterdir()):
                if not skill_dir_item.is_dir():
                    continue
                dst_skill_dir = dst_skills / skill_dir_item.name
                if dst_skill_dir.exists():
                    shutil.rmtree(dst_skill_dir)
                    print(f"[{target_name}] Removed: {dst_skill_dir}")

        # Cleanup old accidental install paths from legacy versions.
        legacy_cmd_dir = target_dir / "commands" / "gui-agent"
        if legacy_cmd_dir.exists():
            shutil.rmtree(legacy_cmd_dir)
            print(f"[{target_name}] Removed legacy path: {legacy_cmd_dir}")

        legacy_agent_dir = target_dir / "agents" / "gui-agent"
        if legacy_agent_dir.exists():
            shutil.rmtree(legacy_agent_dir)
            print(f"[{target_name}] Removed legacy path: {legacy_agent_dir}")

    print(f"[{target_name}] Uninstall complete")


def resolve_install_targets(args: argparse.Namespace) -> dict[str, Path]:
    """Resolve install/uninstall targets for claude/codex/both/auto."""
    claude_dir = args.claude_dir or get_claude_config_dir()
    codex_dir = args.codex_dir or get_codex_config_dir()

    if args.target == "claude":
        return {"claude": claude_dir}
    if args.target == "codex":
        return {"codex": codex_dir}
    if args.target == "both":
        return {"claude": claude_dir, "codex": codex_dir}

    # auto mode:
    # 1) if explicit dir is provided, prefer it
    # 2) otherwise check existing dirs
    # 3) if unknown, install both to avoid "installed only for Claude" mismatch
    has_claude = args.claude_dir is not None or claude_dir.exists()
    has_codex = args.codex_dir is not None or codex_dir.exists()
    if has_claude and has_codex:
        return {"claude": claude_dir, "codex": codex_dir}
    if has_claude:
        return {"claude": claude_dir}
    if has_codex:
        return {"codex": codex_dir}
    return {"claude": claude_dir, "codex": codex_dir}


def main() -> int:
    parser = argparse.ArgumentParser(description="GUI Agent Skill installer")
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall GUI Agent Skill",
    )
    parser.add_argument(
        "--claude-dir",
        type=Path,
        default=None,
        help="Claude Code config directory",
    )
    parser.add_argument(
        "--codex-dir",
        type=Path,
        default=None,
        help="Codex config directory",
    )
    parser.add_argument(
        "--target",
        choices=("auto", "claude", "codex", "both"),
        default="auto",
        help="Install/uninstall target: auto, claude, codex, or both",
    )
    parser.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        default=None,
        help="Set default provider during install",
    )
    parser.add_argument(
        "--tap-only",
        action="store_true",
        help="Enable providerless tap-only mode (execute/continue disabled; tap/click only).",
    )
    parser.add_argument(
        "--stepfun-api-key",
        default=None,
        help="Write Stepfun API key during install",
    )
    parser.add_argument(
        "--zhipu-api-key",
        default=None,
        help="Write Zhipu API key during install",
    )
    parser.add_argument(
        "--dashscope-api-key",
        default=None,
        help="Write DashScope API key for qwen during install",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable interactive install prompts",
    )

    args = parser.parse_args()
    if args.provider and args.tap_only:
        print("Error: --provider and --tap-only cannot be used together.")
        return 1

    skill_dir = Path(__file__).resolve().parent
    targets = resolve_install_targets(args)

    print(f"Skill directory: {skill_dir}")
    print(f"Target mode: {args.target}")
    for name, path in targets.items():
        print(f"{name} config dir: {path}")
    print()

    if args.uninstall:
        for name, path in targets.items():
            uninstall(skill_dir, path, name)
        return 0

    check_adb_environment(skill_dir)
    print()

    total_cmd_count = 0
    total_agent_count = 0
    total_prompt_count = 0
    total_skill_count = 0

    for name, path in targets.items():
        path.mkdir(parents=True, exist_ok=True)

        if name == "claude":
            print(f"=== [{name}] Install slash commands ===")
            total_cmd_count += install_commands(skill_dir, path, args.force)

            print(f"\n=== [{name}] Install custom agents ===")
            total_agent_count += install_agents(skill_dir, path, args.force)
            print()
            continue

        if name == "codex":
            print(f"=== [{name}] Install custom prompts ===")
            total_prompt_count += install_codex_prompts(skill_dir, path, args.force)

            print(f"\n=== [{name}] Install skills ===")
            total_skill_count += install_codex_skills(skill_dir, path, args.force)
            print()
            continue

        print(f"[{name}] Unknown target, skipped")
        print()

    print("\n=== Create user config ===")
    create_user_config(skill_dir)
    config_summary = update_user_config(
        skill_dir=skill_dir,
        provider=args.provider,
        tap_only=args.tap_only,
        api_keys={
            "stepfun": args.stepfun_api_key or "",
            "zhipu": args.zhipu_api_key or "",
            "qwen": args.dashscope_api_key or "",
        },
        interactive=not args.non_interactive,
    )

    print(f"\nInstall complete. Targets: {len(targets)}")
    if "claude" in targets:
        print(f"Claude artifacts: {total_cmd_count} commands, {total_agent_count} agents")
    if "codex" in targets:
        print(f"Codex artifacts: {total_prompt_count} prompts, {total_skill_count} skills")

    print("\nHow to use:")
    tap_only_mode = bool(config_summary.get("tap_only_mode", False))
    if "claude" in targets:
        print("Claude Code:")
        if tap_only_mode:
            print("  /gui-agent:tap --x 0.5 --y 0.82 --coord-space ratio")
            print("  execute/continue are disabled in tap-only mode")
        else:
            print('  /gui-agent:execute --task "Open WeChat"')
            print('  /gui-agent:continue --reply "Confirm"')
        print("  /gui-agent:status")
        print("  /gui-agent:config")

    if "codex" in targets:
        print("Codex (CLI recommended):")
        if tap_only_mode:
            print("  python -m gui_agent_skill.cli tap --x 0.5 --y 0.82 --coord-space ratio")
            print("  execute/continue are disabled in tap-only mode")
        else:
            default_provider = config_summary.get("default_provider") or "local"
            print(
                f'  python -m gui_agent_skill.cli execute --task "Open WeChat" --provider {default_provider}'
            )
            print('  python -m gui_agent_skill.cli continue --reply "Confirm"')
        print("  python -m gui_agent_skill.cli status")
        print("  python -m gui_agent_skill.cli providers")
        print("  Or mention $gui-agent-mobile in chat to trigger the skill workflow")
        print("  Restart Codex after install to load new prompts/skills")

    return 0


if __name__ == "__main__":
    sys.exit(main())

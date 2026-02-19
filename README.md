# GUI Agent Skill

Mobile GUI automation extension for Claude Code and Codex. It controls Android phones/emulators for multi-step task execution, state capture, and normalized JSON output.

Docs: [English](README.md) | [中文](README.zh.md)

## Highlights

- Multi-provider support: `local` (Ollama GELab), `stepfun`, `zhipu`, `qwen`
- Stateful sessions: run `execute` then `continue` with `session_id`
- Stateless mode: one-shot minimal actions without local session persistence
- Runtime timeout control: `--timeout-sec` on `execute` and `continue`
- Direct coordinate tap mode: model-free `tap`/`click` using ADB
- Unified outputs: `session_id`, `next_action`, `caption`, `screenshot_path`, timeout metadata

## Install

```bash
cd D:\project\gui_agent_skill
python install.py
```

Default install target is `--target auto`:

- If `~/.claude` and/or `~/.codex` already exist, install to detected targets.
- If neither exists, install to both by default.

Specify target explicitly:

```bash
python install.py --target claude
python install.py --target codex
python install.py --target both
```

Set default provider and keys during install:

```bash
python install.py --provider zhipu --zhipu-api-key "your-zhipu-api-key"
python install.py --provider qwen --dashscope-api-key "your-dashscope-api-key"
python install.py --provider local --non-interactive
# Providerless mode (Codex controls coordinates directly):
python install.py --tap-only --non-interactive
```

`--tap-only` enables providerless mode and disables `execute`/`continue`; use `tap`/`click` for step-by-step control.

After installing to Codex, restart Codex so new prompts/skills are loaded.

## Prerequisites

- Python 3.10+
- `gui_agent_forge`
- Android `adb` (platform-tools)
- At least one connected Android device/emulator

Check ADB:

```bash
adb devices
```

If `adb` is not in `PATH`, configure `device.adb_path` in `~/.gui_agent_skill/config.yaml`.

## Quick Start

### Claude Code

```bash
/gui-agent:execute --task "Open WeChat and enter chat list"
/gui-agent:continue --reply "Select the first contact"
/gui-agent:status
/gui-agent:config
```

### Codex

Use CLI commands directly (recommended):

```bash
# Stateful flow
python -m gui_agent_skill.cli execute --task "Open WeChat and enter chat list" --provider local --timeout-sec 60
python -m gui_agent_skill.cli continue --reply "Select the first contact" --timeout-sec 60

# Stateless flow (run execute repeatedly)
python -m gui_agent_skill.cli execute --task "Open WeChat search" --stateless --timeout-sec 45
python -m gui_agent_skill.cli execute --task "Search AI and sample top 3 official-account posts" --stateless --timeout-sec 45

# Direct coordinate tap
python -m gui_agent_skill.cli tap --x 0.5 --y 0.82 --coord-space ratio --timeout-sec 20
```

You can also mention `$gui-agent-mobile` in conversation to trigger the skill workflow.

## CLI Commands

```bash
python cli.py execute --task "task" [--provider local] [--device-id ID] [--max-steps 20] [--stateless] [--timeout-sec 60]
python cli.py continue [--session-id ID] [--reply "text"] [--task "task"] [--timeout-sec 60]
python cli.py status [--device-id ID]
python cli.py tap --x 0.5 --y 0.82 --coord-space ratio [--timeout-sec 20]
python cli.py devices
python cli.py sessions
python cli.py providers
```

Notes:

- `execute` / `continue` / `status` / `tap` all validate device connectivity before running.
- If no ADB devices are connected, CLI returns a clear error with USB-debugging guidance.
- When `tap_only_mode=true` in config, `execute` and `continue` return a clear error and only direct coordinate mode is allowed.

## Output Schema (Example)

```json
{
  "success": true,
  "session_id": "abc12345",
  "task": "Open WeChat",
  "provider": "local",
  "device_id": "emulator-5554",
  "step_count": 1,
  "caption": "WeChat home screen is visible with bottom tabs.",
  "screenshot_path": "~/.gui_agent_skill/outputs/abc12345/screenshot.png",
  "next_action": "continue",
  "current_app": "com.tencent.mm/.ui.LauncherUI",
  "message": "Task in progress. Current state: ..."
}
```

## Practical Demo Scenarios

1. WeChat Daily Official Account Trend Analysis (read-only)
2. Xiaohongshu Keyword Content Research (read-only)
3. Cross-platform Product Price Comparison (JD/Taobao/Pinduoduo)
4. Stable live demo pipeline (`status` -> `execute --stateless` -> `tap`)

Ready-made demo prompts are provided in `prompt.txt`.

## Demo Videos and Matching Prompts

Local `media/*.mp4` files are removed to keep the repository lightweight. Use Google Drive links below.

### Compare Demo (Price Comparison)

Video (Google Drive): [`compare.mp4`](https://drive.google.com/file/d/1dpVcd9RciNWKVv4Rng3tkhX5riCAO2-Q/view?usp=sharing)

Preview:

[![Compare demo preview](https://drive.google.com/thumbnail?id=1dpVcd9RciNWKVv4Rng3tkhX5riCAO2-Q&sz=w1600)](https://drive.google.com/file/d/1dpVcd9RciNWKVv4Rng3tkhX5riCAO2-Q/view?usp=sharing)

Prompt (from `prompt.txt`, compare scenario):

```text
Use GUI Agent Skill to compare prices for one product across JD, Taobao, and Pinduoduo.

Product:
- "iPhone 17 128G, China version, brand new"

Required output table columns:
- Platform
- Product title
- Final price (after coupons if visible)
- Store type (official/flagship/individual)
- Estimated delivery time
- Return/refund info (if visible)
- Notes (spec mismatch risk)

Constraints:
- Stop before checkout/payment.
- Exclude non-comparable variants (activated/imported/refurbished/spec mismatch).
```

### WeChat Demo (Daily Official Account Trend Analysis)

Video (Google Drive): [`wechat.mp4`](https://drive.google.com/file/d/14ozH3U5i3kaqjddXOQScNzwlcQQUx4A-/view?usp=sharing)

Preview:

[![WeChat demo preview](https://drive.google.com/thumbnail?id=14ozH3U5i3kaqjddXOQScNzwlcQQUx4A-&sz=w1600)](https://drive.google.com/file/d/14ozH3U5i3kaqjddXOQScNzwlcQQUx4A-/view?usp=sharing)

Prompt (from `prompt.txt`, wechat scenario):

```text
Use GUI Agent Skill to complete a daily WeChat official-account trend scan in read-only mode.

Goal:
- Collect article samples and produce a daily trend summary.

Keywords:
- AI Agent
- Cross-border e-commerce
- Private-domain operations

Required output:
- Top 3 high-frequency themes
- Common title patterns
- 3 follow-up content angles

Constraints:
- Read-only. No like/comment/share/follow.
- Use execute --stateless step by step with timeout on each call.
```

## Configuration

User config path: `~/.gui_agent_skill/config.yaml`

Common fields:

- `default_provider`
- `tap_only_mode`
- `default_device_id`
- `default_operation_timeout_sec`
- `providers.<name>.api_key`
- output/session settings

## Uninstall

```bash
python install.py --uninstall
python install.py --uninstall --target both
```

## Maintenance

If you make major capability changes, update both `AGENTS.md` and `README.md`.

## License

MIT License

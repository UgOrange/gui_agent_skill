---
description: Execute a mobile GUI automation task on Android.
allowed-tools: Bash(python *), Read(**), Write(**/session.json)
argument-hint: --task "task description" [--provider local|stepfun|zhipu|qwen] [--device-id ID] [--max-steps N] [--stateless] [--timeout-sec SEC]
---

# GUI Agent Execute

Run a mobile GUI automation task via GUI Agent Skill.

## Usage

```bash
/gui-agent:execute --task "Open WeChat and enter chat list"
/gui-agent:execute --task "Recognize text on current screen" --provider zhipu
/gui-agent:execute --task "Capture current screen state" --device-id emulator-5554
```

## Arguments

- `--task, -t`: Required task description
- `--provider, -p`: Model provider (`local`, `stepfun`, `zhipu`, `qwen`)
- `--device-id, -d`: ADB device ID (recommended when multiple devices are connected)
- `--max-steps, -m`: Max execution steps (default 20)
- `--stateless, --no-session`: One-shot mode without local session persistence
- `--timeout-sec`: Per-call timeout budget in seconds

## Execution Workflow

1. Prefer `python -m gui_agent_skill.cli execute ...`
2. Fallback to `python cli.py execute ...` if module import fails
3. Parse JSON response and track `next_action`
4. If `next_action=needs_reply`, ask user for explicit reply
5. If `session_mode=stateless`, run another `execute --stateless` instead of `continue`

## Timeout Behavior

On timeout, JSON includes:

- `timed_out: true`
- `timeout_sec`
- `terminated_subprocesses` (if forced cleanup happened)

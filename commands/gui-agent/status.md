---
description: View current Android device status (app, notifications, timestamp).
allowed-tools: Bash(python *), Read(**)
argument-hint: [--device-id ID]
---

# GUI Agent Status

Get a lightweight snapshot of current device state.

## Usage

```bash
/gui-agent:status
/gui-agent:status --device-id emulator-5554
```

## Arguments

- `--device-id, -d`: Optional ADB device ID

## Workflow

1. Run `python -m gui_agent_skill.cli status $ARGUMENTS`
2. Fallback to `python cli.py status $ARGUMENTS` if needed
3. Return key fields: `device_id`, `current_app`, `notifications`, `timestamp`

## Related Commands

```bash
python -m gui_agent_skill.cli devices
python -m gui_agent_skill.cli sessions
```

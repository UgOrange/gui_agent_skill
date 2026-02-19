---
description: View current Android device status
argument-hint: [--device-id ID]
---

Query current Android device status.

Run in order:
1. `python -m gui_agent_skill.cli status $ARGUMENTS`
2. Fallback: `python cli.py status $ARGUMENTS`
3. Return key fields: `device_id`, `current_app`, `notifications`, `timestamp`

For connection troubleshooting, you can also run:

- `python -m gui_agent_skill.cli devices`
- `python -m gui_agent_skill.cli sessions`

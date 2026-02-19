---
description: Continue an existing GUI Agent session.
allowed-tools: Bash(python *), Read(**), Write(**/session.json)
argument-hint: [--session-id ID] [--reply "reply text"] [--task "new task"] [--device-id ID] [--max-steps N] [--timeout-sec SEC]
---

# GUI Agent Continue

Continue a previously started multi-step session.

## Usage

```bash
/gui-agent:continue
/gui-agent:continue --session-id abc12345
/gui-agent:continue --reply "Select the first contact"
/gui-agent:continue --task "Go back to previous page"
```

## Arguments

- `--session-id, -s`: Session ID (latest active session if omitted)
- `--reply, -r`: User reply for interactive steps
- `--task, -t`: Optional replacement task text
- `--device-id, -d`: ADB device ID
- `--max-steps, -m`: Max execution steps
- `--timeout-sec`: Per-call timeout budget in seconds

## Workflow

1. Prefer `python -m gui_agent_skill.cli continue ...`
2. Fallback to `python cli.py continue ...` if needed
3. Parse `success`, `session_id`, `step_count`, `caption`, `next_action`
4. Guide user based on `next_action` (`continue`, `needs_reply`, `complete`)

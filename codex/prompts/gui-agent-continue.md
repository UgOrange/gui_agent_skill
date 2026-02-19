---
description: Continue an existing GUI Agent session
argument-hint: [--session-id ID] [--reply "reply text"] [--task "new task"] [--device-id ID] [--max-steps N] [--timeout-sec SEC]
---

Continue a multi-step GUI Agent session.

Run in order:
1. `python -m gui_agent_skill.cli continue $ARGUMENTS`
2. Fallback: `python cli.py continue $ARGUMENTS`
3. Summarize key fields: `success`, `session_id`, `step_count`, `caption`, `next_action`, `timed_out`, `terminated_subprocesses`
4. Guide next action by `next_action` (`continue`, `needs_reply`, `complete`)

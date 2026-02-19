---
description: Execute a new mobile GUI automation task.
argument-hint: --task "task description" [--provider local|stepfun|zhipu|qwen] [--device-id ID] [--max-steps N] [--timeout-sec SEC] [--stateless]
---

Use GUI Agent Skill to execute a new mobile GUI task.
Follow this order:
1. First try: `python -m gui_agent_skill.cli execute $ARGUMENTS`
2. If module import fails, fallback: `python cli.py execute $ARGUMENTS`
3. Parse and summarize key JSON fields: `success`, `session_id`, `caption`, `next_action`, `screenshot_path`, `session_mode`, `continuation_supported`, `timed_out`, `terminated_subprocesses`
4. If `session_mode` is `stateless`, do not call `continue`; ask the user for the next independent action and run `execute --stateless` again.
5. If `next_action` is `needs_reply` and `session_mode` is `stateful`, ask user for explicit reply content.

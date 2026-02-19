---
description: Execute a direct coordinate tap on Android without model planning.
argument-hint: --x <number> --y <number> [--coord-space auto|pixel|ratio] [--device-id ID] [--post-delay-ms MS] [--timeout-sec SEC]
---

Use GUI Agent Skill direct tap mode for one-shot coordinate interaction.
Follow this order:
1. First try: `python -m gui_agent_skill.cli tap $ARGUMENTS`
2. If module import fails, fallback: `python cli.py tap $ARGUMENTS`
3. Parse and summarize key JSON fields: `success`, `device_id`, `coordinate`, `screenshot_path`, `current_app`, `timed_out`, `terminated_subprocesses`
4. If successful, inspect `coordinate.effective_coord_space`, `coordinate.screen_size`, and `coordinate.tap` to validate coordinate mapping before next tap.

---
name: gui-agent-mobile
description: Use this skill when the user wants to automate Android GUI tasks (execute, continue, status) through gui_agent_skill from Codex.
metadata:
  short-description: Control Android GUI with gui_agent_skill
---

# GUI Agent Mobile Skill

This skill wraps `gui_agent_skill` CLI so Codex can execute complex Android GUI workflows.

## When To Use

- User asks to control an Android phone/emulator UI.
- User asks for multi-step mobile automation with session continuation.
- User asks to inspect current device/app screen state.

## Command Workflow

1. New task:
`python -m gui_agent_skill.cli execute --task "<task>" [--provider <provider>] [--device-id <id>] [--max-steps <n>] [--timeout-sec <sec>] [--stateless]`
2. Continue task:
`python -m gui_agent_skill.cli continue [--session-id <id>] [--reply "<text>"] [--task "<task>"] [--device-id <id>] [--max-steps <n>] [--timeout-sec <sec>]`
3. Status:
`python -m gui_agent_skill.cli status [--device-id <id>]`
4. Providers:
`python -m gui_agent_skill.cli providers`
5. Direct coordinate tap (no model planning):
`python -m gui_agent_skill.cli tap --x <x> --y <y> [--coord-space auto|pixel|ratio] [--device-id <id>] [--post-delay-ms <ms>] [--timeout-sec <sec>]`

Fallback when module import fails:
- `python cli.py execute ...`
- `python cli.py continue ...`
- `python cli.py status ...`
- `python cli.py providers`
- `python cli.py tap ...`

## Response Handling

- Always parse returned JSON and report `success`.
- Preserve and surface `session_id` for follow-up turns.
- Respect timeout controls: pass `--timeout-sec` for bounded runtime and check `timed_out` in error responses.
- When `terminated_subprocesses` is present, report that forced cleanup happened (timeout/interruption/tail cleanup).
- Use `next_action` to drive interaction:
  - `continue`: proceed with next step
  - `needs_reply`: ask user for explicit reply content
  - `complete`: close task
- Include `caption` and `screenshot_path` when available.
- Check `session_mode` and `continuation_supported`:
  - `session_mode=stateful`: normal `execute -> continue`
  - `session_mode=stateless`: do not call `continue`; run a new `execute --stateless` instead
- If `error=tap_only_mode_enabled`, switch to `tap`/`click`; do not retry `execute`/`continue`.

## Execution Modes (Direct vs Planner-Controlled)

Use two complementary modes based on task complexity:

- Direct execution mode (default): GUI Agent can receive and execute a single complex task
  with multiple actions/clicks.
- Planner-controlled mode (for complex global tasks): Codex/Claude acts as planner and
  GUI Agent acts as executor.

When to switch to planner-controlled mode:

- Long-horizon tasks with many dependent steps.
- High-branching tasks where each screen state changes next action.
- Tasks that need precise, low-risk, step-by-step control.

Planner-controlled workflow:

- Start one global session with `execute`, then iteratively use `continue`.
- Planner inspects each new screenshot/state and decides the next micro-steps.
- Executor receives explicit, concrete commands (UI element identity, relative position,
  row/column/layer description, buttons, sequence) and performs them.
- Repeat inspect -> plan -> execute until task completion.

Direct coordinate mode:
- Use `tap` only when the user explicitly asks for coordinate-based control.
- This path skips adapter/model planning and sends `adb shell input tap` directly.
- Prefer `--coord-space ratio` when user gives normalized coordinates, or `auto` for mixed input.
- After each `tap`, inspect returned `screenshot_path` and `coordinate` fields before the next action.
- This is the only available control path when `tap_only_mode=true` (for example: installed with `python install.py --tap-only`).

## Stateless Mode

Use stateless mode for short, incremental actions where each call must start a new conversation
without resetting the phone environment:

`python -m gui_agent_skill.cli execute --task "<task>" --stateless [--device-id <id>] [--provider <provider>]`

Behavior:
- Starts a fresh adapter conversation for each call.
- Skips local session persistence in `gui_agent_skill`.
- Keeps current app/screen context (no forced Home reset in local/gelab path).
- Best for minimal one-turn tasks.

This pattern is generic and applies to games and non-game global workflows alike.

Instruction style requirement in planner-controlled mode:

- Do not use coordinate-based commands.
- Use semantic location language (for example: "top row middle grass tile",
  "leftmost tile in the second row", "bottom toolbar shuffle button").
- To improve efficiency, planner can issue one or multiple semantic actions in one turn.

Instruction style requirement in direct coordinate mode:
- Coordinate commands are allowed.
- Verify coordinate conversion using returned `coordinate.screen_size`, `coordinate.computed`, and `coordinate.tap`.

## Safety Notes

- `execute/continue` can operate real devices; confirm intent for risky actions.
- If command fails, check ADB connectivity first; then check provider configuration unless running in tap-only mode.

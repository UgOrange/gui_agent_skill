---
description: Perform a direct coordinate tap (no model planning) and return post-action state.
allowed-tools: Bash(python *), Read(**), Write(**/session.json)
argument-hint: --x <number> --y <number> [--coord-space auto|pixel|ratio] [--device-id ID] [--post-delay-ms MS] [--timeout-sec SEC]
---

# GUI Agent Tap

Execute one direct tap with ADB and return updated state + screenshot.

## Usage

```bash
/gui-agent:tap --x 0.5 --y 0.82 --coord-space ratio
/gui-agent:tap --x 540 --y 1720 --coord-space pixel --timeout-sec 20
```

## Arguments

- `--x`: Required X coordinate (ratio or pixel)
- `--y`: Required Y coordinate (ratio or pixel)
- `--coord-space`: `auto`, `ratio`, or `pixel`
- `--device-id, -d`: ADB device ID
- `--post-delay-ms`: Wait after tap before collecting state (default 350)
- `--timeout-sec`: Per-call timeout budget

## Notes

- `auto`: treat values in `[0,1]` as ratio only when both x and y are in range
- Coordinates are clamped to visible bounds
- This mode is one-shot; run another `tap` for the next action

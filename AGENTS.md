# AGENTS.md

## 项目定位
`gui_agent_skill` 是 `gui_agent_forge` 的轻量入口层，负责 CLI 分发、配置读取、会话续接和结果标准化输出。

## 运行方式（关键差异）
- Claude Code：通过 `commands/gui-agent/*.md` + `agents/gui-agent/*.md` 触发。
- Codex：通过 `codex/prompts/*.md`（`/prompts:*`）和 `skills/gui-agent/SKILL.md` 触发。

## 调用链路
1. 命令/Prompt/Skill 触发 `python -m gui_agent_skill.cli ...`（或 `python cli.py ...`）。
2. `cli.py` 分发到 `core/executor.py`。
3. `GUIAgentExecutor` 调用 `gui_agent_forge.adapters.AdapterRegistry`。
4. 输出统一 JSON（`session_id`/`next_action`/`caption`/`screenshot_path` 等）。

## 核心目录
- `cli.py`：CLI 入口（execute/tap/continue/status/devices/sessions/providers）。
- `core/config.py`：配置加载、环境变量展开、forge 路径发现。
- `core/executor.py`：执行主流程、状态采集、截图与消息封装。
- `core/session_manager.py`：会话持久化（默认 `~/.gui_agent_skill/sessions`）。
- `core/model_providers.py`：provider 校验与 API Key 注入。
- `install.py`：安装到 Claude/Codex，并初始化用户配置。
- `codex/prompts/`：Codex 自定义 prompts 源文件。
- `skills/gui-agent/SKILL.md`：Codex skill 源文件。

## 开发最小命令
```bash
python cli.py --help
python cli.py providers
python cli.py status
python install.py --help
```

## 配置约定
- 用户配置优先：`~/.gui_agent_skill/config.yaml`
- 默认配置回退：`config/skill_config.yaml`
- API Key 来源：环境变量或 `providers.<name>.api_key`
- 可选 `tap_only_mode: true`：无 provider 模式，仅允许 `tap/click`

## 开发注意
- 不要提交真实 API key。
- Windows 下统一使用 UTF-8，避免依赖本地默认编码。
- forge 路径异常时优先检查 `GUI_AGENT_FORGE_PATH` 和 `gui_agent_forge_path`。
- 如有功能或能力的重大改动，必须同步更新 `AGENTS.md` 和 `README.md`。

## Stateless Mode (New)
- `execute` supports `--stateless` / `--no-session` for one-shot minimal actions.
- This mode starts a new adapter conversation per call but skips local session persistence.
- It should keep current app/screen context and avoid forced Home reset (local/gelab path).
- In stateless mode, follow-up should use another `execute --stateless` instead of `continue`.

## Runtime Timeout Control (New)
- `execute` and `continue` support `--timeout-sec <seconds>` to bound each call's runtime.
- If omitted, `default_operation_timeout_sec` from config is used when configured.
- Timeout failures return `timed_out=true` and `timeout_sec` in JSON error output.
- When forced cleanup occurs, JSON includes `terminated_subprocesses`.
- CLI performs a tail cleanup before exit to reduce stuck/background execution.

## ADB Preflight Checks (New)
- `install.py` performs an ADB environment check and prints actionable guidance when `adb` is missing.
- Runtime commands (`execute` / `continue` / `status` / `tap`) verify ADB availability before device operations.
- If no Android device is connected/authorized, runtime returns a clear hint to enable USB debugging and authorize the host.

## Direct Coordinate Tap Mode (New)
- `tap` (alias: `click`) supports direct coordinate tapping without calling GUI planning/model path.
- Core flow: resolve coordinates -> `adb shell input tap` -> collect post-state snapshot.
- Coordinate options:
  - `--coord-space auto|pixel|ratio`
  - `auto`: when both `x` and `y` are in `[0,1]`, interpret as ratio; otherwise pixels.
- Runtime safety:
  - Screen size is derived from screenshot PNG metadata first, then `adb shell wm size` fallback.
  - Final coordinates are clamped to visible screen bounds.
- Output includes `coordinate` detail object (`input`, `effective_coord_space`, `screen_size`, `computed`, `tap`, `clamped`).
- This mode is stateless and should be repeated with another `tap` call for step-by-step control.

## Providerless Install / Tap-Only Mode (New)
- `install.py` supports providerless setup (`--tap-only`) and interactive skip-provider selection.
- In tap-only mode, runtime disables `execute` / `continue` and returns a clear error with guidance.
- Tap-only mode is intended for Codex-controlled coordinate workflows (`tap` / `click`).

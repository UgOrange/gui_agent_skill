# GUI Agent Skill

面向 Claude Code 和 Codex 的移动端 GUI 自动化扩展，可控制 Android 手机/模拟器执行多步任务，并输出统一 JSON 结果。

文档导航：[English](README.md) | [中文](README.zh.md)

## 亮点能力

- 多模型 provider：`local`（Ollama GELab）、`stepfun`、`zhipu`、`qwen`
- 有状态会话：`execute` + `continue`
- 无状态模式：`--stateless` 单步执行，不落地本地会话
- 运行超时控制：`execute` / `continue` 支持 `--timeout-sec`
- 直接坐标点击：`tap` / `click` 走 ADB，不依赖规划模型
- 统一返回字段：`session_id`、`next_action`、`caption`、`screenshot_path` 等

## 安装

```bash
cd D:\project\gui_agent_skill
python install.py
```

默认 `--target auto`：

- 若检测到 `~/.claude` / `~/.codex`，安装到对应目录
- 若两者都不存在，默认同时安装到两端

显式指定目标：

```bash
python install.py --target claude
python install.py --target codex
python install.py --target both
```

安装时写入默认 provider / key：

```bash
python install.py --provider zhipu --zhipu-api-key "your-zhipu-api-key"
python install.py --provider qwen --dashscope-api-key "your-dashscope-api-key"
python install.py --provider local --non-interactive
# 无 provider 模式（由 Codex 直接控制坐标）：
python install.py --tap-only --non-interactive
```

`--tap-only` 会启用无 provider 模式，并禁用 `execute`/`continue`，仅允许 `tap`/`click` 逐步控制。

安装到 Codex 后请重启 Codex，使 prompts/skills 生效。

## 依赖与环境

- Python 3.10+
- `gui_agent_forge`
- Android `adb`（platform-tools）
- 已连接 Android 设备/模拟器

检查 ADB：

```bash
adb devices
```

若 `adb` 不在 PATH，可在 `~/.gui_agent_skill/config.yaml` 设置 `device.adb_path`。

## 快速使用

### Claude Code

```bash
/gui-agent:execute --task "打开微信并进入聊天列表"
/gui-agent:continue --reply "选择第一个联系人"
/gui-agent:status
/gui-agent:config
```

### Codex

推荐直接走 CLI：

```bash
# 有状态任务
python -m gui_agent_skill.cli execute --task "打开微信并进入聊天列表" --provider local --timeout-sec 60
python -m gui_agent_skill.cli continue --reply "选择第一个联系人" --timeout-sec 60

# 无状态任务
python -m gui_agent_skill.cli execute --task "打开微信搜索" --stateless --timeout-sec 45
python -m gui_agent_skill.cli execute --task "搜索 AI 并采样前 3 篇公众号文章" --stateless --timeout-sec 45

# 直接坐标点击
python -m gui_agent_skill.cli tap --x 0.5 --y 0.82 --coord-space ratio --timeout-sec 20
```

也可以在对话中显式提及 `$gui-agent-mobile` 触发 skill。

## 常用命令

```bash
python cli.py execute --task "任务描述" [--provider local] [--device-id ID] [--max-steps 20] [--stateless] [--timeout-sec 60]
python cli.py continue [--session-id ID] [--reply "回复内容"] [--task "新任务"] [--timeout-sec 60]
python cli.py status [--device-id ID]
python cli.py tap --x 0.5 --y 0.82 --coord-space ratio [--timeout-sec 20]
python cli.py devices
python cli.py sessions
python cli.py providers
```

说明：
- `execute` / `continue` / `status` / `tap` 运行前都会校验 ADB 连接。
- 若配置 `tap_only_mode=true`，`execute` / `continue` 会返回明确错误，仅允许直接坐标模式。

## 输出示例

```json
{
  "success": true,
  "session_id": "abc12345",
  "task": "打开微信",
  "provider": "local",
  "device_id": "emulator-5554",
  "step_count": 1,
  "caption": "当前显示微信主界面，底部有多个标签",
  "screenshot_path": "~/.gui_agent_skill/outputs/abc12345/screenshot.png",
  "next_action": "continue",
  "current_app": "com.tencent.mm/.ui.LauncherUI",
  "message": "任务执行中。当前状态: ..."
}
```

## 对外演示场景

1. 微信每日公众号趋势分析（只读）
2. 小红书关键词内容调研（只读）
3. 多平台商品自动比价（京东/淘宝/拼多多）
4. 稳定演示链路（`status` -> `execute --stateless` -> `tap`）

可直接复用的演示 prompts 见 `prompt.txt`。

## 演示视频与对应 Prompt

为保持仓库轻量，已移除本地 `media/*.mp4` 文件，改用 Google Drive 外链。

### Compare 演示（商品自动比价）

视频（Google Drive）：[`compare.mp4`](https://drive.google.com/file/d/1dpVcd9RciNWKVv4Rng3tkhX5riCAO2-Q/view?usp=sharing)

预览图：

[![Compare 演示预览](https://drive.google.com/thumbnail?id=1dpVcd9RciNWKVv4Rng3tkhX5riCAO2-Q&sz=w1600)](https://drive.google.com/file/d/1dpVcd9RciNWKVv4Rng3tkhX5riCAO2-Q/view?usp=sharing)

对应 Prompt（来自 `prompt.txt` 比价场景）：

```text
请使用 GUI Agent Skill 对同一商品进行跨平台比价。

商品：
- “iPhone 17 128G 国行 全新”

输出表格列：
- 平台
- 商品标题
- 到手价（如可见含券后）
- 店铺类型（自营/旗舰/个人）
- 预计时效
- 退换政策（如可见）
- 备注（规格不一致风险）

约束：
- 在下单/支付前停止。
- 排除不可比样本（激活机/翻新/非国行/规格不一致）。
```

### WeChat 演示（每日公众号趋势分析）

视频（Google Drive）：[`wechat.mp4`](https://drive.google.com/file/d/14ozH3U5i3kaqjddXOQScNzwlcQQUx4A-/view?usp=sharing)

预览图：

[![WeChat 演示预览](https://drive.google.com/thumbnail?id=14ozH3U5i3kaqjddXOQScNzwlcQQUx4A-&sz=w1600)](https://drive.google.com/file/d/14ozH3U5i3kaqjddXOQScNzwlcQQUx4A-/view?usp=sharing)

对应 Prompt（来自 `prompt.txt` 微信场景）：

```text
请使用 GUI Agent Skill，以只读方式完成“每日微信公众号趋势扫描”。

目标：
- 采样文章并输出当日趋势摘要。

关键词：
- AI Agent
- 跨境电商
- 私域运营

输出要求：
- 高频主题 Top 3
- 标题常见写法
- 后续可跟进的 3 个选题角度

约束：
- 全程只读，不进行点赞/评论/转发/关注。
- 每一步使用 execute --stateless，并配置 timeout。
```

## 配置

用户配置文件：`~/.gui_agent_skill/config.yaml`

常见项：

- `default_provider`
- `tap_only_mode`
- `default_device_id`
- `default_operation_timeout_sec`
- `providers.<name>.api_key`
- output/session 相关参数

## 卸载

```bash
python install.py --uninstall
python install.py --uninstall --target both
```

## 维护约定

若有重大能力改动，请同步更新 `AGENTS.md` 和 `README.md`。

## 许可证

MIT License

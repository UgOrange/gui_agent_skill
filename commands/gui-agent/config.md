---
description: View provider availability and configuration status.
allowed-tools: Bash(python *), Read(**), Write(**)
argument-hint: (no arguments)
---

# GUI Agent Config

Inspect available model providers and whether each provider is configured.

## Usage

```bash
/gui-agent:config
```

## Workflow

1. Run `python -m gui_agent_skill.cli providers`
2. Fallback to `python cli.py providers` if needed
3. Summarize each provider's `configured` status and `config_error` if any

## Providers

- `local`: Local Ollama GELab model, no API key required
- `stepfun`: Requires `STEPFUN_API_KEY`
- `zhipu`: Requires `ZHIPUAI_API_KEY`
- `qwen`: Requires `DASHSCOPE_API_KEY`

## Update Config

Use installer to set default provider or write API keys:

```bash
python install.py --provider <name> [--zhipu-api-key ... | --stepfun-api-key ... | --dashscope-api-key ...]
```

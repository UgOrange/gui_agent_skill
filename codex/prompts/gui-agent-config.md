---
description: View model providers and configuration status
argument-hint: (no arguments)
---

Inspect currently available GUI Agent providers.

Run in order:
1. `python -m gui_agent_skill.cli providers`
2. Fallback: `python cli.py providers`
3. Summarize each provider's `configured` status and `config_error`

If the user needs to change default provider or API keys, suggest:

`python install.py --provider <name> [--zhipu-api-key ... | --stepfun-api-key ... | --dashscope-api-key ...]`

If the user wants providerless coordinate-only control, suggest:

`python install.py --tap-only --non-interactive`

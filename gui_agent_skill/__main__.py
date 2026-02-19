#!/usr/bin/env python3
"""Package entrypoint wrapper for `python -m gui_agent_skill`."""

from __future__ import annotations

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())


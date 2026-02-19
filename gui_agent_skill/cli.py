#!/usr/bin/env python3
"""Package entrypoint wrapper for `python -m gui_agent_skill.cli`."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_root() -> None:
    # Current file: <repo>/gui_agent_skill/cli.py
    # Need repo root on sys.path so top-level `cli.py` can be imported.
    repo_root = Path(__file__).resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_root()

from cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())


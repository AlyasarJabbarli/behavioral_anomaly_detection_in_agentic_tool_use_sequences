"""Small helpers for reading YAML configs and resolving repo-relative paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file into a dict."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def repo_path(relative: str | Path) -> Path:
    """Resolve a path from a config relative to the repository root."""
    p = Path(relative)
    return p if p.is_absolute() else REPO_ROOT / p

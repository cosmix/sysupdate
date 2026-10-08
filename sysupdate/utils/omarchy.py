"""Omarchy detection helpers."""

import os
import shutil
from pathlib import Path

from .user_exec import user_exec_context, user_home

SYSTEM_OMARCHY_DIR = "/usr/share/omarchy"
OMARCHY_OVERWRITE_ARGS = ("--overwrite", f"{SYSTEM_OMARCHY_DIR}/*")


def find_omarchy_migrate(search_path: str | None, home: str) -> str | None:
    """Locate the ``omarchy-migrate`` script, or ``None`` when not installed."""
    found = shutil.which("omarchy-migrate", path=search_path)
    if found:
        return found
    candidates = []
    omarchy_path = os.environ.get("OMARCHY_PATH")
    if omarchy_path:
        candidates.append(Path(omarchy_path) / "bin" / "omarchy-migrate")
    candidates.append(Path(SYSTEM_OMARCHY_DIR) / "bin" / "omarchy-migrate")
    candidates.append(Path(home) / ".local/share/omarchy/bin/omarchy-migrate")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def is_omarchy() -> bool:
    """True when Omarchy is installed for the invoking user."""
    kwargs, search_path = user_exec_context()
    return find_omarchy_migrate(search_path, user_home(kwargs)) is not None

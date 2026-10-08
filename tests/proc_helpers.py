"""Fake subprocess helpers shared by user-level updater tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ALICE = SimpleNamespace(
    pw_name="alice",
    pw_uid=1000,
    pw_gid=1001,
    pw_dir="/home/alice",
    pw_shell="/bin/zsh",
)


def fake_proc(text: str = "", returncode: int = 0) -> MagicMock:
    """Process double usable with both ``communicate`` and streamed ``stdout``."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(text.encode(), b""))
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(side_effect=[text.encode(), b""])
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc

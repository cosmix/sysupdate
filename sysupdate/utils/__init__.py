"""Utility modules for parsing and logging."""

import asyncio
import time

from .parsing import parse_apt_output, parse_flatpak_output
from .logging import setup_logging, get_log_path


# Cache TTL in seconds (5 minutes)
_CACHE_TTL_SECONDS = 300

# Module-level cache for command availability checks.
# Values are (result, timestamp) tuples using monotonic clock.
_availability_cache: dict[tuple[str, tuple[str, ...]], tuple[bool, float]] = {}


async def command_available(command: str, *args: str) -> bool:
    """Check if a command is available on the system, with caching.

    Results are cached for up to ``_CACHE_TTL_SECONDS`` to avoid repeated
    subprocess calls for the same command.

    Args:
        command: The command to check.
        *args: Additional arguments to pass to the command.

    Returns:
        True if the command executes successfully, False otherwise.
    """
    cache_key = (command, args)
    if cache_key in _availability_cache:
        result, cached_at = _availability_cache[cache_key]
        if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
            return result
        del _availability_cache[cache_key]

    try:
        proc = await asyncio.create_subprocess_exec(
            command, *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        result = proc.returncode == 0
    except Exception:
        result = False

    _availability_cache[cache_key] = (result, time.monotonic())
    return result


def invalidate_cache(command: str | None = None) -> None:
    """Invalidate command availability cache.

    Args:
        command: Specific command to invalidate. If None, clears entire cache.
    """
    if command is None:
        _availability_cache.clear()
    else:
        keys_to_remove = [k for k in _availability_cache if k[0] == command]
        for k in keys_to_remove:
            del _availability_cache[k]


__all__ = [
    "parse_apt_output",
    "parse_flatpak_output",
    "setup_logging",
    "get_log_path",
    "command_available",
    "invalidate_cache",
]

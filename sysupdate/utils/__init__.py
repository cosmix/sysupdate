"""Utility modules for parsing and logging."""

import asyncio

from .parsing import parse_apt_output, parse_flatpak_output
from .logging import setup_logging, get_log_path


# Module-level cache for command availability checks
_availability_cache: dict[tuple[str, tuple[str, ...]], bool] = {}


async def command_available(command: str, *args: str) -> bool:
    """Check if a command is available on the system, with caching.

    Results are cached to avoid repeated subprocess calls for the same command.

    Args:
        command: The command to check.
        *args: Additional arguments to pass to the command.

    Returns:
        True if the command executes successfully, False otherwise.
    """
    cache_key = (command, args)
    if cache_key in _availability_cache:
        return _availability_cache[cache_key]

    try:
        proc = await asyncio.create_subprocess_exec(
            command, *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        result = proc.returncode == 0
    except (FileNotFoundError, Exception):
        result = False

    _availability_cache[cache_key] = result
    return result


__all__ = [
    "parse_apt_output",
    "parse_flatpak_output",
    "setup_logging",
    "get_log_path",
    "command_available",
]

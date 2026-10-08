"""Subprocess helpers shared by updaters that run as the invoking user."""

import asyncio
from typing import Any

from .base import BaseUpdater, read_process_lines


async def capture_output(
    argv: list[str], exec_kwargs: dict[str, Any]
) -> tuple[int, str]:
    """Run ``argv`` and return ``(returncode, stdout)``; stderr is discarded."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        **exec_kwargs,
    )
    try:
        stdout, _ = await proc.communicate()
    finally:
        if proc.returncode is None:
            proc.kill()
    return proc.returncode or 0, stdout.decode(errors="replace")


async def run_logged(
    owner: BaseUpdater,
    argv: list[str],
    exec_kwargs: dict[str, Any],
) -> tuple[int, str]:
    """Run ``argv`` with merged output streamed to the owner's logger.

    The process is stored on ``owner`` so ``run_update`` can kill it on
    cleanup. Returns ``(returncode, last output line)``.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        **exec_kwargs,
    )
    owner._process = proc
    last_line = ""
    if proc.stdout:
        async for line in read_process_lines(proc.stdout):
            last_line = line
            if owner._logger:
                owner._logger.log(line)
    await proc.wait()
    return proc.returncode or 0, last_line

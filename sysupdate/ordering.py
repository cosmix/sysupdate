"""Run-order gate between updaters (for example AUR waits for Pacman)."""

import asyncio
from collections.abc import Iterable


class OrderGate:
    """Lets an updater wait until the updaters it depends on have finished.

    Only labels passed to the constructor (the updaters that are actually
    running) are tracked, so a dependency on an unavailable updater is ignored.
    """

    def __init__(self, running: Iterable[str]) -> None:
        self._done = {label: asyncio.Event() for label in running}
        self._succeeded: dict[str, bool] = {}

    async def wait_for(self, after: Iterable[str]) -> str | None:
        """Wait for the running predecessors in ``after``.

        Returns a skip message naming the first predecessor that failed, or
        ``None`` when every predecessor succeeded (or none was running).
        """
        waits = [label for label in after if label in self._done]
        for label in waits:
            await self._done[label].wait()
        for label in waits:
            if not self._succeeded.get(label, False):
                return f"skipped: {label} update failed"
        return None

    def done(self, label: str, success: bool) -> None:
        """Mark ``label`` finished; call from a ``finally`` so waiters wake."""
        self._succeeded[label] = success
        self._done[label].set()

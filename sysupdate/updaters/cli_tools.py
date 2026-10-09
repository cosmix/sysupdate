"""Updaters for self-updating command line tools (Claude Code, Codex CLI)."""

import asyncio
import re
import shutil

from ..utils.user_exec import user_exec_context
from .base import (
    BaseUpdater,
    Package,
    ProgressCallback,
    UpdatePhase,
    UpdateProgress,
    read_process_lines,
)

_VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)+\S*")

# Output that means a system package manager owns the install, so the tool
# cannot update itself and that package manager's updater handles it.
_PACKAGE_MANAGED_MARKERS = (
    "managed by a package manager",
    "could not detect the codex installation method",
)


class CliToolUpdater(BaseUpdater):
    """Runs ``<command> update`` for a CLI tool that updates itself."""

    def __init__(self, command: str, display_name: str) -> None:
        super().__init__()
        self._command = command
        self._display_name = display_name
        self._exec_kwargs, self._search_path = user_exec_context()
        self._executable = command

    @property
    def name(self) -> str:
        return self._display_name

    @property
    def _logger_name(self) -> str:
        return self._command

    async def check_available(self) -> bool:
        """Check if the tool is installed."""
        resolved = shutil.which(self._command, path=self._search_path)
        if resolved is None:
            return False
        self._executable = resolved
        return True

    async def check_updates(self) -> list[Package]:
        """These tools have no check-only mode, so a dry run reports nothing."""
        return []

    async def _get_version(self) -> str:
        """Return the version printed by ``<command> --version``, or ``""``."""
        proc = await asyncio.create_subprocess_exec(
            self._executable,
            "--version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            **self._exec_kwargs,
        )
        stdout, _ = await proc.communicate()
        match = _VERSION_PATTERN.search(stdout.decode(errors="replace"))
        return match.group(0) if match else ""

    async def _do_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run ``<command> update`` and report the version change, if any."""
        before = await self._get_version()

        self._process = await asyncio.create_subprocess_exec(
            self._executable,
            "update",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **self._exec_kwargs,
        )
        stdout = self._process.stdout
        if not stdout:
            return [], False, "Failed to create subprocess stdout pipe"

        report(
            UpdateProgress(
                phase=UpdatePhase.INSTALLING,
                progress=0.5,
                current_package=self._command,
            )
        )
        last_line = ""
        package_managed = False
        async for line in read_process_lines(stdout):
            last_line = line
            lowered = line.lower()
            if any(marker in lowered for marker in _PACKAGE_MANAGED_MARKERS):
                package_managed = True
            if self._logger:
                self._logger.log(line)
        await self._process.wait()

        if package_managed:
            return [], True, ""
        if self._process.returncode != 0:
            return [], False, last_line or f"{self._command} update failed"

        after = await self._get_version()
        if after and after != before:
            return (
                [Package(name=self._command, old_version=before, new_version=after)],
                True,
                "",
            )
        return [], True, ""

"""Updaters for self-updating command line tools (Claude Code, Codex CLI)."""

import asyncio
import os
import pwd
import re
import shutil
from typing import Any

from .base import (
    BaseUpdater,
    Package,
    ProgressCallback,
    UpdatePhase,
    UpdateProgress,
    read_process_lines,
)

_VERSION_PATTERN = re.compile(r"\d+(?:\.\d+)+\S*")


def _exec_context() -> tuple[dict[str, Any], str | None]:
    """Return ``(subprocess kwargs, PATH to search)`` for running the tool.

    Under ``sudo`` the tools are per-user installs of the invoking user, so
    commands run as ``SUDO_USER`` with that user's home and ``~/.local/bin``
    on PATH. Otherwise they run as the current user with the inherited env.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if os.geteuid() != 0 or not sudo_user or sudo_user == "root":
        return {}, os.environ.get("PATH")
    try:
        pw = pwd.getpwnam(sudo_user)
    except KeyError:
        return {}, os.environ.get("PATH")

    path = f"{pw.pw_dir}/.local/bin:{os.environ.get('PATH', '')}"
    env = {
        "HOME": pw.pw_dir,
        "USER": pw.pw_name,
        "LOGNAME": pw.pw_name,
        "SHELL": pw.pw_shell,
        "PATH": path,
    }
    env.update({k: os.environ[k] for k in ("LANG", "TERM") if k in os.environ})
    kwargs: dict[str, Any] = {
        "user": pw.pw_uid,
        "group": pw.pw_gid,
        "extra_groups": os.getgrouplist(pw.pw_name, pw.pw_gid),
        "cwd": pw.pw_dir,
        "env": env,
    }
    return kwargs, path


class CliToolUpdater(BaseUpdater):
    """Runs ``<command> update`` for a CLI tool that updates itself."""

    def __init__(self, command: str, display_name: str) -> None:
        super().__init__()
        self._command = command
        self._display_name = display_name
        self._exec_kwargs, self._search_path = _exec_context()
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
        async for line in read_process_lines(stdout):
            last_line = line
            if self._logger:
                self._logger.log(line)
        await self._process.wait()

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

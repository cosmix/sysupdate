"""Omarchy updater: applies pending ``omarchy-migrate`` migrations."""

import os

from ..utils.omarchy import find_omarchy_migrate
from ..utils.user_exec import user_exec_context, user_home
from .base import (
    BaseUpdater,
    Package,
    ProgressCallback,
    UpdatePhase,
    UpdateProgress,
)
from .user_tool import capture_output, run_logged


class OmarchyMigrateUpdater(BaseUpdater):
    """Runs ``omarchy-migrate`` as the invoking user.

    Migrations keep their state under ``$HOME/.local/state/omarchy`` and call
    sudo themselves, so they must not run as root.
    """

    def __init__(self) -> None:
        super().__init__()
        self._exec_kwargs, self._search_path = user_exec_context()
        self._executable = "omarchy-migrate"
        # False once ``--pending`` exits nonzero (older Omarchy without it)
        self._pending_supported = True

    @property
    def name(self) -> str:
        return "Omarchy migrations"

    @property
    def _logger_name(self) -> str:
        return "omarchy"

    async def check_available(self) -> bool:
        """Check if the omarchy-migrate script can be found."""
        found = find_omarchy_migrate(self._search_path, user_home(self._exec_kwargs))
        if found is None:
            return False
        self._executable = found
        self._expose_omarchy_bin(found)
        return True

    def _expose_omarchy_bin(self, script: str) -> None:
        """Put Omarchy's bin dir on PATH and set ``OMARCHY_PATH`` for migrations.

        Migrations call other ``omarchy-*`` commands, which are missing from
        PATH under sudo or when the script was found by a fallback location.
        """
        bin_dir = os.path.dirname(os.path.realpath(script))
        root = os.path.dirname(bin_dir)
        env = dict(self._exec_kwargs.get("env") or os.environ)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        if os.path.isdir(os.path.join(root, "migrations")):
            env.setdefault("OMARCHY_PATH", root)
        self._exec_kwargs = {**self._exec_kwargs, "env": env}

    async def check_updates(self) -> list[Package]:
        """List pending migrations from ``omarchy-migrate --pending``."""
        code, stdout = await capture_output(
            [self._executable, "--pending"], self._exec_kwargs
        )
        self._pending_supported = code == 0
        if code != 0:
            return []
        packages = []
        for line in stdout.splitlines():
            filename = line.strip()
            if filename:
                packages.append(
                    Package(
                        name=filename.removesuffix(".sh"),
                        old_version="pending",
                        new_version="applied",
                    )
                )
        return packages

    async def _do_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run ``omarchy-migrate``; skipped when ``--pending`` reports none."""
        pending = await self.check_updates()
        if self._pending_supported and not pending:
            return [], True, ""

        report(
            UpdateProgress(
                phase=UpdatePhase.INSTALLING,
                progress=0.5,
                current_package="migrations",
            )
        )
        code, last_line = await run_logged(self, [self._executable], self._exec_kwargs)
        if code != 0:
            return [], False, last_line or "omarchy-migrate failed"
        return pending, True, ""

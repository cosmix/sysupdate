"""mise updater: upgrades tools managed by mise."""

import json
import shutil

from ..utils.user_exec import user_exec_context
from .base import (
    BaseUpdater,
    Package,
    ProgressCallback,
    UpdatePhase,
    UpdateProgress,
)
from .user_tool import capture_output, run_logged


class MiseUpdater(BaseUpdater):
    """Runs ``mise upgrade`` as the invoking user."""

    def __init__(self) -> None:
        super().__init__()
        self._exec_kwargs, self._search_path = user_exec_context()
        self._executable = "mise"

    @property
    def name(self) -> str:
        return "mise tools"

    @property
    def _logger_name(self) -> str:
        return "mise"

    async def check_available(self) -> bool:
        """Check if mise is installed for the invoking user."""
        resolved = shutil.which("mise", path=self._search_path)
        if resolved is None:
            return False
        self._executable = resolved
        return True

    async def check_updates(self) -> list[Package]:
        """List outdated tools from ``mise outdated --json``."""
        code, stdout = await capture_output(
            [self._executable, "outdated", "--json"], self._exec_kwargs
        )
        if code != 0:
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []
        packages = []
        for tool, info in data.items():
            if not isinstance(info, dict) or not info.get("latest"):
                continue
            packages.append(
                Package(
                    name=tool,
                    old_version=info.get("current") or "",
                    new_version=str(info["latest"]),
                )
            )
        return packages

    async def _do_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run ``mise upgrade`` when tools are outdated."""
        pending = await self.check_updates()
        if not pending:
            return [], True, ""

        report(
            UpdateProgress(
                phase=UpdatePhase.INSTALLING,
                progress=0.5,
                current_package="mise",
            )
        )
        code, last_line = await run_logged(
            self, [self._executable, "upgrade"], self._exec_kwargs
        )
        if code != 0:
            return [], False, last_line or "mise upgrade failed"
        return pending, True, ""

"""AUR updater (yay or paru) for Arch-based systems."""

import re
import shutil

from ..utils.user_exec import runs_as_root, user_exec_context
from .base import (
    BaseUpdater,
    Package,
    ProgressCallback,
    UpdatePhase,
    UpdateProgress,
)
from .user_tool import capture_output, run_logged

_HELPERS = ("yay", "paru")
_UPGRADE_FLAGS = {
    "yay": ["-Sua", "--noconfirm"],
    "paru": ["-Sua", "--noconfirm", "--skipreview"],
}
_AUR_LINE = re.compile(r"^(\S+)\s+(\S+)\s+->\s+(\S+)")


class AurUpdater(BaseUpdater):
    """Updates AUR packages through yay or paru, as the invoking user.

    makepkg refuses to run as root, so the updater is unavailable when the
    commands would execute as root.
    """

    def __init__(self) -> None:
        super().__init__()
        self._exec_kwargs, self._search_path = user_exec_context()
        self._helper: str | None = None
        self._helper_path = ""

    @property
    def name(self) -> str:
        return f"AUR ({self._helper})" if self._helper else "AUR"

    @property
    def _logger_name(self) -> str:
        return "aur"

    async def check_available(self) -> bool:
        """Available with yay or paru and pacman present, never as root."""
        if runs_as_root(self._exec_kwargs):
            return False
        if shutil.which("pacman", path=self._search_path) is None:
            return False
        for helper in _HELPERS:
            resolved = shutil.which(helper, path=self._search_path)
            if resolved:
                self._helper = helper
                self._helper_path = resolved
                return True
        return False

    async def check_updates(self) -> list[Package]:
        """List pending AUR updates from ``<helper> -Qua``."""
        if not self._helper_path:
            return []
        _, stdout = await capture_output([self._helper_path, "-Qua"], self._exec_kwargs)
        packages = []
        for line in stdout.splitlines():
            match = _AUR_LINE.match(line.strip())
            if match:
                packages.append(Package(match[1], match[2], match[3]))
        return packages

    async def _do_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run ``<helper> -Sua --noconfirm`` when AUR updates are pending."""
        pending = await self.check_updates()
        if not pending or self._helper is None:
            return [], True, ""

        report(
            UpdateProgress(
                phase=UpdatePhase.INSTALLING,
                progress=0.5,
                current_package=self._helper,
            )
        )
        code, last_line = await run_logged(
            self,
            [self._helper_path, *_UPGRADE_FLAGS[self._helper]],
            self._exec_kwargs,
        )
        if code != 0:
            return [], False, last_line or f"{self._helper} failed"
        return pending, True, ""

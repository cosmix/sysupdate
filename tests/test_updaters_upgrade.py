"""Tests for _do_upgrade / run_update(dry_run=False) paths of Flatpak, Snap, and Pacman updaters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sysupdate.updaters.base import UpdatePhase, UpdateProgress
from sysupdate.updaters.flatpak import FlatpakUpdater
from sysupdate.updaters.pacman import PacmanUpdater
from sysupdate.updaters.snap import SnapUpdater


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_process(
    stdout_chunks: list[bytes],
    returncode: int = 0,
) -> AsyncMock:
    """Create a mock subprocess with streaming stdout.

    ``stdout_chunks`` should end with ``b""`` to signal EOF.
    ``read`` is called by ``read_process_lines`` with a 1024 chunk size.
    """
    proc = AsyncMock()
    proc.returncode = returncode
    proc.stdout = AsyncMock()
    proc.stdout.read = AsyncMock(side_effect=stdout_chunks)
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc


def _make_communicate_process(
    stdout_bytes: bytes,
    returncode: int = 0,
) -> AsyncMock:
    """Create a mock subprocess that returns output via ``communicate()``."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout_bytes, b""))
    proc.wait = AsyncMock()
    return proc


def _collect_phases(updates: list[UpdateProgress]) -> list[UpdatePhase]:
    """Extract unique phases in order of first appearance."""
    seen: set[UpdatePhase] = set()
    ordered: list[UpdatePhase] = []
    for u in updates:
        if u.phase not in seen:
            seen.add(u.phase)
            ordered.append(u.phase)
    return ordered


# ---------------------------------------------------------------------------
# FlatpakUpdater tests
# ---------------------------------------------------------------------------

class TestFlatpakUpgrade:
    """Tests for FlatpakUpdater._do_upgrade / run_update(dry_run=False)."""

    @pytest.fixture
    def updater(self) -> FlatpakUpdater:
        return FlatpakUpdater()

    async def test_upgrade_with_updates(self, updater: FlatpakUpdater):
        """Successful upgrade with two apps produces correct result and phases."""
        flatpak_output = (
            "Looking for updates\u2026\n"
            "\n"
            "        ID                              Branch    Op\n"
            " 1.     org.mozilla.firefox             stable    u\n"
            " 2.     org.gimp.GIMP                   stable    u\n"
            "\n"
            "Downloading org.mozilla.firefox... 50%\n"
            "Downloading org.mozilla.firefox... 100%\n"
            "Installing org.mozilla.firefox\n"
            "Downloading org.gimp.GIMP... 50%\n"
            "Downloading org.gimp.GIMP... 100%\n"
            "Installing org.gimp.GIMP\n"
            "Updates complete.\n"
        )
        mock_proc = _make_mock_process(
            [flatpak_output.encode(), b""],
            returncode=0,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is True
        assert len(result.packages) >= 2
        pkg_names = {p.name for p in result.packages}
        assert "firefox" in pkg_names
        assert "GIMP" in pkg_names

        phases = _collect_phases(progress_updates)
        assert UpdatePhase.CHECKING in phases
        assert UpdatePhase.DOWNLOADING in phases
        assert UpdatePhase.INSTALLING in phases
        assert UpdatePhase.COMPLETE in phases

    async def test_upgrade_no_updates(self, updater: FlatpakUpdater):
        """When Flatpak reports nothing to do, result is success with no packages."""
        flatpak_output = (
            "Looking for updates\u2026\n"
            "Nothing to do.\n"
        )
        mock_proc = _make_mock_process(
            [flatpak_output.encode(), b""],
            returncode=0,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is True
        assert len(result.packages) == 0

    async def test_upgrade_subprocess_failure(self, updater: FlatpakUpdater):
        """Non-zero exit code from flatpak results in error."""
        flatpak_output = (
            "Looking for updates\u2026\n"
            "error: Unable to update: network unavailable\n"
        )
        mock_proc = _make_mock_process(
            [flatpak_output.encode(), b""],
            returncode=1,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is False
        assert result.error_message != ""
        assert any(p.phase == UpdatePhase.ERROR for p in progress_updates)


# ---------------------------------------------------------------------------
# SnapUpdater tests
# ---------------------------------------------------------------------------

class TestSnapUpgrade:
    """Tests for SnapUpdater._do_upgrade / run_update(dry_run=False)."""

    @pytest.fixture
    def updater(self) -> SnapUpdater:
        return SnapUpdater()

    async def test_upgrade_with_updates(self, updater: SnapUpdater):
        """Successful snap refresh with two snaps populates packages and reports phases."""
        # check_updates: snap refresh --list
        check_output = (
            b"Name                  Version    Rev    Size    Publisher        Notes\n"
            b"firefox               125.0.1    4432   279MB   mozilla          -\n"
            b"thunderbird           115.7.0    432    180MB   canonical        -\n"
        )
        mock_check_proc = _make_communicate_process(check_output, returncode=0)

        # _get_current_versions: snap list
        list_output = (
            b"Name                  Version    Rev    Tracking         Publisher   Notes\n"
            b"firefox               124.0.2    4336   latest/stable    mozilla     -\n"
            b"thunderbird           115.6.0    430    latest/stable    canonical   -\n"
        )
        mock_list_proc = _make_communicate_process(list_output, returncode=0)

        # snap refresh (streaming)
        refresh_output = (
            "firefox (stable) 125.0.1 from Mozilla refreshed\n"
            "thunderbird (stable) 115.7.0 from Canonical refreshed\n"
        )
        mock_refresh_proc = _make_mock_process(
            [refresh_output.encode(), b""],
            returncode=0,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                mock_check_proc,    # check_updates() inside _do_upgrade
                mock_list_proc,     # _get_current_versions()
                mock_refresh_proc,  # snap refresh
            ]
            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is True
        assert len(result.packages) == 2
        pkg_names = {p.name for p in result.packages}
        assert "firefox" in pkg_names
        assert "thunderbird" in pkg_names

        # Verify version tracking
        firefox = next(p for p in result.packages if p.name == "firefox")
        assert firefox.old_version == "124.0.2"
        assert firefox.new_version == "125.0.1"

        phases = _collect_phases(progress_updates)
        assert UpdatePhase.CHECKING in phases
        assert UpdatePhase.INSTALLING in phases
        assert UpdatePhase.COMPLETE in phases

    async def test_upgrade_no_updates(self, updater: SnapUpdater):
        """When check_updates returns nothing, snap refresh is not called."""
        # check_updates: snap refresh --list returns "All snaps up to date"
        check_output = b"All snaps up to date.\n"
        mock_check_proc = _make_communicate_process(check_output, returncode=0)

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [mock_check_proc]
            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is True
        assert len(result.packages) == 0
        # Only one subprocess call (check_updates); refresh was never started
        assert mock_exec.call_count == 1

    async def test_upgrade_subprocess_failure(self, updater: SnapUpdater):
        """Non-zero exit code from snap refresh results in error."""
        # check_updates: snap refresh --list
        check_output = (
            b"Name       Version    Rev    Size    Publisher   Notes\n"
            b"firefox    125.0.1    4432   279MB   mozilla     -\n"
        )
        mock_check_proc = _make_communicate_process(check_output, returncode=0)

        # _get_current_versions: snap list
        list_output = (
            b"Name       Version    Rev    Tracking         Publisher   Notes\n"
            b"firefox    124.0.2    4336   latest/stable    mozilla     -\n"
        )
        mock_list_proc = _make_communicate_process(list_output, returncode=0)

        # snap refresh fails
        refresh_output = b"error: cannot refresh \"firefox\": snap is running\n"
        mock_refresh_proc = _make_mock_process(
            [refresh_output, b""],
            returncode=1,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                mock_check_proc,
                mock_list_proc,
                mock_refresh_proc,
            ]
            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is False
        assert result.error_message != ""
        assert any(p.phase == UpdatePhase.ERROR for p in progress_updates)


# ---------------------------------------------------------------------------
# PacmanUpdater tests
# ---------------------------------------------------------------------------

class TestPacmanUpgrade:
    """Tests for PacmanUpdater._do_upgrade / run_update(dry_run=False)."""

    @pytest.fixture
    def updater(self) -> PacmanUpdater:
        return PacmanUpdater()

    async def test_upgrade_with_updates(self, updater: PacmanUpdater):
        """Successful pacman -Syu with two packages produces correct result."""
        # check_updates: checkupdates
        checkupdates_output = (
            b"linux 6.1.0-1 -> 6.1.1-1\n"
            b"mesa 23.0-1 -> 23.1-1\n"
        )
        mock_check_proc = _make_communicate_process(checkupdates_output, returncode=0)

        # pacman -Syu streaming output
        syu_output = (
            ":: Synchronizing package databases...\n"
            " core is up to date\n"
            " extra is up to date\n"
            ":: Starting full system upgrade...\n"
            "resolving dependencies...\n"
            "looking for conflicting packages...\n"
            "\n"
            "Packages (2) linux-6.1.1-1  mesa-23.1-1\n"
            "\n"
            ":: Proceed with installation? [Y/n]\n"
            ":: Retrieving packages...\n"
            " downloading linux-6.1.1-1\n"
            " downloading mesa-23.1-1\n"
            "(1/2) upgrading linux\n"
            "(2/2) upgrading mesa\n"
        )
        mock_syu_proc = _make_mock_process(
            [syu_output.encode(), b""],
            returncode=0,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("sysupdate.updaters.pacman.command_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = [
                    mock_check_proc,  # check_updates (checkupdates)
                    mock_syu_proc,    # sudo pacman -Syu
                ]
                with patch.object(updater, "_logger", MagicMock()):
                    result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is True
        assert len(result.packages) == 2
        pkg_names = {p.name for p in result.packages}
        assert "linux" in pkg_names
        assert "mesa" in pkg_names

        # Verify old versions from checkupdates were preserved
        linux_pkg = next(p for p in result.packages if p.name == "linux")
        assert linux_pkg.old_version == "6.1.0-1"
        assert linux_pkg.new_version == "6.1.1-1"

        phases = _collect_phases(progress_updates)
        assert UpdatePhase.CHECKING in phases
        assert UpdatePhase.DOWNLOADING in phases
        assert UpdatePhase.INSTALLING in phases
        assert UpdatePhase.COMPLETE in phases

    async def test_upgrade_no_updates(self, updater: PacmanUpdater):
        """When check_updates returns nothing, pacman -Syu is not called."""
        # checkupdates returns exit code 2 (no updates) with empty output
        mock_check_proc = _make_communicate_process(b"", returncode=2)

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("sysupdate.updaters.pacman.command_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = [mock_check_proc]
                with patch.object(updater, "_logger", MagicMock()):
                    result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is True
        assert len(result.packages) == 0
        # Only check_updates was called; pacman -Syu was skipped
        assert mock_exec.call_count == 1

    async def test_upgrade_subprocess_failure(self, updater: PacmanUpdater):
        """Non-zero exit code from pacman -Syu results in error."""
        # check_updates: checkupdates
        checkupdates_output = b"linux 6.1.0-1 -> 6.1.1-1\n"
        mock_check_proc = _make_communicate_process(checkupdates_output, returncode=0)

        # pacman -Syu fails
        syu_output = (
            ":: Synchronizing package databases...\n"
            "error: failed to synchronize all databases (unable to lock database)\n"
        )
        mock_syu_proc = _make_mock_process(
            [syu_output.encode(), b""],
            returncode=1,
        )

        progress_updates: list[UpdateProgress] = []

        def track(p: UpdateProgress) -> None:
            progress_updates.append(p)

        with patch("sysupdate.updaters.pacman.command_available", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = [
                    mock_check_proc,
                    mock_syu_proc,
                ]
                with patch.object(updater, "_logger", MagicMock()):
                    result = await updater.run_update(callback=track, dry_run=False)

        assert result.success is False
        assert "error" in result.error_message.lower() or "failed" in result.error_message.lower()
        assert any(p.phase == UpdatePhase.ERROR for p in progress_updates)

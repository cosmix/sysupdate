"""Tests for package updater backends."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.updaters.base import Package, UpdateProgress, UpdateResult, UpdatePhase
from sysupdate.updaters.apt import AptUpdater
from sysupdate.updaters.flatpak import FlatpakUpdater
from sysupdate.updaters.snap import SnapUpdater
from sysupdate.updaters.pacman import PacmanUpdater


class TestPackage:
    """Tests for Package dataclass."""

    def test_package_str_with_versions(self):
        """Test string representation with versions."""
        pkg = Package(
            name="libssl3",
            old_version="3.0.11",
            new_version="3.0.13",
        )
        assert str(pkg) == "libssl3: 3.0.11 → 3.0.13"

    def test_package_str_without_versions(self):
        """Test string representation without versions."""
        pkg = Package(name="firefox")
        assert str(pkg) == "firefox"

    def test_package_defaults(self):
        """Test default values."""
        pkg = Package(name="test")
        assert pkg.old_version == ""
        assert pkg.new_version == ""
        assert pkg.size == ""
        assert pkg.status == "pending"


class TestUpdateProgress:
    """Tests for UpdateProgress dataclass."""

    def test_defaults(self):
        """Test default values."""
        progress = UpdateProgress()
        assert progress.phase == UpdatePhase.IDLE
        assert progress.progress == 0.0
        assert progress.total_packages == 0
        assert progress.completed_packages == 0
        assert progress.current_package == ""


class TestUpdateResult:
    """Tests for UpdateResult dataclass."""

    def test_basic_fields(self):
        """Test basic UpdateResult fields."""
        from datetime import datetime

        result = UpdateResult(
            success=True,
            packages=[
                Package(name="pkg1", status="complete"),
                Package(name="pkg2", status="complete"),
                Package(name="pkg3", status="pending"),
            ],
        )
        assert result.success is True
        assert len(result.packages) == 3
        assert result.error_message == ""
        assert isinstance(result.start_time, datetime)


class TestAptUpdater:
    """Tests for AptUpdater."""

    @pytest.fixture
    def updater(self):
        """Create an AptUpdater instance."""
        return AptUpdater()

    @pytest.mark.asyncio
    async def test_check_available_true(self, updater):
        """Test check_available when apt exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_available_false(self, updater):
        """Test check_available when apt doesn't exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_available_exception(self, updater):
        """Test check_available handles exceptions."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = Exception("Command not found")

            result = await updater.check_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_updates(self, updater):
        """Test check_updates returns package list."""
        apt_list_output = b"""
libssl3/jammy-updates 3.0.13-0ubuntu1 amd64 [upgradable from: 3.0.11-0ubuntu1]
openssl/jammy-updates 3.0.13-0ubuntu1 amd64 [upgradable from: 3.0.11-0ubuntu1]
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock apt update
            mock_update = AsyncMock()
            mock_update.returncode = 0
            mock_update.communicate = AsyncMock(return_value=(b"", b""))

            # Mock apt list
            mock_list = AsyncMock()
            mock_list.returncode = 0
            mock_list.communicate = AsyncMock(return_value=(apt_list_output, b""))

            mock_exec.side_effect = [mock_update, mock_list]

            packages = await updater.check_updates()

            assert len(packages) == 2
            assert any(p.name == "libssl3" for p in packages)
            assert any(p.name == "openssl" for p in packages)

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, updater):
        """Test dry run doesn't actually install."""
        apt_list_output = b"libssl3/jammy-updates 3.0.13 amd64 [upgradable from: 3.0.11]\n"

        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock apt update
            mock_update = AsyncMock()
            mock_update.returncode = 0
            mock_update.stdout = AsyncMock()
            mock_update.stdout.readline = AsyncMock(return_value=b"")
            mock_update.wait = AsyncMock()

            # Mock apt list
            mock_list = AsyncMock()
            mock_list.returncode = 0
            mock_list.communicate = AsyncMock(return_value=(apt_list_output, b""))

            mock_exec.side_effect = [mock_update, mock_list]

            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track_progress, dry_run=True)

            assert result.success is True
            # Should reach COMPLETE phase
            assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)


class TestFlatpakUpdater:
    """Tests for FlatpakUpdater."""

    @pytest.fixture
    def updater(self):
        """Create a FlatpakUpdater instance."""
        return FlatpakUpdater()

    @pytest.mark.asyncio
    async def test_check_available_true(self, updater):
        """Test check_available when flatpak exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_available_false(self, updater):
        """Test check_available when flatpak doesn't exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_updates(self, updater):
        """Test check_updates returns app list."""
        flatpak_list_output = b"""org.mozilla.firefox\tstable\t
org.gimp.GIMP\tstable\t
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(flatpak_list_output, b""))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 2
            assert any(p.name == "firefox" for p in packages)
            assert any(p.name == "GIMP" for p in packages)

    @pytest.mark.asyncio
    async def test_check_updates_filters_runtimes(self, updater):
        """Test that runtimes and extensions are filtered."""
        flatpak_list_output = b"""org.mozilla.firefox\tstable\t
org.freedesktop.Platform\t23.08\t
org.gnome.Platform.Locale\t45\t
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(flatpak_list_output, b""))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 1
            assert packages[0].name == "firefox"

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, updater):
        """Test dry run doesn't actually update."""
        flatpak_list_output = b"org.mozilla.firefox\tstable\t\n"

        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(flatpak_list_output, b""))
            mock_exec.return_value = mock_proc

            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track_progress, dry_run=True)

            assert result.success is True
            assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)


class TestSnapUpdater:
    """Tests for SnapUpdater."""

    @pytest.fixture
    def updater(self):
        """Create a SnapUpdater instance."""
        return SnapUpdater()

    @pytest.mark.asyncio
    async def test_check_available_true(self, updater):
        """Test check_available when snap exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_available_false(self, updater):
        """Test check_available when snap doesn't exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_updates(self, updater):
        """Test check_updates parses snap refresh --list output."""
        snap_list_output = b"""Name                  Version    Rev    Size    Publisher        Notes
firefox               125.0.1    4432   279MB   mozilla          -
vlc                   3.0.20     3650   485MB   videolan         -
spotify               1.2.31     71     181MB   spotify          -
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(snap_list_output, b""))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 3
            assert any(p.name == "firefox" for p in packages)
            assert any(p.name == "vlc" for p in packages)
            assert any(p.name == "spotify" for p in packages)

    @pytest.mark.asyncio
    async def test_check_updates_filters_system_snaps(self, updater):
        """Test that system snaps are filtered out."""
        snap_list_output = b"""Name                  Version    Rev    Size    Publisher        Notes
firefox               125.0.1    4432   279MB   mozilla          -
snapd                 2.61.3     21184  32MB    canonical        snapd
core22                20240111   1122   64MB    canonical        base
gnome-42-2204         0+git.510  176    190MB   canonical        -
gtk-common-themes     0.1-81     1535   64MB    canonical        -
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(snap_list_output, b""))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            # Only firefox should remain, system snaps are filtered
            assert len(packages) == 1
            assert packages[0].name == "firefox"

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, updater):
        """Test dry run doesn't actually update."""
        snap_list_output = b"""Name      Version    Rev    Size    Publisher   Notes
firefox   125.0.1    4432   279MB   mozilla     -
"""

        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(snap_list_output, b""))
            mock_exec.return_value = mock_proc

            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track_progress, dry_run=True)

            assert result.success is True
            assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)

    @pytest.mark.asyncio
    async def test_no_updates_available(self, updater):
        """Test handling when no updates are available."""
        snap_list_output = b"All snaps up to date.\n"

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(snap_list_output, b""))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()
            assert len(packages) == 0


class TestPacmanUpdater:
    """Tests for PacmanUpdater."""

    @pytest.fixture
    def updater(self):
        """Create a PacmanUpdater instance."""
        return PacmanUpdater()

    @pytest.mark.asyncio
    async def test_check_available_true(self, updater):
        """Test check_available when pacman exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_available_false(self, updater):
        """Test check_available when pacman doesn't exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_updates_checkupdates_format(self, updater):
        """Test check_updates parses checkupdates output format."""
        checkupdates_output = b"""linux 6.7.0-1 -> 6.7.1-1
firefox 122.0-1 -> 122.0.1-1
python 3.11.7-1 -> 3.11.8-1
"""
        with patch("sysupdate.updaters.pacman.command_available") as mock_avail:
            mock_avail.return_value = True  # checkupdates is available

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(checkupdates_output, b""))
                mock_exec.return_value = mock_proc

                packages = await updater.check_updates()

                assert len(packages) == 3
                linux_pkg = next(p for p in packages if p.name == "linux")
                assert linux_pkg.old_version == "6.7.0-1"
                assert linux_pkg.new_version == "6.7.1-1"

    @pytest.mark.asyncio
    async def test_check_updates_pacman_qu_format(self, updater):
        """Test check_updates parses pacman -Qu output format."""
        pacman_output = b"""linux 6.7.1-1
firefox 122.0.1-1
"""
        with patch("sysupdate.updaters.pacman.command_available") as mock_avail:
            mock_avail.return_value = False  # checkupdates not available

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(pacman_output, b""))
                mock_exec.return_value = mock_proc

                packages = await updater.check_updates()

                assert len(packages) == 2
                assert any(p.name == "linux" and p.new_version == "6.7.1-1" for p in packages)

    @pytest.mark.asyncio
    async def test_check_updates_empty(self, updater):
        """Test handling when no updates are available."""
        with patch("sysupdate.updaters.pacman.command_available") as mock_avail:
            mock_avail.return_value = True

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 2  # checkupdates returns 2 when no updates
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = mock_proc

                packages = await updater.check_updates()
                assert len(packages) == 0

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, updater):
        """Test dry run doesn't actually update."""
        checkupdates_output = b"firefox 122.0-1 -> 122.0.1-1\n"

        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("sysupdate.updaters.pacman.command_available") as mock_avail:
            mock_avail.return_value = True

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(checkupdates_output, b""))
                mock_exec.return_value = mock_proc

                with patch.object(updater, "_logger", MagicMock()):
                    result = await updater.run_update(callback=track_progress, dry_run=True)

                assert result.success is True
                assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)

    @pytest.mark.asyncio
    async def test_get_current_versions(self, updater):
        """Test _get_current_versions parses pacman -Q output."""
        pacman_q_output = b"""linux 6.7.0-1
firefox 122.0-1
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(pacman_q_output, b""))
            mock_exec.return_value = mock_proc

            versions = await updater._get_current_versions(["linux", "firefox"])

            assert versions["linux"] == "6.7.0-1"
            assert versions["firefox"] == "122.0-1"

    def test_name_attribute(self, updater):
        """Test that the updater has correct name."""
        assert updater.name == "Pacman Packages"

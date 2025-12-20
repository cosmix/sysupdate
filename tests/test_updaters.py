"""Tests for package updater backends."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.updaters.base import Package, UpdateProgress, UpdateResult, UpdatePhase
from sysupdate.updaters.apt import AptUpdater
from sysupdate.updaters.flatpak import FlatpakUpdater


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

    def test_percentage_calculation(self):
        """Test percentage property."""
        progress = UpdateProgress(progress=0.75)
        assert progress.percentage == 75

    def test_percentage_zero(self):
        """Test percentage at zero."""
        progress = UpdateProgress(progress=0.0)
        assert progress.percentage == 0

    def test_percentage_full(self):
        """Test percentage at 100%."""
        progress = UpdateProgress(progress=1.0)
        assert progress.percentage == 100

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

    def test_package_count(self):
        """Test package_count property."""
        result = UpdateResult(
            success=True,
            packages=[
                Package(name="pkg1", status="complete"),
                Package(name="pkg2", status="complete"),
                Package(name="pkg3", status="pending"),
            ],
        )
        assert result.package_count == 2

    def test_duration(self):
        """Test duration calculation."""
        from datetime import datetime, timedelta

        start = datetime.now()
        end = start + timedelta(seconds=30)
        result = UpdateResult(
            success=True,
            start_time=start,
            end_time=end,
        )
        assert result.duration == 30.0

    def test_duration_no_end(self):
        """Test duration when not ended."""
        result = UpdateResult(success=True)
        assert result.duration == 0.0


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

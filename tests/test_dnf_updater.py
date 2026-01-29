"""Tests for DNF package manager updater."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.updaters.base import Package, UpdateProgress, UpdatePhase
from sysupdate.updaters.dnf import DnfUpdater


class TestDnfUpdater:
    """Tests for DnfUpdater."""

    @pytest.fixture
    def updater(self):
        """Create a DnfUpdater instance."""
        return DnfUpdater()

    @pytest.mark.asyncio
    async def test_check_available_dnf5_preferred(self, updater):
        """Test that dnf5 is preferred when both dnf and dnf5 exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()

            assert result is True
            assert updater._dnf_command == "dnf5"

    @pytest.mark.asyncio
    async def test_check_available_dnf4_fallback(self, updater):
        """Test fallback to dnf when dnf5 doesn't exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_dnf5_proc = AsyncMock()
            mock_dnf5_proc.returncode = 1
            mock_dnf5_proc.wait = AsyncMock()

            mock_dnf_proc = AsyncMock()
            mock_dnf_proc.returncode = 0
            mock_dnf_proc.wait = AsyncMock()

            mock_exec.side_effect = [mock_dnf5_proc, mock_dnf_proc]

            result = await updater.check_available()

            assert result is True
            assert updater._dnf_command == "dnf"

    @pytest.mark.asyncio
    async def test_check_available_none(self, updater):
        """Test returns False when neither dnf5 nor dnf exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.wait = AsyncMock()
            mock_exec.return_value = mock_proc

            result = await updater.check_available()

            assert result is False

    @pytest.mark.asyncio
    async def test_check_available_exception(self, updater):
        """Test check_available handles exceptions gracefully."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = Exception("Command not found")

            result = await updater.check_available()

            assert result is False

    @pytest.mark.asyncio
    async def test_check_updates_parses_output(self, updater, dnf_check_update_output):
        """Test that check_updates correctly parses dnf check-update output."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 100  # DNF returns 100 when updates available
            mock_proc.communicate = AsyncMock(
                return_value=(dnf_check_update_output.encode(), b"")
            )
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 4
            package_names = {p.name for p in packages}
            # DNF stores package names with architecture suffix
            assert "kernel.x86_64" in package_names
            assert "openssl-libs.x86_64" in package_names
            assert "python3.x86_64" in package_names
            assert "vim-minimal.x86_64" in package_names

    @pytest.mark.asyncio
    async def test_check_updates_extracts_versions(self, updater, dnf_check_update_output):
        """Test that package versions are correctly extracted."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 100
            mock_proc.communicate = AsyncMock(
                return_value=(dnf_check_update_output.encode(), b"")
            )
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            # Package names include architecture suffix
            kernel = next((p for p in packages if p.name == "kernel.x86_64"), None)
            assert kernel is not None
            assert kernel.new_version == "6.6.9-200.fc39"

    @pytest.mark.asyncio
    async def test_check_updates_empty(self, updater, dnf_no_updates_output):
        """Test handling when no updates are available."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0  # DNF returns 0 when no updates
            mock_proc.communicate = AsyncMock(
                return_value=(dnf_no_updates_output.encode(), b"")
            )
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 0

    @pytest.mark.asyncio
    async def test_check_updates_handles_error(self, updater):
        """Test that check_updates handles subprocess errors gracefully."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1  # Error exit code
            mock_proc.communicate = AsyncMock(return_value=(b"", b"Error"))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 0

    @pytest.mark.asyncio
    async def test_run_update_dry_run(self, updater, dnf_check_update_output):
        """Test dry run doesn't execute actual upgrade."""
        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 100
            mock_proc.communicate = AsyncMock(
                return_value=(dnf_check_update_output.encode(), b"")
            )
            mock_exec.return_value = mock_proc

            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track_progress, dry_run=True)

            assert result.success is True
            assert len(result.packages) == 4
            assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)
            # Verify subprocess was only called for check_updates, not upgrade
            # In dry run, only one subprocess call (check-update) should happen
            assert mock_exec.call_count == 1

    @pytest.mark.asyncio
    async def test_run_update_progress_callback(self, updater, dnf_upgrade_output):
        """Test that progress is reported through phases during update."""
        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock check_updates call (returns 100 with updates)
            mock_check_proc = AsyncMock()
            mock_check_proc.returncode = 100
            mock_check_proc.communicate = AsyncMock(return_value=(
                b"kernel.x86_64    6.6.9-200.fc39    updates\nopenssl-libs.x86_64    1.2.3    updates\n",
                b""
            ))

            # Mock list installed call for old versions
            mock_list_proc = AsyncMock()
            mock_list_proc.returncode = 0
            mock_list_proc.communicate = AsyncMock(return_value=(
                b"Installed Packages\nkernel.x86_64    6.5.0-100.fc39    @updates\nopenssl-libs.x86_64    1.2.0    @updates\n",
                b""
            ))

            # Mock upgrade process with streaming output
            mock_upgrade_proc = AsyncMock()
            mock_upgrade_proc.returncode = 0
            mock_upgrade_proc.stdout = AsyncMock()
            mock_upgrade_proc.stdout.read = AsyncMock(side_effect=[
                dnf_upgrade_output.encode(),
                b""  # EOF
            ])
            mock_upgrade_proc.wait = AsyncMock()

            mock_exec.side_effect = [
                mock_check_proc,  # First check in run_update
                mock_check_proc,  # Second check in _run_dnf_upgrade
                mock_list_proc,   # get_current_versions
                mock_upgrade_proc # actual upgrade
            ]

            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track_progress, dry_run=False)

            # Verify we got progress updates
            assert len(progress_updates) > 0
            # Verify we went through CHECKING phase
            assert any(p.phase == UpdatePhase.CHECKING for p in progress_updates)

    @pytest.mark.asyncio
    async def test_run_update_no_updates_available(self, updater, dnf_no_updates_output):
        """Test run_update when there are no updates available."""
        progress_updates = []

        def track_progress(progress: UpdateProgress):
            progress_updates.append(progress)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock check_updates returning no updates
            mock_check_proc = AsyncMock()
            mock_check_proc.returncode = 0  # No updates
            mock_check_proc.communicate = AsyncMock(
                return_value=(dnf_no_updates_output.encode(), b"")
            )
            mock_exec.return_value = mock_check_proc

            with patch.object(updater, "_logger", MagicMock()):
                result = await updater.run_update(callback=track_progress, dry_run=True)

            assert result.success is True
            assert len(result.packages) == 0
            # Should reach COMPLETE phase
            assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)

    @pytest.mark.asyncio
    async def test_name_attribute(self, updater):
        """Test that the updater has the correct name."""
        assert updater.name == "DNF Packages"

    @pytest.mark.asyncio
    async def test_get_current_versions(self, updater, dnf_list_installed_output):
        """Test _get_current_versions parses installed package versions."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(
                return_value=(dnf_list_installed_output.encode(), b"")
            )
            mock_exec.return_value = mock_proc

            versions = await updater._get_current_versions(
                ["kernel.x86_64", "openssl-libs.x86_64"]
            )

            assert "kernel.x86_64" in versions
            assert versions["kernel.x86_64"] == "6.5.0-100.fc39"

    @pytest.mark.asyncio
    async def test_check_updates_skips_metadata_lines(self, updater):
        """Test that metadata lines are skipped in check-update output."""
        output = """Last metadata expiration check: 0:15:42 ago on Thu Jan 11 10:00:00 2024.

kernel.x86_64    6.6.9-200.fc39    updates
"""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 100
            mock_proc.communicate = AsyncMock(return_value=(output.encode(), b""))
            mock_exec.return_value = mock_proc

            packages = await updater.check_updates()

            assert len(packages) == 1
            # Package name includes architecture suffix
            assert packages[0].name == "kernel.x86_64"

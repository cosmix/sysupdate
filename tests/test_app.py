"""Integration tests for the main application."""

import pytest
from unittest.mock import AsyncMock, patch
from rich.console import Console

from sysupdate.app import SysUpdateCLI
from sysupdate.updaters.base import UpdateResult, Package


class TestSysUpdateCLI:
    """Tests for SysUpdateCLI."""

    def test_instantiation(self):
        """Test CLI can be instantiated with default options."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            assert cli is not None
            assert cli.verbose is False
            assert cli.dry_run is False
            assert isinstance(cli.console, Console)
            assert cli._apt_updater is not None
            assert cli._flatpak_updater is not None

    def test_instantiation_with_options(self):
        """Test CLI with verbose and dry_run options."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI(verbose=True, dry_run=True)

            assert cli.verbose is True
            assert cli.dry_run is True

    def test_run_method_exists(self):
        """Test that run method exists and is callable."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            assert hasattr(cli, 'run')
            assert callable(cli.run)

    def test_run_handles_keyboard_interrupt(self):
        """Test that run handles KeyboardInterrupt gracefully."""
        def mock_asyncio_run(coro):
            """Mock asyncio.run that properly closes the coroutine before raising."""
            coro.close()
            raise KeyboardInterrupt

        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.asyncio.run', side_effect=mock_asyncio_run):
            cli = SysUpdateCLI()
            result = cli.run()

            assert result == 130  # Standard exit code for SIGINT

    def test_print_header(self):
        """Test that header is printed correctly."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Mock console.print to capture calls
            with patch.object(cli.console, 'print') as mock_print:
                cli._print_header()

                # Should have at least one print call for header
                assert mock_print.call_count >= 1
                # Check that header contains version info
                calls_str = str(mock_print.call_args_list)
                assert 'v2.' in calls_str  # Version number present


class TestCLIIntegration:
    """Integration tests for concurrent update execution."""

    @pytest.mark.asyncio
    async def test_run_updates_checks_availability(self):
        """Test that _run_updates checks if APT and Flatpak are available."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Mock check_available for both updaters
            cli._apt_updater.check_available = AsyncMock(return_value=False)
            cli._flatpak_updater.check_available = AsyncMock(return_value=False)

            result = await cli._run_updates()

            # Should call check_available on both
            cli._apt_updater.check_available.assert_called_once()
            cli._flatpak_updater.check_available.assert_called_once()

            # Should return success even if nothing to update
            assert result == 0

    @pytest.mark.asyncio
    async def test_run_updates_apt_only(self):
        """Test updates when only APT is available."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Mock APT available, Flatpak not
            cli._apt_updater.check_available = AsyncMock(return_value=True)
            cli._flatpak_updater.check_available = AsyncMock(return_value=False)

            # Mock APT update result
            apt_packages = [
                Package(name="package1", old_version="1.0", new_version="2.0"),
                Package(name="package2", old_version="1.5", new_version="1.6"),
            ]
            cli._apt_updater.run_update = AsyncMock(
                return_value=UpdateResult(success=True, packages=apt_packages)
            )

            result = await cli._run_updates()

            assert result == 0
            cli._apt_updater.run_update.assert_called_once()
            cli._flatpak_updater.check_available.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_flatpak_only(self):
        """Test updates when only Flatpak is available."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Mock Flatpak available, APT not
            cli._apt_updater.check_available = AsyncMock(return_value=False)
            cli._flatpak_updater.check_available = AsyncMock(return_value=True)

            # Mock Flatpak update result
            flatpak_packages = [
                Package(name="org.example.App"),
            ]
            cli._flatpak_updater.run_update = AsyncMock(
                return_value=UpdateResult(success=True, packages=flatpak_packages)
            )

            result = await cli._run_updates()

            assert result == 0
            cli._apt_updater.check_available.assert_called_once()
            cli._flatpak_updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_concurrent_execution(self):
        """Test that APT and Flatpak updates run concurrently."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Both available
            cli._apt_updater.check_available = AsyncMock(return_value=True)
            cli._flatpak_updater.check_available = AsyncMock(return_value=True)

            # Mock successful updates
            apt_packages = [Package(name="apt-pkg")]
            flatpak_packages = [Package(name="flatpak-app")]

            cli._apt_updater.run_update = AsyncMock(
                return_value=UpdateResult(success=True, packages=apt_packages)
            )
            cli._flatpak_updater.run_update = AsyncMock(
                return_value=UpdateResult(success=True, packages=flatpak_packages)
            )

            result = await cli._run_updates()

            assert result == 0
            # Both updaters should be called
            cli._apt_updater.run_update.assert_called_once()
            cli._flatpak_updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_handles_exceptions(self):
        """Test that exceptions in one updater don't stop the other."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Both available
            cli._apt_updater.check_available = AsyncMock(return_value=True)
            cli._flatpak_updater.check_available = AsyncMock(return_value=True)

            # APT raises exception, Flatpak succeeds
            cli._apt_updater.run_update = AsyncMock(
                side_effect=RuntimeError("APT failed")
            )
            flatpak_packages = [Package(name="flatpak-app")]
            cli._flatpak_updater.run_update = AsyncMock(
                return_value=UpdateResult(success=True, packages=flatpak_packages)
            )

            result = await cli._run_updates()

            # Should still complete and return success
            assert result == 0
            cli._apt_updater.run_update.assert_called_once()
            cli._flatpak_updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_passes_dry_run(self):
        """Test that dry_run flag is passed to updaters."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI(dry_run=True)

            cli._apt_updater.check_available = AsyncMock(return_value=True)
            cli._flatpak_updater.check_available = AsyncMock(return_value=False)

            cli._apt_updater.run_update = AsyncMock(
                return_value=UpdateResult(success=True, packages=[])
            )

            await cli._run_updates()

            # Check dry_run was passed
            cli._apt_updater.run_update.assert_called_once()
            call_args = cli._apt_updater.run_update.call_args
            assert call_args.kwargs['dry_run'] is True


class TestPrintSummary:
    """Tests for summary output."""

    def test_print_summary_no_updates(self):
        """Test summary when no packages were updated."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary([], [], [])

                # Should indicate system is up to date
                calls_str = str(mock_print.call_args_list)
                assert 'up to date' in calls_str.lower()

    def test_print_summary_apt_only(self):
        """Test summary with APT packages only."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            apt_packages = [
                Package(name="pkg1", old_version="1.0", new_version="2.0"),
                Package(name="pkg2", old_version="1.5", new_version="1.6"),
            ]

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(apt_packages, [], [])

                calls_str = str(mock_print.call_args_list)
                assert '2' in calls_str  # 2 packages
                assert 'APT' in calls_str
                # Check that a Table object was printed (for package details)
                assert 'Table object' in calls_str

    def test_print_summary_flatpak_only(self):
        """Test summary with Flatpak packages only."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            flatpak_packages = [
                Package(name="org.example.App1"),
                Package(name="org.example.App2"),
            ]

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary([], flatpak_packages, [])

                calls_str = str(mock_print.call_args_list)
                assert '2' in calls_str  # 2 packages
                assert 'Flatpak' in calls_str

    def test_print_summary_both(self):
        """Test summary with both APT and Flatpak packages."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            apt_packages = [Package(name="apt-pkg")]
            flatpak_packages = [Package(name="flatpak-app")]

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(apt_packages, flatpak_packages, [])

                calls_str = str(mock_print.call_args_list)
                assert '2' in calls_str  # Total 2 packages
                assert 'APT' in calls_str
                assert 'Flatpak' in calls_str

    def test_print_summary_shows_all_packages(self):
        """Test that summary shows all packages without truncation."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            # Create 20 APT packages
            apt_packages = [
                Package(name=f"pkg{i}", old_version="1.0", new_version="2.0")
                for i in range(20)
            ]

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(apt_packages, [], [])

                calls_str = str(mock_print.call_args_list)
                # Should NOT show "and X more" message - all packages displayed
                assert 'more' not in calls_str.lower()
                assert '20' in calls_str  # Count shown in header

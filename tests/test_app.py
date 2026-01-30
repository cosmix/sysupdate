"""Integration tests for the main application."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from rich.console import Console

from sysupdate.app import SysUpdateCLI, UpdaterConfig
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
            assert cli._updaters is not None
            assert len(cli._updaters) == 5  # APT, Flatpak, Snap, DNF, Pacman

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

    def test_updater_configs(self):
        """Test that updater configs have correct labels."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            labels = [cfg.label for cfg in cli._updaters]
            assert "APT" in labels
            assert "Flatpak" in labels
            assert "Snap" in labels
            assert "DNF" in labels
            assert "Pacman" in labels


class TestCLIIntegration:
    """Integration tests for concurrent update execution."""

    def _get_updater_by_label(self, cli: SysUpdateCLI, label: str) -> UpdaterConfig:
        """Helper to get an updater config by label."""
        for cfg in cli._updaters:
            if cfg.label == label:
                return cfg
        raise ValueError(f"No updater with label {label}")

    @pytest.mark.asyncio
    async def test_run_updates_checks_availability(self):
        """Test that _run_updates checks if all updaters are available."""
        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.Aria2Downloader') as mock_aria2:
            mock_aria2.return_value.check_available = AsyncMock(return_value=True)

            cli = SysUpdateCLI()

            # Mock all updaters as unavailable
            for cfg in cli._updaters:
                cfg.updater.check_available = AsyncMock(return_value=False)

            result = await cli._run_updates()

            # Should call check_available on all updaters
            for cfg in cli._updaters:
                cfg.updater.check_available.assert_called_once()

            # Should return success even if nothing to update
            assert result == 0

    @pytest.mark.asyncio
    async def test_run_updates_apt_only(self):
        """Test updates when only APT is available."""
        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.Aria2Downloader') as mock_aria2:
            mock_aria2.return_value.check_available = AsyncMock(return_value=True)

            cli = SysUpdateCLI()

            # Mock all updaters as unavailable except APT
            for cfg in cli._updaters:
                if cfg.label == "APT":
                    cfg.updater.check_available = AsyncMock(return_value=True)
                    apt_packages = [
                        Package(name="package1", old_version="1.0", new_version="2.0"),
                        Package(name="package2", old_version="1.5", new_version="1.6"),
                    ]
                    cfg.updater.run_update = AsyncMock(
                        return_value=UpdateResult(success=True, packages=apt_packages)
                    )
                else:
                    cfg.updater.check_available = AsyncMock(return_value=False)

            result = await cli._run_updates()

            assert result == 0
            apt_cfg = self._get_updater_by_label(cli, "APT")
            apt_cfg.updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_flatpak_only(self):
        """Test updates when only Flatpak is available."""
        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.Aria2Downloader') as mock_aria2:
            mock_aria2.return_value.check_available = AsyncMock(return_value=True)

            cli = SysUpdateCLI()

            # Mock all updaters as unavailable except Flatpak
            for cfg in cli._updaters:
                if cfg.label == "Flatpak":
                    cfg.updater.check_available = AsyncMock(return_value=True)
                    flatpak_packages = [Package(name="org.example.App")]
                    cfg.updater.run_update = AsyncMock(
                        return_value=UpdateResult(success=True, packages=flatpak_packages)
                    )
                else:
                    cfg.updater.check_available = AsyncMock(return_value=False)

            result = await cli._run_updates()

            assert result == 0
            flatpak_cfg = self._get_updater_by_label(cli, "Flatpak")
            flatpak_cfg.updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_concurrent_execution(self):
        """Test that APT and Flatpak updates run concurrently."""
        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.Aria2Downloader') as mock_aria2:
            mock_aria2.return_value.check_available = AsyncMock(return_value=True)

            cli = SysUpdateCLI()

            # Mock APT and Flatpak available, others not
            for cfg in cli._updaters:
                if cfg.label in ("APT", "Flatpak"):
                    cfg.updater.check_available = AsyncMock(return_value=True)
                    packages = [Package(name=f"{cfg.label.lower()}-pkg")]
                    cfg.updater.run_update = AsyncMock(
                        return_value=UpdateResult(success=True, packages=packages)
                    )
                else:
                    cfg.updater.check_available = AsyncMock(return_value=False)

            result = await cli._run_updates()

            assert result == 0
            # Both updaters should be called
            self._get_updater_by_label(cli, "APT").updater.run_update.assert_called_once()
            self._get_updater_by_label(cli, "Flatpak").updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_handles_exceptions(self):
        """Test that exceptions in one updater don't stop the other."""
        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.Aria2Downloader') as mock_aria2:
            mock_aria2.return_value.check_available = AsyncMock(return_value=True)

            cli = SysUpdateCLI()

            # Mock APT and Flatpak available, others not
            for cfg in cli._updaters:
                if cfg.label == "APT":
                    cfg.updater.check_available = AsyncMock(return_value=True)
                    cfg.updater.run_update = AsyncMock(side_effect=RuntimeError("APT failed"))
                elif cfg.label == "Flatpak":
                    cfg.updater.check_available = AsyncMock(return_value=True)
                    flatpak_packages = [Package(name="flatpak-app")]
                    cfg.updater.run_update = AsyncMock(
                        return_value=UpdateResult(success=True, packages=flatpak_packages)
                    )
                else:
                    cfg.updater.check_available = AsyncMock(return_value=False)

            result = await cli._run_updates()

            # Should still complete and return success
            assert result == 0
            self._get_updater_by_label(cli, "APT").updater.run_update.assert_called_once()
            self._get_updater_by_label(cli, "Flatpak").updater.run_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_updates_passes_dry_run(self):
        """Test that dry_run flag is passed to updaters."""
        with patch('sysupdate.app.setup_logging'), \
             patch('sysupdate.app.Aria2Downloader') as mock_aria2:
            mock_aria2.return_value.check_available = AsyncMock(return_value=True)

            cli = SysUpdateCLI(dry_run=True)

            # Mock only APT available
            for cfg in cli._updaters:
                if cfg.label == "APT":
                    cfg.updater.check_available = AsyncMock(return_value=True)
                    cfg.updater.run_update = AsyncMock(
                        return_value=UpdateResult(success=True, packages=[])
                    )
                else:
                    cfg.updater.check_available = AsyncMock(return_value=False)

            await cli._run_updates()

            # Check dry_run was passed
            apt_cfg = self._get_updater_by_label(cli, "APT")
            apt_cfg.updater.run_update.assert_called_once()
            call_args = apt_cfg.updater.run_update.call_args
            assert call_args.kwargs['dry_run'] is True


class TestPrintSummary:
    """Tests for summary output."""

    def test_print_summary_no_updates(self):
        """Test summary when no packages were updated."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            results = {"APT": [], "Flatpak": [], "Snap": [], "DNF": [], "Pacman": []}

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(results)

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
            results = {"APT": apt_packages, "Flatpak": [], "Snap": [], "DNF": [], "Pacman": []}

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(results)

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
            results = {"APT": [], "Flatpak": flatpak_packages, "Snap": [], "DNF": [], "Pacman": []}

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(results)

                calls_str = str(mock_print.call_args_list)
                assert '2' in calls_str  # 2 packages
                assert 'Flatpak' in calls_str

    def test_print_summary_both(self):
        """Test summary with both APT and Flatpak packages."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            apt_packages = [Package(name="apt-pkg")]
            flatpak_packages = [Package(name="flatpak-app")]
            results = {"APT": apt_packages, "Flatpak": flatpak_packages, "Snap": [], "DNF": [], "Pacman": []}

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(results)

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
            results = {"APT": apt_packages, "Flatpak": [], "Snap": [], "DNF": [], "Pacman": []}

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(results)

                calls_str = str(mock_print.call_args_list)
                # Should NOT show "and X more" message - all packages displayed
                assert 'more' not in calls_str.lower()
                assert '20' in calls_str  # Count shown in header

    def test_print_summary_all_managers(self):
        """Test summary with packages from all managers."""
        with patch('sysupdate.app.setup_logging'):
            cli = SysUpdateCLI()

            results = {
                "APT": [Package(name="apt-pkg", old_version="1.0", new_version="2.0")],
                "Flatpak": [Package(name="flatpak-app")],
                "Snap": [Package(name="snap-app", old_version="1.0", new_version="2.0")],
                "DNF": [Package(name="dnf-pkg", old_version="1.0", new_version="2.0")],
                "Pacman": [Package(name="pacman-pkg", old_version="1.0", new_version="2.0")],
            }

            with patch.object(cli.console, 'print') as mock_print:
                cli._print_summary(results)

                calls_str = str(mock_print.call_args_list)
                assert '5' in calls_str  # Total 5 packages
                assert 'APT' in calls_str
                assert 'Flatpak' in calls_str
                assert 'Snap' in calls_str
                assert 'DNF' in calls_str
                assert 'Pacman' in calls_str

"""Tests for sysupdate.__main__ entry point."""

import argparse
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sysupdate.__main__ import check_sudo, cmd_self_update, cmd_update, main


class TestCheckSudo:
    """Tests for check_sudo() function."""

    @patch("sysupdate.__main__.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        """check_sudo returns True when sudo -v exits with 0."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["sudo", "-v"], returncode=0
        )
        assert check_sudo() is True
        mock_run.assert_called_once_with(["sudo", "-v"], check=False)

    @patch("sysupdate.__main__.subprocess.run")
    def test_returns_false_on_nonzero_exit(self, mock_run):
        """check_sudo returns False when sudo -v exits with non-zero code."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["sudo", "-v"], returncode=1
        )
        assert check_sudo() is False

    @patch("sysupdate.__main__.subprocess.run")
    def test_returns_false_on_exit_code_130(self, mock_run):
        """check_sudo returns False when sudo is interrupted (e.g., Ctrl+C)."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["sudo", "-v"], returncode=130
        )
        assert check_sudo() is False

    @patch("sysupdate.__main__.subprocess.run")
    def test_returns_false_on_oserror(self, mock_run):
        """check_sudo returns False when sudo binary is not found."""
        mock_run.side_effect = OSError("No such file or directory: 'sudo'")
        assert check_sudo() is False

    @patch("sysupdate.__main__.subprocess.run")
    def test_returns_false_on_generic_exception(self, mock_run):
        """check_sudo returns False on any unexpected exception."""
        mock_run.side_effect = RuntimeError("unexpected error")
        assert check_sudo() is False


class TestCmdUpdate:
    """Tests for cmd_update() function."""

    @patch("sysupdate.__main__.check_sudo", return_value=True)
    @patch("sysupdate.app.SysUpdateCLI")
    def test_creates_cli_with_default_options(self, mock_cli_cls, mock_sudo):
        """cmd_update creates SysUpdateCLI with verbose=False, dry_run=False."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = 0
        mock_cli_cls.return_value = mock_instance

        args = argparse.Namespace(verbose=False, dry_run=False)
        result = cmd_update(args)

        mock_cli_cls.assert_called_once_with(verbose=False, dry_run=False)
        mock_instance.run.assert_called_once()
        assert result == 0

    @patch("sysupdate.__main__.check_sudo", return_value=True)
    @patch("sysupdate.app.SysUpdateCLI")
    def test_creates_cli_with_verbose(self, mock_cli_cls, mock_sudo):
        """cmd_update passes verbose=True through to SysUpdateCLI."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = 0
        mock_cli_cls.return_value = mock_instance

        args = argparse.Namespace(verbose=True, dry_run=False)
        cmd_update(args)

        mock_cli_cls.assert_called_once_with(verbose=True, dry_run=False)

    @patch("sysupdate.__main__.check_sudo", return_value=True)
    @patch("sysupdate.app.SysUpdateCLI")
    def test_creates_cli_with_dry_run(self, mock_cli_cls, mock_sudo):
        """cmd_update passes dry_run=True through to SysUpdateCLI."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = 0
        mock_cli_cls.return_value = mock_instance

        args = argparse.Namespace(verbose=False, dry_run=True)
        cmd_update(args)

        mock_cli_cls.assert_called_once_with(verbose=False, dry_run=True)
        # dry_run skips check_sudo
        mock_sudo.assert_not_called()

    @patch("sysupdate.__main__.check_sudo", return_value=False)
    def test_returns_1_when_sudo_fails(self, mock_sudo):
        """cmd_update returns 1 when sudo access cannot be obtained."""
        args = argparse.Namespace(verbose=False, dry_run=False)
        result = cmd_update(args)

        assert result == 1
        mock_sudo.assert_called_once()

    @patch("sysupdate.__main__.check_sudo", return_value=True)
    @patch("sysupdate.app.SysUpdateCLI")
    def test_propagates_run_return_code(self, mock_cli_cls, mock_sudo):
        """cmd_update propagates the return code from SysUpdateCLI.run()."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = 42
        mock_cli_cls.return_value = mock_instance

        args = argparse.Namespace(verbose=False, dry_run=False)
        result = cmd_update(args)

        assert result == 42

    @patch("sysupdate.__main__.check_sudo", return_value=True)
    @patch("sysupdate.app.SysUpdateCLI")
    def test_dry_run_skips_sudo(self, mock_cli_cls, mock_sudo):
        """cmd_update does not call check_sudo when dry_run is True."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = 0
        mock_cli_cls.return_value = mock_instance

        args = argparse.Namespace(verbose=False, dry_run=True)
        cmd_update(args)

        mock_sudo.assert_not_called()


class TestCmdSelfUpdate:
    """Tests for cmd_self_update() function."""

    @patch("sysupdate.__main__.asyncio.run", return_value=0)
    @patch("sysupdate.selfupdate.run_self_update")
    def test_delegates_to_run_self_update(self, mock_run_su, mock_asyncio_run):
        """cmd_self_update delegates to run_self_update via asyncio.run."""
        args = argparse.Namespace(check_only=False)
        mock_asyncio_run.return_value = 0
        result = cmd_self_update(args)

        # asyncio.run was called with the coroutine from run_self_update
        mock_asyncio_run.assert_called_once()
        mock_run_su.assert_called_once_with(check_only=False)
        assert result == 0

    @patch("sysupdate.__main__.asyncio.run", return_value=0)
    @patch("sysupdate.selfupdate.run_self_update")
    def test_passes_check_only_true(self, mock_run_su, mock_asyncio_run):
        """cmd_self_update passes check_only=True to run_self_update."""
        args = argparse.Namespace(check_only=True)
        cmd_self_update(args)

        mock_run_su.assert_called_once_with(check_only=True)

    @patch("sysupdate.__main__.asyncio.run", return_value=1)
    @patch("sysupdate.selfupdate.run_self_update")
    def test_propagates_error_return_code(self, mock_run_su, mock_asyncio_run):
        """cmd_self_update propagates non-zero return code."""
        args = argparse.Namespace(check_only=False)
        result = cmd_self_update(args)

        assert result == 1


class TestMain:
    """Tests for main() argument parsing and dispatch."""

    @patch("sysupdate.__main__.cmd_update", return_value=0)
    def test_default_command_runs_update(self, mock_cmd_update):
        """With no subcommand, main() dispatches to cmd_update."""
        with patch("sys.argv", ["sysupdate"]):
            result = main()

        mock_cmd_update.assert_called_once()
        args = mock_cmd_update.call_args[0][0]
        assert args.verbose is False
        assert args.dry_run is False
        assert args.command is None
        assert result == 0

    @patch("sysupdate.__main__.cmd_update", return_value=0)
    def test_verbose_flag(self, mock_cmd_update):
        """--verbose flag is parsed and passed through."""
        with patch("sys.argv", ["sysupdate", "--verbose"]):
            main()

        args = mock_cmd_update.call_args[0][0]
        assert args.verbose is True

    @patch("sysupdate.__main__.cmd_update", return_value=0)
    def test_verbose_short_flag(self, mock_cmd_update):
        """-v short flag is parsed as verbose."""
        with patch("sys.argv", ["sysupdate", "-v"]):
            main()

        args = mock_cmd_update.call_args[0][0]
        assert args.verbose is True

    @patch("sysupdate.__main__.cmd_update", return_value=0)
    def test_dry_run_flag(self, mock_cmd_update):
        """--dry-run flag is parsed and passed through."""
        with patch("sys.argv", ["sysupdate", "--dry-run"]):
            main()

        args = mock_cmd_update.call_args[0][0]
        assert args.dry_run is True

    @patch("sysupdate.__main__.cmd_update", return_value=0)
    def test_combined_flags(self, mock_cmd_update):
        """--verbose and --dry-run can be combined."""
        with patch("sys.argv", ["sysupdate", "--verbose", "--dry-run"]):
            main()

        args = mock_cmd_update.call_args[0][0]
        assert args.verbose is True
        assert args.dry_run is True

    def test_version_flag_exits(self):
        """--version prints version and exits with code 0."""
        with patch("sys.argv", ["sysupdate", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch("sysupdate.__main__.cmd_self_update", return_value=0)
    def test_self_update_subcommand(self, mock_cmd_self_update):
        """self-update subcommand dispatches to cmd_self_update."""
        with patch("sys.argv", ["sysupdate", "self-update"]):
            result = main()

        mock_cmd_self_update.assert_called_once()
        args = mock_cmd_self_update.call_args[0][0]
        assert args.command == "self-update"
        assert args.check_only is False
        assert result == 0

    @patch("sysupdate.__main__.cmd_self_update", return_value=0)
    def test_self_update_check_only(self, mock_cmd_self_update):
        """self-update --check-only is parsed correctly."""
        with patch("sys.argv", ["sysupdate", "self-update", "--check-only"]):
            main()

        args = mock_cmd_self_update.call_args[0][0]
        assert args.check_only is True

    @patch("sysupdate.__main__.cmd_update", return_value=1)
    def test_propagates_update_failure(self, mock_cmd_update):
        """main() propagates non-zero return code from cmd_update."""
        with patch("sys.argv", ["sysupdate"]):
            result = main()

        assert result == 1

    @patch("sysupdate.__main__.cmd_self_update", return_value=1)
    def test_propagates_self_update_failure(self, mock_cmd_self_update):
        """main() propagates non-zero return code from cmd_self_update."""
        with patch("sys.argv", ["sysupdate", "self-update"]):
            result = main()

        assert result == 1

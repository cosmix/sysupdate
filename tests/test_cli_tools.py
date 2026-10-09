"""Tests for the CLI tool updaters (Claude Code, Codex CLI)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sysupdate.updaters.cli_tools import CliToolUpdater


def _version_proc(text: str) -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(text.encode(), b""))
    return proc


def _update_proc(chunks: list[bytes], returncode: int = 0) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.stdout = AsyncMock()
    proc.stdout.read = AsyncMock(side_effect=chunks)
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc


@pytest.fixture
def updater() -> CliToolUpdater:
    with patch("os.geteuid", return_value=1000):
        return CliToolUpdater("claude", "Claude Code")


_PW = SimpleNamespace(
    pw_name="alice",
    pw_uid=1000,
    pw_gid=1001,
    pw_dir="/home/alice",
    pw_shell="/bin/zsh",
)


def _root_updater() -> CliToolUpdater:
    with (
        patch("os.geteuid", return_value=0),
        patch.dict("os.environ", {"SUDO_USER": "alice", "PATH": "/usr/bin"}),
        patch("pwd.getpwnam", return_value=_PW),
        patch("os.getgrouplist", return_value=[1001, 27]),
    ):
        return CliToolUpdater("claude", "Claude Code")


class TestCliToolUpdater:
    def test_names(self, updater):
        assert updater.name == "Claude Code"
        assert updater._logger_name == "claude"

    @pytest.mark.asyncio
    async def test_available(self, updater):
        with patch("shutil.which", return_value="/usr/bin/claude") as which:
            assert await updater.check_available() is True
        assert which.call_args.args == ("claude",)
        assert updater._executable == "/usr/bin/claude"

    @pytest.mark.asyncio
    async def test_unavailable(self, updater):
        with patch("shutil.which", return_value=None):
            assert await updater.check_available() is False

    @pytest.mark.asyncio
    async def test_non_root_passes_no_user_kwargs(self, updater):
        procs = [_version_proc("1.0.0\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as mock_exec:
            await updater._get_version()
        kwargs = mock_exec.call_args.kwargs
        for key in ("user", "group", "extra_groups", "cwd", "env"):
            assert key not in kwargs

    @pytest.mark.asyncio
    async def test_sudo_user_runs_as_that_user(self):
        updater = _root_updater()
        procs = [
            _version_proc("1.0.0\n"),
            _update_proc([b""]),
            _version_proc("1.0.0\n"),
        ]
        with (
            patch(
                "shutil.which", return_value="/home/alice/.local/bin/claude"
            ) as which,
            patch("asyncio.create_subprocess_exec", side_effect=procs) as mock_exec,
        ):
            assert await updater.check_available() is True
            await updater._do_upgrade(lambda _: None)
        assert which.call_args.kwargs["path"].startswith("/home/alice/.local/bin:")
        assert mock_exec.call_count == 3
        for call in mock_exec.call_args_list:
            assert call.args[0] == "/home/alice/.local/bin/claude"
            kwargs = call.kwargs
            assert kwargs["user"] == 1000
            assert kwargs["group"] == 1001
            assert kwargs["extra_groups"] == [1001, 27]
            assert kwargs["cwd"] == "/home/alice"
            assert kwargs["env"]["HOME"] == "/home/alice"
            assert kwargs["env"]["USER"] == "alice"
            assert kwargs["env"]["PATH"].startswith("/home/alice/.local/bin:")

    @pytest.mark.asyncio
    async def test_dry_run_reports_nothing(self, updater):
        assert await updater.check_updates() == []

    @pytest.mark.asyncio
    async def test_version_changed(self, updater):
        procs = [
            _version_proc("2.1.3 (Claude Code)\n"),
            _update_proc([b"Updating...\n", b"Done\n", b""]),
            _version_proc("2.1.4 (Claude Code)\n"),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            packages, success, error = await updater._do_upgrade(lambda _: None)
        assert success is True
        assert error == ""
        assert [(p.name, p.old_version, p.new_version) for p in packages] == [
            ("claude", "2.1.3", "2.1.4")
        ]

    @pytest.mark.asyncio
    async def test_version_unchanged(self):
        updater = CliToolUpdater("codex", "Codex CLI")
        procs = [
            _version_proc("codex-cli 0.40.0\n"),
            _update_proc([b"Already up to date\n", b""]),
            _version_proc("codex-cli 0.40.0\n"),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            packages, success, _ = await updater._do_upgrade(lambda _: None)
        assert packages == []
        assert success is True

    @pytest.mark.asyncio
    async def test_nonzero_exit_returns_last_line(self, updater):
        procs = [
            _version_proc("2.1.3 (Claude Code)\n"),
            _update_proc([b"starting\n", b"permission denied\n", b""], returncode=1),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            packages, success, error = await updater._do_upgrade(lambda _: None)
        assert packages == []
        assert success is False
        assert error == "permission denied"

    @pytest.mark.asyncio
    async def test_package_managed_install_is_not_a_failure(self):
        updater = CliToolUpdater("codex", "Codex CLI")
        procs = [
            _version_proc("codex-cli 0.40.0\n"),
            _update_proc(
                [
                    b"Error: Could not detect the Codex installation method. "
                    b"Please update manually: https://developers.openai.com/codex/cli/\n",
                    b"",
                ],
                returncode=1,
            ),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            packages, success, error = await updater._do_upgrade(lambda _: None)
        assert (packages, success, error) == ([], True, "")

    @pytest.mark.asyncio
    async def test_nonzero_exit_without_output(self, updater):
        procs = [
            _version_proc("2.1.3 (Claude Code)\n"),
            _update_proc([b""], returncode=2),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            _, success, error = await updater._do_upgrade(lambda _: None)
        assert success is False
        assert error == "claude update failed"

"""Tests for the CLI tool updaters (Claude Code, Codex CLI)."""

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
    return CliToolUpdater("claude", "Claude Code")


class TestCliToolUpdater:
    def test_names(self, updater):
        assert updater.name == "Claude Code"
        assert updater._logger_name == "claude"

    @pytest.mark.asyncio
    async def test_available(self, updater):
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.return_value = AsyncMock(wait=AsyncMock(return_value=0))
            mock_exec.return_value.returncode = 0
            assert await updater.check_available() is True

    @pytest.mark.asyncio
    async def test_unavailable(self, updater):
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError
            assert await updater.check_available() is False

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
    async def test_nonzero_exit_without_output(self, updater):
        procs = [
            _version_proc("2.1.3 (Claude Code)\n"),
            _update_proc([b""], returncode=2),
        ]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            _, success, error = await updater._do_upgrade(lambda _: None)
        assert success is False
        assert error == "claude update failed"

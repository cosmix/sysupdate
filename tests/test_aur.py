"""Tests for the AUR updater."""

from unittest.mock import patch

import pytest

from sysupdate.updaters.aur import AurUpdater
from tests.proc_helpers import ALICE, fake_proc

QUA = "paru-bin 2.0-1 -> 2.1-1\nyay 12.0-1 -> 12.1-1\nnoise line\n"


def _which(found: set[str]):
    return lambda cmd, path=None: f"/usr/bin/{cmd}" if cmd in found else None


@pytest.fixture
def updater() -> AurUpdater:
    with patch("os.geteuid", return_value=1000):
        return AurUpdater()


async def _available(updater: AurUpdater, found: set[str]) -> bool:
    with patch("shutil.which", side_effect=_which(found)):
        return await updater.check_available()


class TestAvailability:
    async def test_prefers_yay(self, updater):
        assert await _available(updater, {"pacman", "yay", "paru"}) is True
        assert updater._helper == "yay"
        assert updater.name == "AUR (yay)"

    async def test_falls_back_to_paru(self, updater):
        assert await _available(updater, {"pacman", "paru"}) is True
        assert updater._helper == "paru"

    async def test_no_helper(self, updater):
        assert await _available(updater, {"pacman"}) is False

    async def test_no_pacman(self, updater):
        assert await _available(updater, {"yay"}) is False

    async def test_root_without_sudo_user_unavailable(self):
        with (
            patch("os.geteuid", return_value=0),
            patch.dict("os.environ", {}, clear=False) as env,
        ):
            env.pop("SUDO_USER", None)
            root_updater = AurUpdater()
            assert await _available(root_updater, {"pacman", "yay"}) is False

    async def test_sudo_user_available(self):
        with (
            patch("os.geteuid", return_value=0),
            patch.dict("os.environ", {"SUDO_USER": "alice", "PATH": "/usr/bin"}),
            patch("pwd.getpwnam", return_value=ALICE),
            patch("os.getgrouplist", return_value=[1001]),
        ):
            sudo_updater = AurUpdater()
        assert await _available(sudo_updater, {"pacman", "yay"}) is True
        assert sudo_updater._exec_kwargs["user"] == 1000


class TestCheckUpdates:
    async def test_parses_lines(self, updater):
        await _available(updater, {"pacman", "yay"})
        with patch(
            "asyncio.create_subprocess_exec", return_value=fake_proc(QUA, 0)
        ) as ex:
            pkgs = await updater.check_updates()
        assert [(p.name, p.old_version, p.new_version) for p in pkgs] == [
            ("paru-bin", "2.0-1", "2.1-1"),
            ("yay", "12.0-1", "12.1-1"),
        ]
        assert ex.call_args.args == ("/usr/bin/yay", "-Qua")

    async def test_empty_output_exit_one(self, updater):
        await _available(updater, {"pacman", "yay"})
        with patch("asyncio.create_subprocess_exec", return_value=fake_proc("", 1)):
            assert await updater.check_updates() == []

    async def test_without_helper(self, updater):
        assert await updater.check_updates() == []


class TestUpgrade:
    async def test_nothing_pending_skips_upgrade(self, updater):
        await _available(updater, {"pacman", "yay"})
        with patch(
            "asyncio.create_subprocess_exec", return_value=fake_proc("", 1)
        ) as ex:
            result = await updater._do_upgrade(lambda _: None)
        assert result == ([], True, "")
        assert ex.call_count == 1

    async def test_yay_success(self, updater):
        await _available(updater, {"pacman", "yay"})
        procs = [fake_proc(QUA), fake_proc("building\nok\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            pkgs, ok, err = await updater._do_upgrade(lambda _: None)
        assert ok and err == "" and len(pkgs) == 2
        assert ex.call_args_list[1].args == ("/usr/bin/yay", "-Sua", "--noconfirm")

    async def test_paru_skips_review(self, updater):
        await _available(updater, {"pacman", "paru"})
        procs = [fake_proc(QUA), fake_proc("ok\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            await updater._do_upgrade(lambda _: None)
        assert ex.call_args_list[1].args == (
            "/usr/bin/paru",
            "-Sua",
            "--noconfirm",
            "--skipreview",
        )

    async def test_failure_reports_last_line(self, updater):
        await _available(updater, {"pacman", "yay"})
        procs = [fake_proc(QUA), fake_proc("building\nerror: build failed\n", 1)]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            pkgs, ok, err = await updater._do_upgrade(lambda _: None)
        assert (pkgs, ok, err) == ([], False, "error: build failed")

    async def test_commands_run_with_user_kwargs(self):
        with (
            patch("os.geteuid", return_value=0),
            patch.dict("os.environ", {"SUDO_USER": "alice", "PATH": "/usr/bin"}),
            patch("pwd.getpwnam", return_value=ALICE),
            patch("os.getgrouplist", return_value=[1001]),
        ):
            upd = AurUpdater()
        await _available(upd, {"pacman", "yay"})
        procs = [fake_proc(QUA), fake_proc("ok\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            await upd._do_upgrade(lambda _: None)
        for call in ex.call_args_list:
            assert call.kwargs["user"] == 1000
            assert call.kwargs["env"]["HOME"] == "/home/alice"

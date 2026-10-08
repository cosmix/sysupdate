"""Tests for the mise updater."""

import json
from unittest.mock import patch

import pytest

from sysupdate.updaters.mise import MiseUpdater
from tests.proc_helpers import ALICE, fake_proc

OUTDATED = json.dumps(
    {
        "node": {"name": "node", "current": "20.1.0", "latest": "20.2.0"},
        "python": {"name": "python", "latest": "3.13.1"},
        "broken": "not-a-dict",
    }
)


@pytest.fixture
def updater() -> MiseUpdater:
    with patch("os.geteuid", return_value=1000):
        return MiseUpdater()


class TestMise:
    async def test_available(self, updater):
        with patch("shutil.which", return_value="/usr/bin/mise"):
            assert await updater.check_available() is True
        assert updater._executable == "/usr/bin/mise"

    async def test_unavailable(self, updater):
        with patch("shutil.which", return_value=None):
            assert await updater.check_available() is False

    async def test_check_updates_parses_json(self, updater):
        with patch(
            "asyncio.create_subprocess_exec", return_value=fake_proc(OUTDATED)
        ) as ex:
            pkgs = await updater.check_updates()
        assert [(p.name, p.old_version, p.new_version) for p in pkgs] == [
            ("node", "20.1.0", "20.2.0"),
            ("python", "", "3.13.1"),
        ]
        assert ex.call_args.args == ("mise", "outdated", "--json")

    @pytest.mark.parametrize("text", ["{}", "not json", "[1, 2]", ""])
    async def test_check_updates_empty_or_garbage(self, updater, text):
        with patch("asyncio.create_subprocess_exec", return_value=fake_proc(text)):
            assert await updater.check_updates() == []

    async def test_check_updates_nonzero_exit(self, updater):
        with patch(
            "asyncio.create_subprocess_exec", return_value=fake_proc(OUTDATED, 1)
        ):
            assert await updater.check_updates() == []

    async def test_upgrade_nothing_pending(self, updater):
        with patch(
            "asyncio.create_subprocess_exec", return_value=fake_proc("{}")
        ) as ex:
            assert await updater._do_upgrade(lambda _: None) == ([], True, "")
        assert ex.call_count == 1

    async def test_upgrade_success(self, updater):
        procs = [fake_proc(OUTDATED), fake_proc("installed\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            pkgs, ok, err = await updater._do_upgrade(lambda _: None)
        assert ok and err == "" and [p.name for p in pkgs] == ["node", "python"]
        assert ex.call_args_list[1].args == ("mise", "upgrade")

    async def test_upgrade_failure(self, updater):
        procs = [fake_proc(OUTDATED), fake_proc("boom\n", 1)]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            assert await updater._do_upgrade(lambda _: None) == ([], False, "boom")

    async def test_runs_as_sudo_user(self):
        with (
            patch("os.geteuid", return_value=0),
            patch.dict("os.environ", {"SUDO_USER": "alice", "PATH": "/usr/bin"}),
            patch("pwd.getpwnam", return_value=ALICE),
            patch("os.getgrouplist", return_value=[1001]),
        ):
            upd = MiseUpdater()
        procs = [fake_proc(OUTDATED), fake_proc("ok\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            await upd._do_upgrade(lambda _: None)
        for call in ex.call_args_list:
            assert call.kwargs["user"] == 1000
            assert call.kwargs["cwd"] == "/home/alice"

"""Tests for Omarchy detection and the migration updater."""

import os
from unittest.mock import patch

import pytest

from sysupdate.updaters.omarchy import OmarchyMigrateUpdater
from sysupdate.utils.omarchy import find_omarchy_migrate, is_omarchy
from tests.proc_helpers import fake_proc


def _script(directory) -> str:
    bin_dir = directory / "bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "omarchy-migrate"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    return str(script)


class TestFindOmarchyMigrate:
    def test_found_on_path(self):
        with patch("shutil.which", return_value="/usr/bin/omarchy-migrate") as which:
            assert find_omarchy_migrate("/usr/bin", "/home/a") == (
                "/usr/bin/omarchy-migrate"
            )
        assert which.call_args.kwargs["path"] == "/usr/bin"

    def test_omarchy_path_env(self, tmp_path):
        script = _script(tmp_path / "custom")
        with (
            patch("shutil.which", return_value=None),
            patch.dict("os.environ", {"OMARCHY_PATH": str(tmp_path / "custom")}),
        ):
            assert find_omarchy_migrate(None, str(tmp_path / "nohome")) == script

    def test_home_fallback(self, tmp_path):
        script = _script(tmp_path / ".local/share/omarchy")
        with (
            patch("shutil.which", return_value=None),
            patch.dict("os.environ", {}, clear=False) as env,
        ):
            env.pop("OMARCHY_PATH", None)
            assert find_omarchy_migrate(None, str(tmp_path)) == script

    def test_non_executable_ignored(self, tmp_path):
        script = _script(tmp_path / ".local/share/omarchy")
        os.chmod(script, 0o644)
        with (
            patch("shutil.which", return_value=None),
            patch.dict("os.environ", {}, clear=False) as env,
        ):
            env.pop("OMARCHY_PATH", None)
            assert find_omarchy_migrate(None, str(tmp_path)) is None

    def test_is_omarchy(self):
        with patch("sysupdate.utils.omarchy.find_omarchy_migrate", return_value="/x"):
            assert is_omarchy() is True
        with patch("sysupdate.utils.omarchy.find_omarchy_migrate", return_value=None):
            assert is_omarchy() is False


@pytest.fixture
def updater() -> OmarchyMigrateUpdater:
    with patch("os.geteuid", return_value=1000):
        return OmarchyMigrateUpdater()


PENDING = "1700000000.sh\n1700000001.sh\n"


class TestOmarchyUpdater:
    async def test_available(self, updater):
        with patch(
            "sysupdate.updaters.omarchy.find_omarchy_migrate", return_value="/m"
        ):
            assert await updater.check_available() is True
        assert updater._executable == "/m"

    async def test_available_exposes_omarchy_bin(self, updater, tmp_path):
        (tmp_path / "bin").mkdir()
        (tmp_path / "migrations").mkdir()
        script = tmp_path / "bin" / "omarchy-migrate"
        script.touch()
        with (
            patch(
                "sysupdate.updaters.omarchy.find_omarchy_migrate",
                return_value=str(script),
            ),
            patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True),
        ):
            assert await updater.check_available() is True
        env = updater._exec_kwargs["env"]
        assert env["PATH"] == f"{tmp_path / 'bin'}:/usr/bin"
        assert env["OMARCHY_PATH"] == str(tmp_path)

    async def test_unavailable(self, updater):
        with patch(
            "sysupdate.updaters.omarchy.find_omarchy_migrate", return_value=None
        ):
            assert await updater.check_available() is False

    async def test_check_updates(self, updater):
        with patch(
            "asyncio.create_subprocess_exec", return_value=fake_proc(PENDING)
        ) as ex:
            pkgs = await updater.check_updates()
        assert [(p.name, p.old_version, p.new_version) for p in pkgs] == [
            ("1700000000", "pending", "applied"),
            ("1700000001", "pending", "applied"),
        ]
        assert ex.call_args.args[1:] == ("--pending",)

    async def test_pending_unsupported_returns_empty(self, updater):
        with patch("asyncio.create_subprocess_exec", return_value=fake_proc("", 1)):
            assert await updater.check_updates() == []
        assert updater._pending_supported is False

    async def test_nothing_pending_skips_run(self, updater):
        with patch("asyncio.create_subprocess_exec", return_value=fake_proc("")) as ex:
            assert await updater._do_upgrade(lambda _: None) == ([], True, "")
        assert ex.call_count == 1

    async def test_upgrade_success(self, updater):
        procs = [fake_proc(PENDING), fake_proc("migrated\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            pkgs, ok, err = await updater._do_upgrade(lambda _: None)
        assert ok and err == "" and len(pkgs) == 2
        assert ex.call_args_list[1].args == ("omarchy-migrate",)

    async def test_unsupported_pending_still_runs(self, updater):
        procs = [fake_proc("", 2), fake_proc("done\n")]
        with patch("asyncio.create_subprocess_exec", side_effect=procs) as ex:
            assert await updater._do_upgrade(lambda _: None) == ([], True, "")
        assert ex.call_count == 2

    async def test_failure(self, updater):
        procs = [fake_proc(PENDING), fake_proc("migration failed\n", 1)]
        with patch("asyncio.create_subprocess_exec", side_effect=procs):
            result = await updater._do_upgrade(lambda _: None)
        assert result == ([], False, "migration failed")

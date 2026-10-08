"""Tests for run ordering between updaters."""

import asyncio
from unittest.mock import AsyncMock, patch

from sysupdate.app import SysUpdateCLI, UpdaterConfig
from sysupdate.ordering import OrderGate
from sysupdate.updaters.base import Package, UpdateResult


class FakeUpdater:
    """Records start/end events in a shared log."""

    def __init__(self, label, log, *, delay=0.0, success=True, raises=False):
        self.name = label
        self._label = label
        self._log = log
        self._delay = delay
        self._success = success
        self._raises = raises

    async def check_available(self) -> bool:
        return True

    async def check_updates(self) -> list[Package]:
        return []

    async def run_update(self, callback=None, dry_run=False) -> UpdateResult:
        self._log.append(f"start:{self._label}")
        await asyncio.sleep(self._delay)
        self._log.append(f"end:{self._label}")
        if self._raises:
            raise RuntimeError("boom")
        return UpdateResult(
            success=self._success,
            packages=[Package(f"{self._label}-pkg")],
            error_message="" if self._success else "failed",
        )


def _cli(configs):
    with patch("sysupdate.app.setup_logging"):
        cli = SysUpdateCLI()
    cli._updaters = configs
    return cli


async def _run(cli):
    cli._print_summary = lambda *a, **k: captured.update(k, results=a[0])
    captured: dict = {}
    with patch("sysupdate.app.Aria2Downloader") as aria2:
        aria2.return_value.check_available = AsyncMock(return_value=True)
        code = await cli._run_updates()
    return code, captured


class TestOrderGate:
    async def test_unknown_predecessor_ignored(self):
        gate = OrderGate(["B"])
        assert await gate.wait_for(("A",)) is None

    async def test_failed_predecessor_gives_skip_message(self):
        gate = OrderGate(["A", "B"])
        gate.done("A", False)
        assert await gate.wait_for(("A",)) == "skipped: A update failed"


class TestAppOrdering:
    async def test_dependent_waits_for_predecessor(self):
        log: list[str] = []
        cli = _cli(
            [
                UpdaterConfig(FakeUpdater("Pacman", log, delay=0.05), "Pacman"),
                UpdaterConfig(FakeUpdater("AUR", log), "AUR", after=("Pacman",)),
            ]
        )
        code, _ = await _run(cli)
        assert code == 0
        assert log == ["start:Pacman", "end:Pacman", "start:AUR", "end:AUR"]

    async def test_chain_pacman_omarchy_aur(self):
        log: list[str] = []
        cli = _cli(
            [
                UpdaterConfig(
                    FakeUpdater("AUR", log), "AUR", after=("Pacman", "Omarchy")
                ),
                UpdaterConfig(
                    FakeUpdater("Omarchy", log, delay=0.02),
                    "Omarchy",
                    after=("Pacman",),
                ),
                UpdaterConfig(FakeUpdater("Pacman", log, delay=0.02), "Pacman"),
            ]
        )
        await _run(cli)
        starts = [e for e in log if e.startswith("start:")]
        assert starts == ["start:Pacman", "start:Omarchy", "start:AUR"]
        assert log.index("end:Pacman") < log.index("start:Omarchy")
        assert log.index("end:Omarchy") < log.index("start:AUR")

    async def test_failed_predecessor_skips_dependents(self):
        log: list[str] = []
        cli = _cli(
            [
                UpdaterConfig(FakeUpdater("Pacman", log, success=False), "Pacman"),
                UpdaterConfig(
                    FakeUpdater("Omarchy", log), "Omarchy", after=("Pacman",)
                ),
                UpdaterConfig(
                    FakeUpdater("AUR", log), "AUR", after=("Pacman", "Omarchy")
                ),
            ]
        )
        code, captured = await _run(cli)
        assert code == 1
        assert log == ["start:Pacman", "end:Pacman"]
        failures = dict(captured["failures"])
        assert failures["Omarchy"] == "skipped: Pacman update failed"
        assert failures["AUR"] == "skipped: Pacman update failed"

    async def test_raising_predecessor_skips_dependent(self):
        log: list[str] = []
        cli = _cli(
            [
                UpdaterConfig(FakeUpdater("Pacman", log, raises=True), "Pacman"),
                UpdaterConfig(FakeUpdater("AUR", log), "AUR", after=("Pacman",)),
            ]
        )
        code, captured = await _run(cli)
        assert code == 1
        assert "start:AUR" not in log
        assert dict(captured["failures"])["AUR"] == "skipped: Pacman update failed"

    async def test_unavailable_predecessor_does_not_block(self):
        log: list[str] = []
        pacman = FakeUpdater("Pacman", log)
        pacman.check_available = AsyncMock(return_value=False)
        cli = _cli(
            [
                UpdaterConfig(pacman, "Pacman"),
                UpdaterConfig(FakeUpdater("AUR", log), "AUR", after=("Pacman",)),
            ]
        )
        code, _ = await _run(cli)
        assert code == 0
        assert log == ["start:AUR", "end:AUR"]

    async def test_independent_updaters_run_concurrently(self):
        log: list[str] = []
        cli = _cli(
            [
                UpdaterConfig(FakeUpdater("mise", log, delay=0.05), "mise"),
                UpdaterConfig(FakeUpdater("Flatpak", log, delay=0.05), "Flatpak"),
            ]
        )
        await _run(cli)
        assert log[:2] == ["start:mise", "start:Flatpak"]

    def test_default_registration_order(self):
        with patch("sysupdate.app.setup_logging"):
            cli = SysUpdateCLI()
        cfgs = {c.label: c for c in cli._updaters}
        assert cfgs["Omarchy"].after == ("Pacman",)
        assert cfgs["AUR"].after == ("Pacman", "Omarchy")
        assert cfgs["mise"].after == ()

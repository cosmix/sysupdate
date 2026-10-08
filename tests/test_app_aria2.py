"""Tests for when the aria2 install prompt is shown."""

from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.app import SysUpdateCLI, UpdaterConfig
from sysupdate.updaters.base import UpdateResult


def _updater(available: bool) -> MagicMock:
    updater = MagicMock()
    updater.name = "fake"
    updater.check_available = AsyncMock(return_value=available)
    updater.check_updates = AsyncMock(return_value=[])
    updater.run_update = AsyncMock(return_value=UpdateResult(success=True))
    return updater


async def _run(label: str, updater_available: bool, aria2_available: bool):
    with patch("sysupdate.app.setup_logging"):
        cli = SysUpdateCLI()
    cli._updaters = [UpdaterConfig(_updater(updater_available), label)]
    cli._print_summary = lambda *a, **k: None
    with (
        patch("sysupdate.app.Aria2Downloader") as aria2,
        patch("sysupdate.app.prompt_install_aria2", new_callable=AsyncMock) as prompt,
    ):
        aria2.return_value.check_available = AsyncMock(return_value=aria2_available)
        await cli._run_updates()
    return prompt


class TestAria2Prompt:
    async def test_not_prompted_when_apt_unavailable(self):
        prompt = await _run("APT", updater_available=False, aria2_available=False)
        prompt.assert_not_awaited()

    async def test_not_prompted_for_non_apt_updater(self):
        prompt = await _run("Pacman", updater_available=True, aria2_available=False)
        prompt.assert_not_awaited()

    async def test_prompted_when_apt_available_and_aria2_missing(self):
        prompt = await _run("APT", updater_available=True, aria2_available=False)
        prompt.assert_awaited_once()

    async def test_not_prompted_when_aria2_present(self):
        prompt = await _run("APT", updater_available=True, aria2_available=True)
        prompt.assert_not_awaited()

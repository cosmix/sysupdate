"""Tests for self-update orchestration and SelfUpdater.check_for_update()."""

from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.selfupdate.github import Release, ReleaseAsset
from sysupdate.selfupdate.updater import SelfUpdater, UpdateCheckResult, UpdateResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_release(version: str = "2.0.0", tag: str = "v2.0.0") -> Release:
    """Create a Release fixture with sensible defaults."""
    return Release(
        tag_name=tag,
        version=version,
        name=f"Release {version}",
        assets=[
            ReleaseAsset(
                name="sysupdate-linux-x86_64",
                download_url="https://example.com/sysupdate-linux-x86_64",
                size=1024,
            ),
            ReleaseAsset(
                name="SHA256SUMS.txt",
                download_url="https://example.com/SHA256SUMS.txt",
                size=256,
            ),
        ],
        prerelease=False,
    )


def _make_check_result(
    *,
    update_available: bool = False,
    current: str = "1.0.0",
    latest: str | None = "2.0.0",
    error: str = "",
    release: Release | None = None,
) -> UpdateCheckResult:
    """Create an UpdateCheckResult with convenient defaults."""
    if update_available and release is None:
        release = _make_release(version=latest or "2.0.0")
    return UpdateCheckResult(
        current_version=current,
        latest_version=latest,
        update_available=update_available,
        release=release,
        error_message=error,
    )


# ---------------------------------------------------------------------------
# SelfUpdater.check_for_update tests
# ---------------------------------------------------------------------------

class TestSelfUpdaterCheckForUpdate:
    """Tests for SelfUpdater.check_for_update() method."""

    async def test_returns_update_available_when_newer(self):
        """check_for_update reports update_available=True when remote is newer."""
        release = _make_release(version="2.0.0")

        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.return_value = release
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.0.0")

        assert result.update_available is True
        assert result.current_version == "1.0.0"
        assert result.latest_version == "2.0.0"
        assert result.release is release
        assert result.error_message == ""

    async def test_returns_no_update_when_same_version(self):
        """check_for_update reports update_available=False when versions match."""
        release = _make_release(version="1.0.0")

        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.return_value = release
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.0.0")

        assert result.update_available is False
        assert result.latest_version == "1.0.0"
        assert result.release is None
        assert result.error_message == ""

    async def test_returns_no_update_when_local_is_newer(self):
        """check_for_update reports update_available=False when local is ahead."""
        release = _make_release(version="1.0.0")

        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.return_value = release
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("3.0.0")

        assert result.update_available is False
        assert result.release is None

    async def test_returns_error_when_no_release_found(self):
        """check_for_update returns error when GitHub returns no release."""
        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.return_value = None
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.0.0")

        assert result.update_available is False
        assert result.latest_version is None
        assert result.release is None
        assert "Failed to fetch" in result.error_message

    async def test_returns_error_on_network_exception(self):
        """check_for_update catches exceptions and returns error result."""
        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("no network"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.0.0")

        assert result.update_available is False
        assert result.current_version == "1.0.0"
        assert "Error checking for updates" in result.error_message

    async def test_handles_get_latest_release_exception(self):
        """check_for_update handles exception from get_latest_release."""
        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.side_effect = RuntimeError("API error")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.0.0")

        assert result.update_available is False
        assert "Error checking for updates" in result.error_message

    async def test_release_excluded_when_not_newer(self):
        """When versions match, the release object is not included in result."""
        release = _make_release(version="1.5.0")

        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.return_value = release
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.5.0")

        assert result.release is None

    async def test_release_included_when_newer(self):
        """When an update is available, the release object is included."""
        release = _make_release(version="1.5.0")

        updater = SelfUpdater()
        mock_client = AsyncMock()
        mock_client.get_latest_release.return_value = release
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        updater._github_client = mock_client

        result = await updater.check_for_update("1.0.0")

        assert result.release is release


# ---------------------------------------------------------------------------
# run_self_update orchestrator tests
# ---------------------------------------------------------------------------

class TestRunSelfUpdate:
    """Tests for the run_self_update() orchestrator function."""

    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_check_only_no_update_returns_0(self, mock_updater_cls, mock_console_cls):
        """check_only with no update available returns 0."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = _make_check_result(
            update_available=False, current="1.0.0", latest="1.0.0"
        )
        mock_updater_cls.return_value = mock_updater

        result = await run_self_update(check_only=True)

        assert result == 0
        mock_updater.check_for_update.assert_awaited_once()

    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_check_only_update_available_returns_0(self, mock_updater_cls, mock_console_cls):
        """check_only with update available returns 0 and does not perform update."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = _make_check_result(
            update_available=True, current="1.0.0", latest="2.0.0"
        )
        mock_updater_cls.return_value = mock_updater

        result = await run_self_update(check_only=True)

        assert result == 0
        # perform_update should NOT be called in check-only mode
        mock_updater.perform_update.assert_not_awaited()

    @patch("sysupdate.selfupdate.Progress")
    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_full_update_success_returns_0(
        self, mock_updater_cls, mock_console_cls, mock_progress_cls
    ):
        """Successful full update returns 0."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        release = _make_release(version="2.0.0")
        check_result = _make_check_result(
            update_available=True, current="1.0.0", latest="2.0.0", release=release
        )

        update_result = UpdateResult(
            success=True, old_version="1.0.0", new_version="2.0.0", error_message=""
        )

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = check_result
        mock_updater.perform_update.return_value = update_result
        mock_updater_cls.return_value = mock_updater

        # Mock Progress context manager
        mock_progress = MagicMock()
        mock_progress.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress.__exit__ = MagicMock(return_value=False)
        mock_progress.add_task.return_value = 0
        mock_progress_cls.return_value = mock_progress

        result = await run_self_update(check_only=False)

        assert result == 0
        mock_updater.perform_update.assert_awaited_once()

    @patch("sysupdate.selfupdate.Progress")
    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_full_update_failure_returns_1(
        self, mock_updater_cls, mock_console_cls, mock_progress_cls
    ):
        """Failed update returns 1."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        release = _make_release(version="2.0.0")
        check_result = _make_check_result(
            update_available=True, current="1.0.0", latest="2.0.0", release=release
        )

        update_result = UpdateResult(
            success=False,
            old_version="1.0.0",
            new_version="2.0.0",
            error_message="Checksum mismatch",
        )

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = check_result
        mock_updater.perform_update.return_value = update_result
        mock_updater_cls.return_value = mock_updater

        mock_progress = MagicMock()
        mock_progress.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress.__exit__ = MagicMock(return_value=False)
        mock_progress.add_task.return_value = 0
        mock_progress_cls.return_value = mock_progress

        result = await run_self_update(check_only=False)

        assert result == 1

    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_check_exception_returns_1(self, mock_updater_cls, mock_console_cls):
        """Exception during check_for_update returns 1."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        mock_updater = AsyncMock()
        mock_updater.check_for_update.side_effect = ConnectionError("network down")
        mock_updater_cls.return_value = mock_updater

        result = await run_self_update(check_only=False)

        assert result == 1

    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_check_result_with_error_message_returns_1(
        self, mock_updater_cls, mock_console_cls
    ):
        """check_for_update returning error_message causes return code 1."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = _make_check_result(
            update_available=False,
            current="1.0.0",
            latest=None,
            error="Failed to fetch latest release from GitHub",
        )
        mock_updater_cls.return_value = mock_updater

        result = await run_self_update(check_only=False)

        assert result == 1

    @patch("sysupdate.selfupdate.Progress")
    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_perform_update_exception_returns_1(
        self, mock_updater_cls, mock_console_cls, mock_progress_cls
    ):
        """Exception during perform_update returns 1."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        release = _make_release(version="2.0.0")
        check_result = _make_check_result(
            update_available=True, current="1.0.0", latest="2.0.0", release=release
        )

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = check_result
        mock_updater.perform_update.side_effect = RuntimeError("disk full")
        mock_updater_cls.return_value = mock_updater

        mock_progress = MagicMock()
        mock_progress.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress.__exit__ = MagicMock(return_value=False)
        mock_progress.add_task.return_value = 0
        mock_progress_cls.return_value = mock_progress

        result = await run_self_update(check_only=False)

        assert result == 1

    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_update_available_but_release_none_returns_1(
        self, mock_updater_cls, mock_console_cls
    ):
        """Edge case: update_available=True but release=None returns 1."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = UpdateCheckResult(
            current_version="1.0.0",
            latest_version="2.0.0",
            update_available=True,
            release=None,
            error_message="",
        )
        mock_updater_cls.return_value = mock_updater

        result = await run_self_update(check_only=False)

        assert result == 1

    @patch("sysupdate.selfupdate.Console")
    @patch("sysupdate.selfupdate.SelfUpdater")
    async def test_no_update_no_latest_version(self, mock_updater_cls, mock_console_cls):
        """When latest_version is None but no error, still returns 0 (no update)."""
        from sysupdate.selfupdate import run_self_update

        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        mock_updater = AsyncMock()
        mock_updater.check_for_update.return_value = _make_check_result(
            update_available=False, current="1.0.0", latest=None, error=""
        )
        mock_updater_cls.return_value = mock_updater

        result = await run_self_update(check_only=False)

        # No update available and no error = success (already up to date)
        assert result == 0

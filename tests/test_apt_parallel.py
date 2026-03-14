"""Tests for the parallel APT update orchestration module."""

from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.updaters.apt_cache import PackageInfo
from sysupdate.updaters.apt_parallel import run_parallel_apt_update
from sysupdate.updaters.aria2_downloader import DownloadResult
from sysupdate.updaters.base import UpdatePhase, UpdateResult


def _make_package_infos(count: int = 3) -> list[PackageInfo]:
    """Create a list of sample PackageInfo objects."""
    return [
        PackageInfo(
            name=f"pkg-{i}",
            version=f"2.{i}",
            old_version=f"1.{i}",
            uris=[f"http://example.com/pkg-{i}.deb"],
            filename=f"pkg-{i}_2.{i}_amd64.deb",
            size=1000 * i,
            sha256=f"hash{i}",
        )
        for i in range(count)
    ]


class TestRunParallelAptUpdate:
    """Tests for the run_parallel_apt_update function."""

    async def test_phase1_apt_update_failure(self):
        """Test that failure in apt update (phase 1) returns an error result."""
        run_apt_update = AsyncMock(return_value=False)
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        progress_reports = []

        result = await run_parallel_apt_update(
            run_apt_update=run_apt_update,
            run_apt_install_from_cache=run_apt_install,
            run_sequential_update=run_sequential,
            callback=lambda p: progress_reports.append(p),
        )

        assert result.success is False
        assert "Failed to update package lists" in result.error_message
        run_apt_update.assert_awaited_once()
        run_apt_install.assert_not_awaited()

    async def test_phase2_cache_failure_falls_back_to_sequential(self):
        """Test that AptCacheWrapper failure triggers sequential fallback."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock()

        sequential_result = UpdateResult(success=True)
        run_sequential = AsyncMock(return_value=sequential_result)

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            side_effect=RuntimeError("python3-apt not available"),
        ):
            result = await run_parallel_apt_update(
                run_apt_update=run_apt_update,
                run_apt_install_from_cache=run_apt_install,
                run_sequential_update=run_sequential,
            )

        assert result is sequential_result
        run_sequential.assert_awaited_once()

    async def test_no_packages_returns_success(self):
        """Test that when no packages need upgrading, success is returned immediately."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        mock_cache = MagicMock()
        mock_cache.get_upgradable_packages.return_value = []

        progress_reports = []

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            return_value=mock_cache,
        ):
            with patch("asyncio.to_thread", new_callable=AsyncMock, return_value=[]):
                result = await run_parallel_apt_update(
                    run_apt_update=run_apt_update,
                    run_apt_install_from_cache=run_apt_install,
                    run_sequential_update=run_sequential,
                    callback=lambda p: progress_reports.append(p),
                )

        assert result.success is True
        assert result.packages == []
        # Should have a COMPLETE phase report
        complete_reports = [r for r in progress_reports if r.phase == UpdatePhase.COMPLETE]
        assert len(complete_reports) >= 1

    async def test_dry_run_returns_packages_without_installing(self):
        """Test that dry_run returns package list without downloading or installing."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        package_infos = _make_package_infos(2)

        mock_cache = MagicMock()
        mock_cache.get_upgradable_packages.return_value = package_infos

        progress_reports = []

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            return_value=mock_cache,
        ):
            with patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=package_infos,
            ):
                result = await run_parallel_apt_update(
                    run_apt_update=run_apt_update,
                    run_apt_install_from_cache=run_apt_install,
                    run_sequential_update=run_sequential,
                    callback=lambda p: progress_reports.append(p),
                    dry_run=True,
                )

        assert result.success is True
        assert len(result.packages) == 2
        assert result.packages[0].name == "pkg-0"
        assert result.packages[1].name == "pkg-1"
        run_apt_install.assert_not_awaited()

    async def test_download_failure_falls_back_to_sequential(self):
        """Test that failed parallel download triggers sequential fallback."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock()

        sequential_result = UpdateResult(success=True)
        run_sequential = AsyncMock(return_value=sequential_result)

        package_infos = _make_package_infos(2)

        mock_cache = MagicMock()
        mock_cache.get_upgradable_packages.return_value = package_infos

        download_result = DownloadResult(
            success=False, error_message="Network error"
        )
        mock_downloader = MagicMock()
        mock_downloader.download_packages = AsyncMock(return_value=download_result)

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            return_value=mock_cache,
        ):
            with patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=package_infos,
            ):
                with patch(
                    "sysupdate.updaters.apt_parallel.Aria2Downloader",
                    return_value=mock_downloader,
                ):
                    result = await run_parallel_apt_update(
                        run_apt_update=run_apt_update,
                        run_apt_install_from_cache=run_apt_install,
                        run_sequential_update=run_sequential,
                    )

        assert result is sequential_result
        run_sequential.assert_awaited_once()

    async def test_full_success_flow(self):
        """Test the complete 4-phase successful flow."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock(return_value=(True, ""))
        run_sequential = AsyncMock()

        package_infos = _make_package_infos(3)

        mock_cache = MagicMock()
        mock_cache.get_upgradable_packages.return_value = package_infos

        download_result = DownloadResult(
            success=True,
            downloaded_files=["pkg-0_2.0_amd64.deb", "pkg-1_2.1_amd64.deb", "pkg-2_2.2_amd64.deb"],
        )
        mock_downloader = MagicMock()
        mock_downloader.download_packages = AsyncMock(return_value=download_result)

        progress_reports = []

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            return_value=mock_cache,
        ):
            with patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=package_infos,
            ):
                with patch(
                    "sysupdate.updaters.apt_parallel.Aria2Downloader",
                    return_value=mock_downloader,
                ):
                    result = await run_parallel_apt_update(
                        run_apt_update=run_apt_update,
                        run_apt_install_from_cache=run_apt_install,
                        run_sequential_update=run_sequential,
                        callback=lambda p: progress_reports.append(p),
                    )

        assert result.success is True
        assert len(result.packages) == 3
        assert result.packages[0].name == "pkg-0"
        assert result.packages[2].name == "pkg-2"
        run_sequential.assert_not_awaited()

        # Verify phase progression
        phases_seen = [r.phase for r in progress_reports]
        assert UpdatePhase.CHECKING in phases_seen
        assert UpdatePhase.DOWNLOADING in phases_seen
        assert UpdatePhase.INSTALLING in phases_seen
        assert UpdatePhase.COMPLETE in phases_seen

    async def test_install_failure_returns_error(self):
        """Test that installation failure is correctly reported."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock(return_value=(False, "dpkg error: broken packages"))
        run_sequential = AsyncMock()

        package_infos = _make_package_infos(1)

        mock_cache = MagicMock()
        mock_cache.get_upgradable_packages.return_value = package_infos

        download_result = DownloadResult(
            success=True,
            downloaded_files=["pkg-0_2.0_amd64.deb"],
        )
        mock_downloader = MagicMock()
        mock_downloader.download_packages = AsyncMock(return_value=download_result)

        progress_reports = []

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            return_value=mock_cache,
        ):
            with patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=package_infos,
            ):
                with patch(
                    "sysupdate.updaters.apt_parallel.Aria2Downloader",
                    return_value=mock_downloader,
                ):
                    result = await run_parallel_apt_update(
                        run_apt_update=run_apt_update,
                        run_apt_install_from_cache=run_apt_install,
                        run_sequential_update=run_sequential,
                        callback=lambda p: progress_reports.append(p),
                    )

        assert result.success is False
        assert "dpkg error" in result.error_message

        error_reports = [r for r in progress_reports if r.phase == UpdatePhase.ERROR]
        assert len(error_reports) >= 1

    async def test_progress_scaling_checking_phase(self):
        """Test that checking phase progress is scaled to 0-10% range."""
        run_apt_update = AsyncMock(return_value=False)
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        progress_reports = []

        await run_parallel_apt_update(
            run_apt_update=run_apt_update,
            run_apt_install_from_cache=run_apt_install,
            run_sequential_update=run_sequential,
            callback=lambda p: progress_reports.append(p),
        )

        # The initial CHECKING report should be at 0%
        checking_reports = [r for r in progress_reports if r.phase == UpdatePhase.CHECKING]
        assert len(checking_reports) >= 1
        assert checking_reports[0].progress == 0.0

    async def test_no_callback_does_not_raise(self):
        """Test that passing no callback does not cause errors."""
        run_apt_update = AsyncMock(return_value=False)
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        result = await run_parallel_apt_update(
            run_apt_update=run_apt_update,
            run_apt_install_from_cache=run_apt_install,
            run_sequential_update=run_sequential,
            callback=None,
        )

        assert result.success is False

    async def test_unexpected_exception_is_caught(self):
        """Test that unexpected exceptions are caught and reported."""
        run_apt_update = AsyncMock(side_effect=RuntimeError("unexpected boom"))
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        progress_reports = []

        result = await run_parallel_apt_update(
            run_apt_update=run_apt_update,
            run_apt_install_from_cache=run_apt_install,
            run_sequential_update=run_sequential,
            callback=lambda p: progress_reports.append(p),
        )

        assert result.success is False
        assert "unexpected boom" in result.error_message
        assert result.end_time is not None

    async def test_result_always_has_end_time(self):
        """Test that result always has end_time set, regardless of outcome."""
        run_apt_update = AsyncMock(return_value=False)
        run_apt_install = AsyncMock()
        run_sequential = AsyncMock()

        result = await run_parallel_apt_update(
            run_apt_update=run_apt_update,
            run_apt_install_from_cache=run_apt_install,
            run_sequential_update=run_sequential,
        )

        assert result.end_time is not None

    async def test_download_failure_with_logger(self):
        """Test that download failure logs a message when logger is provided."""
        run_apt_update = AsyncMock(return_value=True)
        run_apt_install = AsyncMock()

        sequential_result = UpdateResult(success=True)
        run_sequential = AsyncMock(return_value=sequential_result)

        package_infos = _make_package_infos(1)

        mock_cache = MagicMock()
        download_result = DownloadResult(success=False, error_message="timeout")
        mock_downloader = MagicMock()
        mock_downloader.download_packages = AsyncMock(return_value=download_result)

        mock_logger = MagicMock()

        with patch(
            "sysupdate.updaters.apt_parallel.AptCacheWrapper",
            return_value=mock_cache,
        ):
            with patch(
                "asyncio.to_thread",
                new_callable=AsyncMock,
                return_value=package_infos,
            ):
                with patch(
                    "sysupdate.updaters.apt_parallel.Aria2Downloader",
                    return_value=mock_downloader,
                ):
                    await run_parallel_apt_update(
                        run_apt_update=run_apt_update,
                        run_apt_install_from_cache=run_apt_install,
                        run_sequential_update=run_sequential,
                        logger=mock_logger,
                    )

        mock_logger.log.assert_called()
        logged_message = mock_logger.log.call_args[0][0]
        assert "falling back" in logged_message.lower()

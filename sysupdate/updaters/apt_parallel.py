"""Parallel APT update implementation using aria2c."""

import asyncio
from datetime import datetime

from .base import Package, UpdateProgress, UpdateResult, UpdatePhase, ProgressCallback
from .apt_cache import AptCacheWrapper
from .aria2_downloader import Aria2Downloader
from ..utils.logging import UpdateLogger


async def run_parallel_apt_update(
    run_apt_update,
    run_apt_install_from_cache,
    run_sequential_update,
    callback: ProgressCallback | None = None,
    dry_run: bool = False,
    logger: UpdateLogger | None = None,
) -> UpdateResult:
    """Run the APT update process using parallel downloads via aria2c.

    Args:
        run_apt_update: Coroutine function to run apt update.
        run_apt_install_from_cache: Coroutine function to install from cache.
        run_sequential_update: Fallback coroutine for sequential update.
        callback: Optional progress callback.
        dry_run: If True, don't actually install updates.
        logger: Optional logger instance.

    Returns:
        UpdateResult with success status and package list.
    """
    result = UpdateResult(success=False)

    # Progress allocation:
    # - Checking (apt update): 0% - 10%
    # - Downloading: 10% - 50%
    # - Installing: 50% - 100%
    checking_end = 0.1
    download_start = 0.1
    download_end = 0.5
    install_start = 0.5

    def report(progress: UpdateProgress) -> None:
        if callback:
            callback(progress)

    try:
        # Phase 1: apt update (0% - 10%)
        report(UpdateProgress(
            phase=UpdatePhase.CHECKING,
            progress=0.0,
            message="Updating package lists...",
        ))

        # Wrapper to scale apt update progress to 0-10%
        def checking_progress_callback(update: UpdateProgress) -> None:
            if update.phase == UpdatePhase.CHECKING and update.progress > 0:
                scaled = update.progress * checking_end
                report(UpdateProgress(
                    phase=update.phase,
                    progress=scaled,
                    message=update.message,
                ))
            else:
                report(update)

        success = await run_apt_update(checking_progress_callback)
        if not success:
            result.error_message = "Failed to update package lists"
            result.end_time = datetime.now()
            return result

        # Phase 2: Get upgradable packages using AptCacheWrapper
        report(UpdateProgress(
            phase=UpdatePhase.CHECKING,
            progress=checking_end,  # 10%
            message="Analyzing packages...",
        ))

        try:
            cache = AptCacheWrapper()
            package_infos = await asyncio.to_thread(cache.get_upgradable_packages)
        except Exception as e:
            if logger:
                logger.log(f"Failed to get upgradable packages: {e}")
            # Fall back to sequential update
            return await run_sequential_update(callback, dry_run)

        if not package_infos:
            # No packages to update
            result.success = True
            result.packages = []
            report(UpdateProgress(
                phase=UpdatePhase.COMPLETE,
                progress=1.0,
                message="Already up to date",
            ))
            result.end_time = datetime.now()
            return result

        if dry_run:
            # Just simulate
            packages = [
                Package(
                    name=pkg.name,
                    new_version=pkg.version,
                    old_version=pkg.old_version,
                )
                for pkg in package_infos
            ]
            result.packages = packages
            result.success = True
            report(UpdateProgress(
                phase=UpdatePhase.COMPLETE,
                progress=1.0,
                completed_packages=len(packages),
                total_packages=len(packages),
            ))
            result.end_time = datetime.now()
            return result

        # Phase 3: Download packages in parallel (10% - 50%)
        total_packages = len(package_infos)
        report(UpdateProgress(
            phase=UpdatePhase.DOWNLOADING,
            progress=download_start,  # Start at 10%
            message=f"Downloading {total_packages} packages in parallel...",
            total_packages=total_packages,
            completed_packages=0,
        ))

        downloader = Aria2Downloader()

        def download_progress_callback(progress_info) -> None:
            """Callback for download progress from aria2."""
            # progress_info is a DownloadProgress object
            # Scale download progress from 10% to 50%
            raw_pct = progress_info.progress  # 0.0 to 1.0 from aria2
            download_range = download_end - download_start  # 0.4
            scaled_pct = download_start + (raw_pct * download_range)  # 0.1 to 0.5
            report(UpdateProgress(
                phase=UpdatePhase.DOWNLOADING,
                progress=scaled_pct,
                completed_packages=int(raw_pct * total_packages),
                total_packages=total_packages,
                current_package=progress_info.filename or "",
                speed=progress_info.speed,
                eta=progress_info.eta,
            ))

        download_success = await downloader.download_packages(
            package_infos,
            callback=download_progress_callback,
        )

        if not download_success.success:
            error_msg = "Parallel download failed, falling back to sequential update"
            if logger:
                logger.log(error_msg)
            # Fall back to sequential update
            return await run_sequential_update(callback, dry_run)

        # Phase 4: Install downloaded packages (50% - 100%)
        report(UpdateProgress(
            phase=UpdatePhase.INSTALLING,
            message="Installing downloaded packages...",
            progress=install_start,  # Start at 50%
            total_packages=total_packages,
            completed_packages=0,
        ))

        # Create a wrapper callback that scales install progress from 0-1 to 50%-100%
        install_range = 1.0 - install_start  # 0.5

        def install_progress_callback(update: UpdateProgress) -> None:
            if update.phase == UpdatePhase.INSTALLING:
                # Scale: internal 0-1 becomes 0.5-1.0
                scaled_progress = install_start + (update.progress * install_range)
                report(UpdateProgress(
                    phase=update.phase,
                    progress=scaled_progress,
                    total_packages=update.total_packages,
                    completed_packages=update.completed_packages,
                    current_package=update.current_package,
                    message=update.message,
                ))
            else:
                report(update)

        install_success, install_error = await run_apt_install_from_cache(
            install_progress_callback, total_packages
        )

        if not install_success:
            result.error_message = install_error
            result.success = False
            report(UpdateProgress(
                phase=UpdatePhase.ERROR,
                message=install_error,
            ))
        else:
            # Convert PackageInfo to Package
            packages = [
                Package(
                    name=pkg.name,
                    new_version=pkg.version,
                    old_version=pkg.old_version,
                )
                for pkg in package_infos
            ]
            result.packages = packages
            result.success = True
            report(UpdateProgress(
                phase=UpdatePhase.COMPLETE,
                progress=1.0,
                completed_packages=total_packages,
                total_packages=total_packages,
            ))

    except Exception as e:
        result.error_message = str(e)
        if logger:
            logger.log(f"Error in parallel update: {e}")
        report(UpdateProgress(
            phase=UpdatePhase.ERROR,
            message=str(e),
        ))

    result.end_time = datetime.now()
    return result

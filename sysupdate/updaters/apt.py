"""APT package manager updater."""

import asyncio
import os
import re
from datetime import datetime

from .base import (
    BaseUpdater,
    Package,
    UpdateProgress,
    UpdateResult,
    UpdatePhase,
    ProgressCallback,
    create_scaled_callback,
)
from .apt_cache import is_apt_available
from .apt_parallel import run_parallel_apt_update
from .apt_parsing import AptUpgradeProgressTracker, AptUpdateProgressTracker
from ..utils import command_available
from ..utils.logging import UpdateLogger
from ..utils.parsing import parse_apt_output


class AptUpdater(BaseUpdater):
    """Updater for APT packages.

    APT has both a sequential and a parallel (aria2c) code path,
    so it overrides :meth:`run_update` instead of using the base template.
    """

    def __init__(self, use_parallel: bool = True) -> None:
        super().__init__()
        self._use_parallel = use_parallel

    @property
    def name(self) -> str:
        return "APT Packages"

    async def check_available(self) -> bool:
        """Check if APT is available."""
        return await command_available("which", "apt")

    async def check_updates(self) -> list[Package]:
        """Check for available updates without installing."""
        packages: list[Package] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "apt", "update",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            proc = await asyncio.create_subprocess_exec(
                "apt", "list", "--upgradable",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            for line in stdout.decode().splitlines():
                if "/" not in line:
                    continue
                match = re.match(
                    r"(\S+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s+(\S+)\]", line
                )
                if match:
                    packages.append(Package(
                        name=match.group(1),
                        new_version=match.group(2),
                        old_version=match.group(3),
                    ))
        except FileNotFoundError:
            return []
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error checking updates: {e}")
        return packages

    async def _do_upgrade(self, report: ProgressCallback) -> tuple[list[Package], bool, str]:
        """Delegate to _run_apt_upgrade (required by BaseUpdater ABC)."""
        return await self._run_apt_upgrade(report)

    async def _can_use_parallel(self) -> bool:
        """Check if parallel downloads are available."""
        if not is_apt_available():
            return False
        return await command_available("aria2c", "--version")

    async def run_update(
        self, callback: ProgressCallback | None = None, dry_run: bool = False,
    ) -> UpdateResult:
        """Run the APT update process, dispatching to parallel or sequential."""
        if self._use_parallel and await self._can_use_parallel():
            return await self._run_parallel_update(callback, dry_run)
        return await self._run_sequential_update(callback, dry_run)

    async def _run_sequential_update(
        self, callback: ProgressCallback | None = None, dry_run: bool = False,
    ) -> UpdateResult:
        """Run the APT update process using sequential apt full-upgrade."""
        result = UpdateResult(success=False)
        self._logger = UpdateLogger("apt")
        checking_end = 0.1

        def report(progress: UpdateProgress) -> None:
            if callback:
                callback(progress)

        try:
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING, progress=0.0,
                message="Refreshing package lists",
            ))
            checking_callback = create_scaled_callback(
                report, scale_start=0.0, scale_end=checking_end,
                phases_to_scale={UpdatePhase.CHECKING},
            )
            success = await self._run_apt_update(checking_callback)
            if not success:
                result.error_message = "Failed to update package lists"
                result.end_time = datetime.now()
                return result

            report(UpdateProgress(
                phase=UpdatePhase.DOWNLOADING, progress=checking_end,
                message="Downloading and installing updates...",
            ))

            if dry_run:
                packages = await self.check_updates()
                result.packages = packages
                result.success = True
                report(UpdateProgress(
                    phase=UpdatePhase.COMPLETE, progress=1.0,
                    completed_packages=len(packages), total_packages=len(packages),
                ))
            else:
                upgrade_callback = create_scaled_callback(
                    report, scale_start=checking_end, scale_end=0.5,
                    phases_to_scale={UpdatePhase.DOWNLOADING},
                )
                packages, success, error = await self._run_apt_upgrade(upgrade_callback)
                result.packages = packages
                result.success = success
                result.error_message = error
                if success:
                    report(UpdateProgress(
                        phase=UpdatePhase.COMPLETE, progress=1.0,
                        completed_packages=len(packages), total_packages=len(packages),
                    ))
                else:
                    report(UpdateProgress(phase=UpdatePhase.ERROR, message=error))
        except Exception as e:
            result.error_message = str(e)
            report(UpdateProgress(phase=UpdatePhase.ERROR, message=str(e)))
        finally:
            if self._process:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            if self._logger:
                self._logger.close()

        result.end_time = datetime.now()
        return result

    async def _run_parallel_update(
        self, callback: ProgressCallback | None = None, dry_run: bool = False,
    ) -> UpdateResult:
        """Run the APT update process using parallel downloads via aria2c."""
        self._logger = UpdateLogger("apt")
        try:
            return await run_parallel_apt_update(
                run_apt_update=self._run_apt_update,
                run_apt_install_from_cache=self._run_apt_install_from_cache,
                run_sequential_update=self._run_sequential_update,
                callback=callback, dry_run=dry_run, logger=self._logger,
            )
        finally:
            if self._process:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            if self._logger:
                self._logger.close()

    async def _run_apt_install_from_cache(
        self, report: ProgressCallback, total_packages: int,
    ) -> tuple[bool, str]:
        """Install packages from the APT cache using apt-get --no-download."""
        try:
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            self._process = await asyncio.create_subprocess_exec(
                "sudo", "apt-get", "-y", "--no-download", "dist-upgrade",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            if not self._process.stdout:
                return False, "Failed to create subprocess stdout pipe"

            completed = 0
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                decoded = line.decode().strip()
                if self._logger:
                    self._logger.log(decoded)
                if "Setting up" in decoded:
                    completed += 1
                    match = re.search(r"Setting up\s+(\S+)", decoded)
                    pkg_name = match.group(1).split(":")[0] if match else ""
                    progress = completed / total_packages if total_packages > 0 else 0.0
                    report(UpdateProgress(
                        phase=UpdatePhase.INSTALLING, progress=progress,
                        completed_packages=completed, total_packages=total_packages,
                        current_package=pkg_name,
                    ))

            await self._process.wait()
            if self._process.returncode != 0:
                return False, "apt-get dist-upgrade failed"
            return True, ""
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error installing from cache: {e}")
            return False, str(e)

    async def _run_apt_update(self, report: ProgressCallback) -> bool:
        """Run apt update command with progress tracking."""
        try:
            self._process = await asyncio.create_subprocess_exec(
                "sudo", "apt", "update",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            if not self._process.stdout:
                return False

            tracker = AptUpdateProgressTracker()
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                decoded = line.decode().strip()
                if self._logger:
                    self._logger.log(decoded)

                progress = tracker.parse_line(decoded)
                if progress is not None:
                    if "Hit:" in decoded:
                        msg = "Syncing package sources"
                    elif "Get:" in decoded:
                        msg = "Fetching package lists"
                    elif "Reading" in decoded:
                        msg = "Checking for upgrades"
                    else:
                        msg = "Refreshing package lists"
                    report(UpdateProgress(
                        phase=UpdatePhase.CHECKING, progress=progress, message=msg,
                    ))
                elif "Hit:" in decoded or "Get:" in decoded:
                    msg = (
                        "Syncing package sources" if "Hit:" in decoded
                        else "Fetching package lists"
                    )
                    report(UpdateProgress(phase=UpdatePhase.CHECKING, message=msg))

            await self._process.wait()
            return self._process.returncode == 0
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error: {e}")
            return False

    async def _run_apt_upgrade(
        self, report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run apt full-upgrade command with progress reporting."""
        packages: list[Package] = []
        collected_output: list[str] = []
        error_msg = ""

        try:
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            self._process = await asyncio.create_subprocess_exec(
                "sudo", "apt-get", "full-upgrade", "-y",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            if not self._process.stdout:
                return [], False, "Failed to create subprocess stdout pipe"

            tracker = AptUpgradeProgressTracker()
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                decoded = line.decode().strip()
                collected_output.append(decoded)
                if self._logger:
                    self._logger.log(decoded)

                progress_info = tracker.parse_line(decoded)
                if progress_info:
                    phase_map = {
                        "downloading": UpdatePhase.DOWNLOADING,
                        "installing": UpdatePhase.INSTALLING,
                        "complete": UpdatePhase.COMPLETE,
                    }
                    phase = phase_map.get(
                        progress_info.get("phase", ""), UpdatePhase.DOWNLOADING
                    )
                    report(UpdateProgress(
                        phase=phase,
                        progress=progress_info.get("progress", 0.0),
                        total_packages=progress_info.get("total_packages", 0),
                        completed_packages=progress_info.get("completed_packages", 0),
                        current_package=progress_info.get("current_package", ""),
                        message=progress_info.get("message", ""),
                    ))
                    if tracker.is_up_to_date:
                        await self._process.wait()
                        return [], True, ""

            await self._process.wait()
            if self._process.returncode != 0:
                for line in reversed(collected_output):
                    if "E:" in line or "error" in line.lower():
                        error_msg = line
                        break
                if not error_msg:
                    error_msg = "apt full-upgrade failed"
                return [], False, error_msg

            full_output = "\n".join(collected_output)
            packages = parse_apt_output(full_output)
            return packages, True, ""
        except Exception as e:
            error_msg = str(e)
            if self._logger:
                self._logger.log(f"Error: {e}")
            return [], False, error_msg

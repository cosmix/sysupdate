"""Pacman package manager updater for Arch-based systems."""

import asyncio
import re
from datetime import datetime

from .base import (
    Package,
    UpdateProgress,
    UpdateResult,
    UpdatePhase,
    ProgressCallback,
    create_scaled_callback,
)
from ..utils import command_available
from ..utils.logging import UpdateLogger


class PacmanUpdater:
    """Updater for Pacman packages (Arch Linux, Manjaro, EndeavourOS, etc.)."""

    name = "Pacman Packages"

    def __init__(self) -> None:
        self._logger: UpdateLogger | None = None
        self._process: asyncio.subprocess.Process | None = None

    async def check_available(self) -> bool:
        """Check if Pacman is available on the system."""
        return await command_available("which", "pacman")

    async def check_updates(self) -> list[Package]:
        """Check for available Pacman updates using pacman -Qu."""
        packages: list[Package] = []

        try:
            # First sync the database (requires sudo for -Sy, but -Sy is needed for accurate -Qu)
            # We use checkupdates if available (from pacman-contrib) as it doesn't need root
            if await command_available("which", "checkupdates"):
                proc = await asyncio.create_subprocess_exec(
                    "checkupdates",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Fall back to pacman -Qu (may show stale results without -Sy)
                proc = await asyncio.create_subprocess_exec(
                    "pacman", "-Qu",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, _ = await proc.communicate()

            # checkupdates returns 2 when no updates, pacman -Qu returns 1
            # Both return 0 when updates are available
            if proc.returncode not in (0, 1, 2):
                return []

            # Parse output format: "package oldversion -> newversion"
            # or just "package newversion" for pacman -Qu
            for line in stdout.decode().splitlines():
                line = line.strip()
                if not line:
                    continue

                # checkupdates format: "package oldver -> newver"
                arrow_match = re.match(r'^(\S+)\s+(\S+)\s+->\s+(\S+)$', line)
                if arrow_match:
                    packages.append(Package(
                        name=arrow_match.group(1),
                        old_version=arrow_match.group(2),
                        new_version=arrow_match.group(3),
                    ))
                    continue

                # pacman -Qu format: "package newver"
                simple_match = re.match(r'^(\S+)\s+(\S+)$', line)
                if simple_match:
                    packages.append(Package(
                        name=simple_match.group(1),
                        new_version=simple_match.group(2),
                    ))

        except FileNotFoundError:
            return []  # Package manager not installed
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error checking updates: {e}")

        return packages

    async def _get_current_versions(self, package_names: list[str]) -> dict[str, str]:
        """Get current installed versions for packages via pacman -Q."""
        versions: dict[str, str] = {}

        if not package_names:
            return versions

        try:
            proc = await asyncio.create_subprocess_exec(
                "pacman", "-Q", *package_names,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            # Output format: "package version"
            for line in stdout.decode().splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    versions[parts[0]] = parts[1]

        except FileNotFoundError:
            return {}  # Package manager not installed
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error getting current versions: {e}")

        return versions

    async def run_update(
        self,
        callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> UpdateResult:
        """Run the Pacman update process."""
        result = UpdateResult(success=False)
        self._logger = UpdateLogger("pacman")

        # Progress allocation: 0-10% checking, 10-50% downloading, 50-100% installing
        checking_end = 0.1

        def report(progress: UpdateProgress) -> None:
            if callback:
                callback(progress)

        try:
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.0,
                message="Checking for Pacman updates...",
            ))

            if dry_run:
                packages = await self.check_updates()
                result.packages = packages
                result.success = True
                report(UpdateProgress(
                    phase=UpdatePhase.COMPLETE,
                    progress=1.0,
                    completed_packages=len(packages),
                    total_packages=len(packages),
                ))
            else:
                scaled_callback = create_scaled_callback(
                    report,
                    scale_start=checking_end,
                    scale_end=1.0,
                    phases_to_scale={UpdatePhase.DOWNLOADING, UpdatePhase.INSTALLING},
                )

                packages, success, error = await self._run_pacman_upgrade(scaled_callback)
                result.packages = packages
                result.success = success
                result.error_message = error

                if success:
                    report(UpdateProgress(
                        phase=UpdatePhase.COMPLETE,
                        progress=1.0,
                        completed_packages=len(packages),
                        total_packages=len(packages),
                    ))
                else:
                    report(UpdateProgress(
                        phase=UpdatePhase.ERROR,
                        message=error,
                    ))

        except Exception as e:
            result.error_message = str(e)
            report(UpdateProgress(
                phase=UpdatePhase.ERROR,
                message=str(e),
            ))

        finally:
            if self._logger:
                self._logger.close()

        result.end_time = datetime.now()
        return result

    async def _run_pacman_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run pacman -Syu command."""
        packages: list[Package] = []
        collected_output: list[str] = []
        error_msg = ""

        try:
            # First check what updates are available
            pending = await self.check_updates()
            if not pending:
                report(UpdateProgress(
                    phase=UpdatePhase.COMPLETE,
                    progress=1.0,
                    message="All packages up to date",
                ))
                return [], True, ""

            total_packages = len(pending)
            package_names = [p.name for p in pending]

            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.05,
                message=f"Found {total_packages} update(s)",
            ))

            # Get current versions before update (if not already known from checkupdates)
            old_versions = {p.name: p.old_version for p in pending if p.old_version}
            missing_versions = [p.name for p in pending if not p.old_version]
            if missing_versions:
                fetched = await self._get_current_versions(missing_versions)
                old_versions.update(fetched)

            # Run pacman -Syu --noconfirm
            self._process = await asyncio.create_subprocess_exec(
                "sudo", "pacman", "-Syu", "--noconfirm", "--color", "never",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            stdout = self._process.stdout
            if not stdout:
                return [], False, "Failed to create subprocess stdout pipe"

            completed = 0
            current_package = ""
            buffer = ""
            last_progress_report = 0.0
            in_downloading_phase = False
            in_installing_phase = False
            download_count = 0
            install_count = 0

            async def read_chunk() -> bytes:
                """Read available data from stdout."""
                return await stdout.read(1024)

            while True:
                chunk = await read_chunk()
                if not chunk:
                    break

                text = chunk.decode(errors='replace')
                buffer += text

                while '\n' in buffer or '\r' in buffer:
                    newline_pos = buffer.find('\n')
                    cr_pos = buffer.find('\r')

                    if newline_pos == -1:
                        split_pos = cr_pos
                    elif cr_pos == -1:
                        split_pos = newline_pos
                    else:
                        split_pos = min(newline_pos, cr_pos)

                    line = buffer[:split_pos].strip()
                    buffer = buffer[split_pos + 1:]

                    if not line:
                        continue

                    collected_output.append(line)
                    if self._logger:
                        self._logger.log(line)

                    # Check for "there is nothing to do" message
                    if "there is nothing to do" in line.lower():
                        report(UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="All packages up to date",
                        ))
                        await self._process.wait()
                        return [], True, ""

                    # Detect phase: ":: Retrieving packages..."
                    if "retrieving packages" in line.lower() or "downloading" in line.lower():
                        in_downloading_phase = True
                        in_installing_phase = False
                        report(UpdateProgress(
                            phase=UpdatePhase.DOWNLOADING,
                            progress=0.1,
                            message="Downloading packages...",
                        ))
                        continue

                    # Detect install phase: "(x/y) upgrading" or "(x/y) installing"
                    install_match = re.search(r'^\((\d+)/(\d+)\)\s+(upgrading|installing|reinstalling)\s+(\S+)', line, re.IGNORECASE)
                    if install_match:
                        in_downloading_phase = False
                        in_installing_phase = True
                        current_idx = int(install_match.group(1))
                        total_idx = int(install_match.group(2))
                        action = install_match.group(3).lower()
                        pkg_name = install_match.group(4)

                        current_package = pkg_name
                        install_count = current_idx

                        # Progress: 50-100% for install phase
                        progress = 0.5 + (current_idx / max(total_idx, 1)) * 0.5

                        if progress > last_progress_report + 0.01:
                            last_progress_report = progress
                            report(UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=progress,
                                total_packages=total_packages,
                                completed_packages=current_idx,
                                current_package=current_package,
                            ))

                        # Track completed packages
                        if action in ("upgrading", "reinstalling"):
                            matched_pkg = None
                            for p in pending:
                                if p.name == pkg_name or pkg_name.startswith(p.name):
                                    matched_pkg = p
                                    break

                            if matched_pkg and matched_pkg not in [pkg for pkg in packages]:
                                old_ver = old_versions.get(matched_pkg.name, "")
                                packages.append(Package(
                                    name=matched_pkg.name,
                                    old_version=old_ver,
                                    new_version=matched_pkg.new_version,
                                    status="complete",
                                ))
                        continue

                    # Parse download progress: "package-name   x.x MiB   y.y MiB/s xx:xx [####] 100%"
                    # or simpler: downloading package...
                    download_match = re.search(r'downloading\s+(\S+)', line, re.IGNORECASE)
                    if download_match and in_downloading_phase:
                        current_package = download_match.group(1)
                        download_count += 1
                        # Progress: 10-50% for download phase
                        progress = 0.1 + (download_count / max(total_packages, 1)) * 0.4

                        if progress > last_progress_report + 0.01:
                            last_progress_report = progress
                            report(UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_packages,
                                completed_packages=download_count,
                                current_package=current_package,
                            ))

            await self._process.wait()

            if self._process.returncode != 0:
                for line in reversed(collected_output):
                    if "error" in line.lower() or "failed" in line.lower():
                        error_msg = line
                        break
                if not error_msg:
                    error_msg = "pacman upgrade failed"
                return [], False, error_msg

            return packages, True, ""

        except Exception as e:
            error_msg = str(e)
            if self._logger:
                self._logger.log(f"Error: {e}")
            return [], False, error_msg

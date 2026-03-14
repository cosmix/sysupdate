"""Pacman package manager updater for Arch-based systems."""

import asyncio
import re

from .base import (
    BaseUpdater,
    Package,
    PackageStatus,
    UpdateProgress,
    UpdatePhase,
    ProgressCallback,
    read_process_lines,
)
from ..utils import command_available


class PacmanUpdater(BaseUpdater):
    """Updater for Pacman packages (Arch Linux, Manjaro, EndeavourOS, etc.)."""

    @property
    def name(self) -> str:
        return "Pacman Packages"

    async def check_available(self) -> bool:
        """Check if Pacman is available on the system."""
        return await command_available("which", "pacman")

    async def check_updates(self) -> list[Package]:
        """Check for available Pacman updates using pacman -Qu."""
        packages: list[Package] = []

        try:
            # Use checkupdates if available (from pacman-contrib) as it doesn't need root
            if await command_available("which", "checkupdates"):
                proc = await asyncio.create_subprocess_exec(
                    "checkupdates",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Fall back to pacman -Qu (may show stale results without -Sy)
                proc = await asyncio.create_subprocess_exec(
                    "pacman",
                    "-Qu",
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
                arrow_match = re.match(r"^(\S+)\s+(\S+)\s+->\s+(\S+)$", line)
                if arrow_match:
                    packages.append(
                        Package(
                            name=arrow_match.group(1),
                            old_version=arrow_match.group(2),
                            new_version=arrow_match.group(3),
                        )
                    )
                    continue

                # pacman -Qu format: "package newver"
                simple_match = re.match(r"^(\S+)\s+(\S+)$", line)
                if simple_match:
                    packages.append(
                        Package(
                            name=simple_match.group(1),
                            new_version=simple_match.group(2),
                        )
                    )

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
            # Use -- separator to prevent option injection from package names
            proc = await asyncio.create_subprocess_exec(
                "pacman",
                "-Q",
                "--",
                *package_names,
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

    async def _do_upgrade(
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
                report(
                    UpdateProgress(
                        phase=UpdatePhase.COMPLETE,
                        progress=1.0,
                        message="All packages up to date",
                    )
                )
                return [], True, ""

            total_packages = len(pending)

            report(
                UpdateProgress(
                    phase=UpdatePhase.CHECKING,
                    progress=0.05,
                    message=f"Found {total_packages} update(s)",
                )
            )

            # Get current versions before update (if not already known from checkupdates)
            old_versions = {p.name: p.old_version for p in pending if p.old_version}
            missing_versions = [p.name for p in pending if not p.old_version]
            if missing_versions:
                fetched = await self._get_current_versions(missing_versions)
                old_versions.update(fetched)

            # Build a dict for O(1) matching of pending packages
            pending_by_name: dict[str, Package] = {p.name: p for p in pending}
            # Track which packages have already been added to avoid duplicates
            added_packages: set[str] = set()

            # Run pacman -Syu --noconfirm
            self._process = await asyncio.create_subprocess_exec(
                "sudo",
                "pacman",
                "-Syu",
                "--noconfirm",
                "--color",
                "never",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            stdout = self._process.stdout
            if not stdout:
                return [], False, "Failed to create subprocess stdout pipe"

            current_package = ""
            last_progress_report = 0.0
            in_downloading_phase = False
            download_count = 0

            async for line in read_process_lines(stdout):
                collected_output.append(line)
                if self._logger:
                    self._logger.log(line)

                # Check for "there is nothing to do" message
                if "there is nothing to do" in line.lower():
                    report(
                        UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="All packages up to date",
                        )
                    )
                    await self._process.wait()
                    return [], True, ""

                # Detect phase: ":: Retrieving packages..."
                if (
                    "retrieving packages" in line.lower()
                    or "downloading" in line.lower()
                ):
                    in_downloading_phase = True
                    report(
                        UpdateProgress(
                            phase=UpdatePhase.DOWNLOADING,
                            progress=0.1,
                            message="Downloading packages...",
                        )
                    )
                    continue

                # Detect install phase: "(x/y) upgrading" or "(x/y) installing"
                install_match = re.search(
                    r"^\((\d+)/(\d+)\)\s+(upgrading|installing|reinstalling)\s+(\S+)",
                    line,
                    re.IGNORECASE,
                )
                if install_match:
                    in_downloading_phase = False
                    current_idx = int(install_match.group(1))
                    total_idx = int(install_match.group(2))
                    action = install_match.group(3).lower()
                    pkg_name = install_match.group(4)

                    current_package = pkg_name

                    # Progress: 50-100% for install phase
                    progress = 0.5 + (current_idx / max(total_idx, 1)) * 0.5

                    if progress > last_progress_report + 0.01:
                        last_progress_report = progress
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=progress,
                                total_packages=total_packages,
                                completed_packages=current_idx,
                                current_package=current_package,
                            )
                        )

                    # Track completed packages
                    if action in ("upgrading", "reinstalling"):
                        # O(1) lookup instead of linear scan
                        matched_pkg = pending_by_name.get(pkg_name)
                        if not matched_pkg:
                            # Fallback: check if pkg_name starts with any pending name
                            for p in pending:
                                if pkg_name.startswith(p.name):
                                    matched_pkg = p
                                    break

                        if matched_pkg and matched_pkg.name not in added_packages:
                            added_packages.add(matched_pkg.name)
                            old_ver = old_versions.get(matched_pkg.name, "")
                            packages.append(
                                Package(
                                    name=matched_pkg.name,
                                    old_version=old_ver,
                                    new_version=matched_pkg.new_version,
                                    status=PackageStatus.COMPLETE,
                                )
                            )
                    continue

                # Parse download progress
                download_match = re.search(
                    r"downloading\s+(\S+)", line, re.IGNORECASE
                )
                if download_match and in_downloading_phase:
                    current_package = download_match.group(1)
                    download_count += 1
                    progress = 0.1 + (download_count / max(total_packages, 1)) * 0.4

                    if progress > last_progress_report + 0.01:
                        last_progress_report = progress
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_packages,
                                completed_packages=download_count,
                                current_package=current_package,
                            )
                        )

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

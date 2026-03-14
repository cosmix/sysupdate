"""Snap package manager updater."""

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

# Skip patterns for filtering system/core snaps that shouldn't be shown
SNAP_SKIP_PATTERNS = frozenset([
    "snapd",
    "core",
    "core18",
    "core20",
    "core22",
    "core24",
    "bare",
    "gnome-",
    "gtk-common-themes",
])


class SnapUpdater(BaseUpdater):
    """Updater for Snap packages."""

    @property
    def name(self) -> str:
        return "Snap Packages"

    async def check_available(self) -> bool:
        """Check if Snap is available."""
        return await command_available("which", "snap")

    async def check_updates(self) -> list[Package]:
        """Check for available Snap updates using snap refresh --list."""
        packages: list[Package] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                "snap",
                "refresh",
                "--list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            for line in stdout.decode().splitlines():
                # Skip header line (Name Version Rev Size Publisher Notes)
                if line.startswith("Name") or not line.strip():
                    continue

                # Skip "All snaps up to date" message
                if "All snaps up to date" in line:
                    continue

                # Skip system snaps
                if any(skip in line for skip in SNAP_SKIP_PATTERNS):
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else ""

                    packages.append(
                        Package(
                            name=name,
                            new_version=version,
                        )
                    )

        except FileNotFoundError:
            return []  # Package manager not installed
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error checking updates: {e}")

        return packages

    async def _get_current_versions(self, package_names: list[str]) -> dict[str, str]:
        """Get current installed versions for packages via snap list."""
        versions: dict[str, str] = {}

        try:
            proc = await asyncio.create_subprocess_exec(
                "snap",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            name_set = set(package_names)
            for line in stdout.decode().splitlines():
                if line.startswith("Name") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].strip()
                    if name in name_set:
                        versions[name] = parts[1].strip()
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
        """Run snap refresh command."""
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
                        message="All snaps up to date",
                    )
                )
                return [], True, ""

            total_snaps = len(pending)
            package_names = [p.name for p in pending]

            # Report progress after finding updates (still in checking phase)
            report(
                UpdateProgress(
                    phase=UpdatePhase.CHECKING,
                    progress=0.05,
                    message=f"Found {total_snaps} update(s)",
                )
            )

            # Get current versions before update
            old_versions = await self._get_current_versions(package_names)

            self._process = await asyncio.create_subprocess_exec(
                "snap",
                "refresh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            stdout = self._process.stdout
            if not stdout:
                return [], False, "Failed to create subprocess stdout pipe"

            completed = 0
            current_snap = ""
            last_progress_report = 0.0

            async for line in read_process_lines(stdout):
                collected_output.append(line)
                if self._logger:
                    self._logger.log(line)

                # Check for "All snaps up to date"
                if "All snaps up to date" in line:
                    report(
                        UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="All snaps up to date",
                        )
                    )
                    await self._process.wait()
                    return [], True, ""

                # Parse progress percentage
                progress_match = re.search(r"(\S+)\s+(\d+)\s*%", line)
                if not progress_match:
                    # Fallback: just percentage
                    progress_match = re.search(r"(\d+)\s*%", line)
                    if progress_match:
                        pct = int(progress_match.group(1))
                        snap_in_progress = current_snap
                    else:
                        pct = None
                        snap_in_progress = ""
                else:
                    snap_in_progress = progress_match.group(1)
                    pct = int(progress_match.group(2))
                    # Update current_snap if we extracted a name
                    if snap_in_progress and not any(
                        skip in snap_in_progress for skip in SNAP_SKIP_PATTERNS
                    ):
                        current_snap = snap_in_progress

                if pct is not None:
                    progress = (completed + (pct / 100.0)) / max(total_snaps, 1)
                    if progress > last_progress_report + 0.01:
                        last_progress_report = progress
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_snaps,
                                completed_packages=completed,
                                current_package=current_snap,
                            )
                        )

                # Parse snap completion
                refresh_match = re.match(
                    r"^(\S+)\s+\([^)]+\)\s+(\S+)\s+from\s+.+\s+refreshed", line
                )
                if refresh_match:
                    snap_name = refresh_match.group(1)
                    new_version = refresh_match.group(2)

                    # Skip system snaps
                    if not any(skip in snap_name for skip in SNAP_SKIP_PATTERNS):
                        completed += 1
                        current_snap = snap_name
                        old_version = old_versions.get(snap_name, "")
                        packages.append(
                            Package(
                                name=snap_name,
                                old_version=old_version,
                                new_version=new_version,
                                status=PackageStatus.COMPLETE,
                            )
                        )
                        progress = completed / max(total_snaps, 1)
                        last_progress_report = max(last_progress_report, progress)
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=progress,
                                total_packages=total_snaps,
                                completed_packages=completed,
                                current_package=snap_name,
                            )
                        )

            await self._process.wait()

            if self._process.returncode != 0:
                for line in reversed(collected_output):
                    if "error" in line.lower():
                        error_msg = line
                        break
                if not error_msg:
                    error_msg = "snap refresh failed"
                return [], False, error_msg

            return packages, True, ""

        except Exception as e:
            error_msg = str(e)
            if self._logger:
                self._logger.log(f"Error: {e}")
            return [], False, error_msg

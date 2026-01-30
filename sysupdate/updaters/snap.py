"""Snap package manager updater."""

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

# Skip patterns for filtering system/core snaps that shouldn't be shown
SNAP_SKIP_PATTERNS = frozenset([
    "snapd", "core", "core18", "core20", "core22", "core24", "bare",
    "gnome-", "gtk-common-themes"
])


class SnapUpdater:
    """Updater for Snap packages."""

    name = "Snap Packages"

    def __init__(self) -> None:
        self._logger: UpdateLogger | None = None
        self._process: asyncio.subprocess.Process | None = None

    async def check_available(self) -> bool:
        """Check if Snap is available."""
        return await command_available("which", "snap")

    async def check_updates(self) -> list[Package]:
        """Check for available Snap updates using snap refresh --list."""
        packages: list[Package] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                "snap", "refresh", "--list",
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

                    packages.append(Package(
                        name=name,
                        new_version=version,
                    ))

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
                "snap", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            for line in stdout.decode().splitlines():
                if line.startswith("Name") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].strip()
                    if name in package_names:
                        versions[name] = parts[1].strip()
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
        """Run the Snap update process."""
        result = UpdateResult(success=False)
        self._logger = UpdateLogger("snap")

        # Progress allocation: 0-10% checking, 10-100% installing
        checking_end = 0.1

        def report(progress: UpdateProgress) -> None:
            if callback:
                callback(progress)

        try:
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.0,
                message="Checking for Snap updates...",
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

                packages, success, error = await self._run_snap_refresh(scaled_callback)
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

    async def _run_snap_refresh(
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
                report(UpdateProgress(
                    phase=UpdatePhase.COMPLETE,
                    progress=1.0,
                    message="All snaps up to date",
                ))
                return [], True, ""

            total_snaps = len(pending)
            package_names = [p.name for p in pending]

            # Report progress after finding updates (still in checking phase)
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.05,
                message=f"Found {total_snaps} update(s)",
            ))

            # Get current versions before update
            old_versions = await self._get_current_versions(package_names)

            self._process = await asyncio.create_subprocess_exec(
                "snap", "refresh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            stdout = self._process.stdout
            if not stdout:
                return [], False, "Failed to create subprocess stdout pipe"

            completed = 0
            current_snap = ""
            buffer = ""
            last_progress_report = 0.0

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

                    # Check for "All snaps up to date"
                    if "All snaps up to date" in line:
                        report(UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="All snaps up to date",
                        ))
                        await self._process.wait()
                        return [], True, ""

                    # Parse progress percentage (snap sometimes shows download %)
                    # Try to extract snap name from progress lines like "snap-name 42%"
                    progress_match = re.search(r'(\S+)\s+(\d+)\s*%', line)
                    if not progress_match:
                        # Fallback: just percentage
                        progress_match = re.search(r'(\d+)\s*%', line)
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
                        if snap_in_progress and not any(skip in snap_in_progress for skip in SNAP_SKIP_PATTERNS):
                            current_snap = snap_in_progress

                    if pct is not None:
                        progress = (completed + (pct / 100.0)) / max(total_snaps, 1)
                        # Only report if progress increased (avoid backwards movement)
                        if progress > last_progress_report + 0.01:
                            last_progress_report = progress
                            report(UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_snaps,
                                completed_packages=completed,
                                current_package=current_snap,
                            ))

                    # Parse snap completion: "appname (channel) version from Publisher refreshed"
                    refresh_match = re.match(r'^(\S+)\s+\([^)]+\)\s+(\S+)\s+from\s+.+\s+refreshed', line)
                    if refresh_match:
                        snap_name = refresh_match.group(1)
                        new_version = refresh_match.group(2)

                        # Skip system snaps
                        if not any(skip in snap_name for skip in SNAP_SKIP_PATTERNS):
                            completed += 1
                            current_snap = snap_name
                            old_version = old_versions.get(snap_name, "")
                            packages.append(Package(
                                name=snap_name,
                                old_version=old_version,
                                new_version=new_version,
                                status="complete",
                            ))
                            progress = completed / max(total_snaps, 1)
                            # Update last_progress_report for consistency
                            last_progress_report = max(last_progress_report, progress)
                            report(UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=progress,
                                total_packages=total_snaps,
                                completed_packages=completed,
                                current_package=snap_name,
                            ))

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

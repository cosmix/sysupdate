"""Flatpak package manager updater."""

import asyncio
import os
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
from ..utils.parsing import parse_flatpak_output

# Skip patterns for filtering runtime/extension packages
FLATPAK_SKIP_PATTERNS = frozenset([
    "Locale", "Extension", "Platform", "GL.", "Sdk", "Runtime"
])


class FlatpakUpdater:
    """Updater for Flatpak applications."""

    name = "Flatpak Apps"

    def __init__(self) -> None:
        self._logger: UpdateLogger | None = None
        self._process: asyncio.subprocess.Process | None = None

    async def check_available(self) -> bool:
        """Check if Flatpak is available."""
        return await command_available("which", "flatpak")

    async def check_updates(self) -> list[Package]:
        """Check for available Flatpak updates."""
        packages: list[Package] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                "flatpak", "remote-ls", "--updates",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            for line in stdout.decode().splitlines():
                # Skip technical entries
                if any(skip in line for skip in FLATPAK_SKIP_PATTERNS):
                    continue

                parts = line.split("\t")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    # Get display name from ref
                    display_name = name.split(".")[-1] if "." in name else name
                    branch = parts[1].strip() if len(parts) > 1 else ""

                    packages.append(Package(
                        name=display_name,
                        new_version=branch,
                    ))

        except FileNotFoundError:
            return []  # Package manager not installed
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error checking updates: {e}")

        return packages

    async def run_update(
        self,
        callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> UpdateResult:
        """Run the Flatpak update process."""
        result = UpdateResult(success=False)
        self._logger = UpdateLogger("flatpak")

        # Progress allocation:
        # - Checking: 0% - 10%
        # - Downloading/Installing: 10% - 100%
        checking_end = 0.1

        def report(progress: UpdateProgress) -> None:
            if callback:
                callback(progress)

        try:
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.0,
                message="Checking for Flatpak updates...",
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

                packages, success, error = await self._run_flatpak_update(scaled_callback)
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

    async def _run_flatpak_update(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run flatpak update command.

        Flatpak uses carriage returns for in-place progress updates,
        so we read character-by-character to capture them.
        """
        packages: list[Package] = []
        collected_output: list[str] = []
        error_msg = ""

        try:
            # Disable Flatpak's interactive progress bar to get cleaner output
            env = os.environ.copy()
            # FLATPAK_TTY_MODE=none disables the progress bar
            env["FLATPAK_TTY_MODE"] = "none"

            self._process = await asyncio.create_subprocess_exec(
                "flatpak", "update", "-y", "--noninteractive",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )

            stdout = self._process.stdout
            if not stdout:
                return [], False, "Failed to create subprocess stdout pipe"

            total_apps = 0
            completed = 0
            current_app = ""
            buffer = ""
            last_progress_report = 0.0

            async def read_chunk() -> bytes:
                """Read available data from stdout."""
                return await stdout.read(1024)

            while True:
                chunk = await read_chunk()
                if not chunk:
                    break

                # Decode and process
                text = chunk.decode(errors='replace')
                buffer += text

                # Process complete lines (both \n and \r delimited)
                while '\n' in buffer or '\r' in buffer:
                    # Find the earliest delimiter
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

                    # Log all lines for final parsing
                    collected_output.append(line)
                    if self._logger:
                        self._logger.log(line)

                    # Check for "Nothing to do"
                    if "Nothing to do" in line:
                        report(UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="Already up to date",
                        ))
                        await self._process.wait()
                        return [], True, ""

                    # Count total from numbered list (skip runtimes)
                    numbered_match = re.match(r"^\s*(\d+)\.\s+(\S+)", line)
                    if numbered_match:
                        app_ref = numbered_match.group(2)
                        if not any(skip in app_ref for skip in FLATPAK_SKIP_PATTERNS):
                            total_apps += 1

                    # Parse download progress - multiple patterns
                    # Pattern 1: "Downloading org.app... 45%"
                    # Pattern 2: "[45%] Downloading..."
                    # Pattern 3: "45% complete"
                    download_match = re.search(r"(\d+)\s*%", line)
                    if download_match:
                        pct = int(download_match.group(1))

                        # Try to extract current app name
                        app_match = re.search(
                            r"(?:Downloading|Fetching)\s+([\w.]+)",
                            line
                        )
                        if app_match:
                            ref = app_match.group(1).rstrip(".")
                            current_app = ref.split(".")[-1] if "." in ref else ref

                        # Calculate overall progress
                        if total_apps > 0:
                            # Per-app progress within the total
                            app_progress = pct / 100.0
                            progress = (completed + app_progress) / total_apps
                        else:
                            progress = pct / 100.0

                        # Only report if progress increased (avoid duplicates)
                        if progress > last_progress_report + 0.01:
                            last_progress_report = progress
                            report(UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_apps,
                                completed_packages=completed,
                                current_package=current_app,
                            ))

                    # Detect installation/updating actions
                    action_match = re.search(
                        r"(?:Installing|Updating|Deploying)\s+(\S+)",
                        line
                    )
                    if action_match:
                        app_ref = action_match.group(1)
                        if not any(skip in app_ref for skip in FLATPAK_SKIP_PATTERNS):
                            current_app = app_ref.split(".")[-1]
                            progress = (completed + 0.5) / max(total_apps, 1)
                            report(UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=progress,
                                total_packages=total_apps,
                                completed_packages=completed,
                                current_package=current_app,
                            ))

                    # Count completions
                    if any(marker in line.lower() for marker in ["done", "installed", "updated"]):
                        if not any(skip in line for skip in FLATPAK_SKIP_PATTERNS):
                            completed += 1
                            report(UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=completed / max(total_apps, 1),
                                total_packages=total_apps,
                                completed_packages=completed,
                                current_package=current_app,
                            ))

            await self._process.wait()

            if self._process.returncode != 0:
                for line in reversed(collected_output):
                    if "error" in line.lower():
                        error_msg = line
                        break
                if not error_msg:
                    error_msg = "flatpak update failed"
                return [], False, error_msg

            # Parse final package list
            full_output = "\n".join(collected_output)
            packages = parse_flatpak_output(full_output)

            return packages, True, ""

        except Exception as e:
            error_msg = str(e)
            if self._logger:
                self._logger.log(f"Error: {e}")
            return [], False, error_msg

"""Flatpak package manager updater."""

import asyncio
import os
import re

from .base import (
    BaseUpdater,
    Package,
    UpdateProgress,
    UpdatePhase,
    ProgressCallback,
    read_process_lines,
)
from ..utils import command_available
from ..utils.parsing import parse_flatpak_output

# Skip patterns for filtering runtime/extension packages
FLATPAK_SKIP_PATTERNS = frozenset([
    "Locale",
    "Extension",
    "Platform",
    "GL.",
    "Sdk",
    "Runtime",
])


class FlatpakUpdater(BaseUpdater):
    """Updater for Flatpak applications."""

    @property
    def name(self) -> str:
        return "Flatpak Apps"

    async def check_available(self) -> bool:
        """Check if Flatpak is available."""
        return await command_available("which", "flatpak")

    async def check_updates(self) -> list[Package]:
        """Check for available Flatpak updates."""
        packages: list[Package] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                "flatpak",
                "remote-ls",
                "--updates",
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

                    packages.append(
                        Package(
                            name=display_name,
                            new_version=branch,
                        )
                    )

        except FileNotFoundError:
            return []  # Package manager not installed
        except Exception as e:
            if self._logger:
                self._logger.log(f"Error checking updates: {e}")

        return packages

    async def _do_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run flatpak update command.

        Flatpak uses carriage returns for in-place progress updates,
        so we use read_process_lines which handles both \\n and \\r.
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
                "flatpak",
                "update",
                "-y",
                "--noninteractive",
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
            last_progress_report = 0.0

            async for line in read_process_lines(stdout):
                # Log all lines for final parsing
                collected_output.append(line)
                if self._logger:
                    self._logger.log(line)

                # Check for "Nothing to do"
                if "Nothing to do" in line:
                    report(
                        UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="Already up to date",
                        )
                    )
                    await self._process.wait()
                    return [], True, ""

                # Count total from numbered list (skip runtimes)
                numbered_match = re.match(r"^\s*(\d+)\.\s+(\S+)", line)
                if numbered_match:
                    app_ref = numbered_match.group(2)
                    if not any(skip in app_ref for skip in FLATPAK_SKIP_PATTERNS):
                        total_apps += 1

                # Parse download progress - multiple patterns
                download_match = re.search(r"(\d+)\s*%", line)
                if download_match:
                    pct = int(download_match.group(1))

                    # Try to extract current app name
                    app_match = re.search(
                        r"(?:Downloading|Fetching)\s+([\w.]+)", line
                    )
                    if app_match:
                        ref = app_match.group(1).rstrip(".")
                        current_app = ref.split(".")[-1] if "." in ref else ref

                    # Calculate overall progress
                    if total_apps > 0:
                        app_progress = pct / 100.0
                        progress = (completed + app_progress) / total_apps
                    else:
                        progress = pct / 100.0

                    if progress > last_progress_report + 0.01:
                        last_progress_report = progress
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_apps,
                                completed_packages=completed,
                                current_package=current_app,
                            )
                        )

                # Detect installation/updating actions
                action_match = re.search(
                    r"(?:Installing|Updating|Deploying)\s+(\S+)", line
                )
                if action_match:
                    app_ref = action_match.group(1)
                    if not any(skip in app_ref for skip in FLATPAK_SKIP_PATTERNS):
                        current_app = app_ref.split(".")[-1]
                        progress = (completed + 0.5) / max(total_apps, 1)
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=progress,
                                total_packages=total_apps,
                                completed_packages=completed,
                                current_package=current_app,
                            )
                        )

                # Count completions
                if any(
                    marker in line.lower()
                    for marker in ["done", "installed", "updated"]
                ):
                    if not any(skip in line for skip in FLATPAK_SKIP_PATTERNS):
                        completed += 1
                        report(
                            UpdateProgress(
                                phase=UpdatePhase.INSTALLING,
                                progress=completed / max(total_apps, 1),
                                total_packages=total_apps,
                                completed_packages=completed,
                                current_package=current_app,
                            )
                        )

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

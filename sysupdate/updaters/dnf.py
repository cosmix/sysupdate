"""DNF package manager updater."""

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


class DnfUpdater:
    """Updater for DNF packages."""

    name = "DNF Packages"

    def __init__(self) -> None:
        self._logger: UpdateLogger | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._dnf_command: str = "dnf"

    async def check_available(self) -> bool:
        """Check if DNF is available (prefers dnf5 over dnf)."""
        if await command_available("which", "dnf5"):
            self._dnf_command = "dnf5"
            return True
        if await command_available("which", "dnf"):
            self._dnf_command = "dnf"
            return True
        return False

    async def check_updates(self) -> list[Package]:
        """Check for available DNF updates using dnf check-update."""
        packages: list[Package] = []

        try:
            proc = await asyncio.create_subprocess_exec(
                self._dnf_command, "check-update",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            # DNF returns exit code 100 when updates are available, 0 when none
            # Both are "success" states for our purposes
            if proc.returncode not in (0, 100):
                return []

            # Parse output format: package.arch    version    repository
            # Skip blank lines and header-like content
            for line in stdout.decode().splitlines():
                line = line.strip()
                if not line:
                    continue

                # Skip informational lines (last metadata check, etc.)
                if "Last metadata expiration" in line or "Metadata cache created" in line:
                    continue

                parts = line.split()
                # Valid update line has at least 3 parts: name.arch, version, repo
                if len(parts) >= 3:
                    # Package name may include arch suffix like "package.x86_64"
                    name = parts[0].strip()
                    version = parts[1].strip()

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
        """Get current installed versions for packages via dnf list installed."""
        versions: dict[str, str] = {}

        try:
            proc = await asyncio.create_subprocess_exec(
                self._dnf_command, "list", "installed",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            for line in stdout.decode().splitlines():
                line = line.strip()
                if not line:
                    continue

                # Skip informational lines
                if "Installed Packages" in line or "Last metadata" in line:
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].strip()
                    # Match against the full name (with arch suffix) or base name
                    if name in package_names or any(name.startswith(pkg.split('.')[0]) for pkg in package_names):
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
        """Run the DNF update process."""
        result = UpdateResult(success=False)
        self._logger = UpdateLogger("dnf")

        # Progress allocation: 0-10% checking, 10-100% installing
        checking_end = 0.1

        def report(progress: UpdateProgress) -> None:
            if callback:
                callback(progress)

        try:
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.0,
                message="Checking for DNF updates...",
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

                packages, success, error = await self._run_dnf_upgrade(scaled_callback)
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

    async def _run_dnf_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Run dnf upgrade command."""
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

            # Report progress after finding updates (still in checking phase)
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.05,
                message=f"Found {total_packages} update(s)",
            ))

            # Get current versions before update
            old_versions = await self._get_current_versions(package_names)

            self._process = await asyncio.create_subprocess_exec(
                self._dnf_command, "upgrade", "-y",
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

                    # Check for "Nothing to do" message
                    if "Nothing to do" in line:
                        report(UpdateProgress(
                            phase=UpdatePhase.COMPLETE,
                            progress=1.0,
                            message="All packages up to date",
                        ))
                        await self._process.wait()
                        return [], True, ""

                    # Detect phase transitions
                    if "Downloading Packages:" in line:
                        in_downloading_phase = True
                        report(UpdateProgress(
                            phase=UpdatePhase.DOWNLOADING,
                            progress=0.1,
                            message="Downloading packages...",
                        ))
                        continue

                    if "Installing:" in line or "Upgrading:" in line:
                        in_downloading_phase = False
                        report(UpdateProgress(
                            phase=UpdatePhase.INSTALLING,
                            progress=0.5,
                            message="Installing packages...",
                        ))
                        continue

                    # Parse download progress lines: (1/5): package-1.2.3.rpm  100% | 2.3 MB/s |  15 MB  00:06
                    download_match = re.search(r'\((\d+)/(\d+)\):\s*(\S+)\s+(\d+)\s*%', line)
                    if download_match and in_downloading_phase:
                        current_idx = int(download_match.group(1))
                        total_idx = int(download_match.group(2))
                        package_file = download_match.group(3)
                        pct = int(download_match.group(4))

                        # Extract package name from filename (remove .rpm and version)
                        pkg_name_match = re.match(r'^(.+?)-[0-9]', package_file)
                        if pkg_name_match:
                            current_package = pkg_name_match.group(1)

                        # Progress calculation: use current package index and percentage
                        progress = (current_idx - 1 + pct / 100.0) / max(total_idx, 1)
                        # Scale to 0.1-0.5 (downloading phase)
                        progress = 0.1 + (progress * 0.4)

                        if progress > last_progress_report + 0.01:
                            last_progress_report = progress
                            report(UpdateProgress(
                                phase=UpdatePhase.DOWNLOADING,
                                progress=progress,
                                total_packages=total_packages,
                                completed_packages=completed,
                                current_package=current_package,
                            ))

                    # Parse completion lines: "Upgraded: package-name-1.2.3-1.fc39.x86_64"
                    if line.startswith("Upgraded:") or line.startswith("Installed:"):
                        # Extract package name from versioned string
                        upgraded_match = re.search(r'^(Upgraded|Installed):\s+(\S+)', line)
                        if upgraded_match:
                            full_name = upgraded_match.group(2)
                            # Parse package name: remove version/release/arch suffixes
                            # Example: "package-name-1.2.3-1.fc39.x86_64" -> "package-name"
                            pkg_name_match = re.match(r'^(.+?)-[0-9]', full_name)
                            if pkg_name_match:
                                pkg_name = pkg_name_match.group(1)
                            else:
                                pkg_name = full_name

                            # Find matching package from pending list
                            matched_pkg = None
                            for p in pending:
                                if p.name.startswith(pkg_name) or pkg_name in p.name:
                                    matched_pkg = p
                                    break

                            if matched_pkg:
                                completed += 1
                                current_package = matched_pkg.name
                                old_version = old_versions.get(matched_pkg.name, "")
                                packages.append(Package(
                                    name=matched_pkg.name,
                                    old_version=old_version,
                                    new_version=matched_pkg.new_version,
                                    status="complete",
                                ))
                                progress = 0.5 + (completed / max(total_packages, 1)) * 0.5
                                last_progress_report = max(last_progress_report, progress)
                                report(UpdateProgress(
                                    phase=UpdatePhase.INSTALLING,
                                    progress=progress,
                                    total_packages=total_packages,
                                    completed_packages=completed,
                                    current_package=current_package,
                                ))

            await self._process.wait()

            if self._process.returncode != 0:
                for line in reversed(collected_output):
                    if "error" in line.lower() or "failed" in line.lower():
                        error_msg = line
                        break
                if not error_msg:
                    error_msg = f"{self._dnf_command} upgrade failed"
                return [], False, error_msg

            return packages, True, ""

        except Exception as e:
            error_msg = str(e)
            if self._logger:
                self._logger.log(f"Error: {e}")
            return [], False, error_msg

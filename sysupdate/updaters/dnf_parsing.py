"""DNF-specific progress tracking and output parsing."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Package

# DNF-specific regex patterns
_DNF_PKG_PATTERN = re.compile(r"^(\S+)\.(\S+)\s+(\S+)\s+(\S+)")
_DNF_DOWNLOAD_PATTERN = re.compile(r"\((\d+)/(\d+)\):\s+(\S+)")
_DNF_UPGRADING_PATTERN = re.compile(r"^\s+Upgrading\s+:\s+(\S+)")
_DNF_COMPLETED_LINE_PATTERN = re.compile(r"^(Upgraded|Installed):")


def parse_dnf_check_output(output: str) -> list[Package]:
    """Parse DNF check-update output to extract package information.

    Looks for patterns like:
    - "package.arch    version    repository"

    Args:
        output: Raw DNF check-update output text

    Returns:
        List of Package objects
    """
    # Import here to avoid circular dependency
    from .base import Package, PackageStatus

    packages: dict[str, Package] = {}

    for line in output.splitlines():
        # Skip empty lines and metadata lines
        if not line.strip() or line.startswith("Last metadata"):
            continue

        # Skip header separator lines
        if line.strip().startswith("===") or line.strip().startswith("---"):
            continue

        # Check for package line format: package.arch version repository
        match = _DNF_PKG_PATTERN.match(line)
        if match:
            name, arch, version, repository = match.groups()
            # Store with original name (without arch), version is new_version
            packages[name] = Package(
                name=name,
                new_version=version,
                status=PackageStatus.PENDING,
            )

    return list(packages.values())


class DnfUpgradeProgressTracker:
    """Tracks progress during dnf upgrade by parsing output lines.

    This class encapsulates the state and logic for tracking DNF upgrade progress,
    parsing lines to detect downloads and installation phases.

    Progress is allocated as follows:
    - Downloading: 0-50%
    - Installing: 50-100%

    Handles edge cases:
    - Unknown total: Uses estimation based on seen package count
    - Multiple packages in transaction: Tracks progress through download/install phases
    """

    def __init__(self) -> None:
        """Initialize the progress tracker."""
        self.total_packages = 0
        self.download_count = 0
        self.install_count = 0
        self.current_package = ""
        self.last_progress = 0.0
        self._in_download_phase = False
        self._in_install_phase = False
        self._download_total = 0

    def parse_line(self, line: str) -> dict | None:
        """Parse a line of dnf output and return progress info if applicable.

        Args:
            line: A single line of dnf output.

        Returns:
            Dict with keys: phase, progress, current_package, total_packages,
            completed_packages, message. Returns None if no progress update.
        """
        # Check for "Downloading Packages:" header
        if "Downloading Packages:" in line:
            self._in_download_phase = True
            return {
                "phase": "downloading",
                "progress": 0.0,
                "current_package": "",
                "total_packages": self.total_packages,
                "completed_packages": 0,
                "message": "Starting download...",
            }

        # Check for download progress: (1/5): package-name
        download_match = _DNF_DOWNLOAD_PATTERN.search(line)
        if download_match and self._in_download_phase:
            current = int(download_match.group(1))
            total = int(download_match.group(2))
            pkg_name = download_match.group(3)

            # Extract package name from filename (e.g., package-1.0.rpm -> package)
            if pkg_name.endswith(".rpm"):
                pkg_name = pkg_name[:-4]
            # Remove version info - split on first dash if present
            if "-" in pkg_name:
                pkg_name = pkg_name.rsplit("-", 2)[0]

            self.download_count = current
            self._download_total = total
            self.total_packages = total
            self.current_package = pkg_name

            # Progress: downloading is 0-50%
            progress = (current / total) * 0.5
            if progress > self.last_progress:
                self.last_progress = progress
                return {
                    "phase": "downloading",
                    "progress": progress,
                    "current_package": self.current_package,
                    "total_packages": self.total_packages,
                    "completed_packages": current,
                }

        # Check for install/upgrade phase - only "Running transaction", not "Upgrading"
        # (Upgrading appears in transaction summary before downloads)
        if "Running transaction" in line:
            if not self._in_install_phase:
                self._in_install_phase = True
                # If we never tracked downloads, start at 50%
                if self.last_progress < 0.5:
                    self.last_progress = 0.5
                return {
                    "phase": "installing",
                    "progress": 0.5,
                    "current_package": "",
                    "total_packages": self.total_packages,
                    "completed_packages": 0,
                    "message": "Installing packages...",
                }

        # Track individual package upgrades during transaction
        # Format: "  Upgrading        : package-version.arch                          N/M"
        upgrading_match = _DNF_UPGRADING_PATTERN.search(line)
        if upgrading_match and self._in_install_phase:
            pkg_name = upgrading_match.group(1)
            # Remove version info from package name
            if "-" in pkg_name:
                pkg_name = pkg_name.rsplit("-", 2)[0]

            self.install_count += 1
            self.current_package = pkg_name

            if self.total_packages > 0:
                # Progress: installing is 50-100%
                progress = 0.5 + (self.install_count / self.total_packages) * 0.5
                if progress > self.last_progress:
                    self.last_progress = progress
                    return {
                        "phase": "installing",
                        "progress": progress,
                        "current_package": self.current_package,
                        "total_packages": self.total_packages,
                        "completed_packages": self.install_count,
                    }

        # Check for completion line "Upgraded:" or "Installed:"
        # This marks the summary at the end
        if _DNF_COMPLETED_LINE_PATTERN.match(line):
            # If we haven't reached 100% yet, do so now
            if self.last_progress < 1.0:
                self.last_progress = 0.99
                return {
                    "phase": "installing",
                    "progress": 0.99,
                    "current_package": "",
                    "total_packages": self.total_packages,
                    "completed_packages": self.total_packages,
                    "message": "Finalizing...",
                }

        # Check for completion
        if "Complete!" in line:
            return {
                "phase": "complete",
                "progress": 1.0,
                "current_package": "",
                "total_packages": self.total_packages,
                "completed_packages": self.total_packages,
                "message": "Update complete",
            }

        return None

"""Output parsing utilities for APT and Flatpak."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..updaters.base import Package

# Import at runtime to avoid circular import - use lazy import in function
# FLATPAK_SKIP_PATTERNS will be imported from flatpak module when needed


# Precompiled regex patterns for performance
_UNPACK_PATTERN = re.compile(r"Unpacking\s+(\S+)\s+\(([^)]+)\)\s+over\s+\(([^)]+)\)")
_SETUP_PATTERN = re.compile(r"Setting up\s+(\S+)\s+\(([^)]+)\)")
_NUMBERED_PATTERN = re.compile(r"^\s*\d+\.\s+(\S+)\s+(\S+)(?:\s+(\S+))?")
_ACTION_PATTERN = re.compile(r"(?:Installing|Updating)\s+(\S+)")
_COUNT_PATTERN = re.compile(r"(\d+)\s+upgraded")
_GET_PATTERN = re.compile(r"Get:(\d+)\s+\S+\s+(\S+)\s+")
_UNPACK_SIMPLE_PATTERN = re.compile(r"Unpacking\s+(\S+)")
_SETUP_SIMPLE_PATTERN = re.compile(r"Setting up\s+(\S+)")
_TRIGGER_PATTERN = re.compile(r"Processing triggers for\s+(\S+)")


def parse_apt_output(output: str) -> list[Package]:
    """
    Parse APT output to extract package information.

    Looks for patterns like:
    - "Unpacking package (version) over (old_version)"
    - "Setting up package (version)"

    Args:
        output: Raw APT output text

    Returns:
        List of Package objects
    """
    # Import here to avoid circular dependency
    from ..updaters.base import Package

    packages: dict[str, Package] = {}

    for line in output.splitlines():
        # Check for unpack line (has old and new version)
        match = _UNPACK_PATTERN.search(line)
        if match:
            name, new_ver, old_ver = match.groups()
            # Remove architecture suffix like :amd64
            name = name.split(":")[0]
            packages[name] = Package(
                name=name,
                old_version=old_ver,
                new_version=new_ver,
                status="complete"
            )
            continue

        # Check for setup line (only has new version)
        match = _SETUP_PATTERN.search(line)
        if match:
            name, version = match.groups()
            name = name.split(":")[0]
            if name not in packages:
                packages[name] = Package(
                    name=name,
                    new_version=version,
                    status="complete"
                )

    return list(packages.values())


def parse_flatpak_output(output: str) -> list[Package]:
    """
    Parse Flatpak output to extract application information.

    Looks for patterns like:
    - Numbered list: "1. org.mozilla.Firefox stable"
    - Tab-separated: "org.mozilla.Firefox\tstable\t124.5 MB"

    Args:
        output: Raw Flatpak output text

    Returns:
        List of Package objects
    """
    # Import here to avoid circular dependency
    from ..updaters.base import Package
    from ..updaters.flatpak import FLATPAK_SKIP_PATTERNS

    packages: dict[str, Package] = {}

    for line in output.splitlines():
        # Skip runtime/extension lines
        if any(skip in line for skip in FLATPAK_SKIP_PATTERNS):
            continue

        # Check numbered list format
        match = _NUMBERED_PATTERN.match(line)
        if match:
            name, branch = match.group(1), match.group(2)
            size = match.group(3) or ""

            # Extract readable name from ref (last part)
            display_name = name.split(".")[-1] if "." in name else name

            packages[name] = Package(
                name=display_name,
                new_version=branch,
                size=size,
                status="complete"
            )
            continue

        # Check action line format
        match = _ACTION_PATTERN.search(line)
        if match:
            name = match.group(1)
            display_name = name.split(".")[-1] if "." in name else name
            if name not in packages:
                packages[name] = Package(
                    name=display_name,
                    status="complete"
                )

    return list(packages.values())


class AptUpgradeProgressTracker:
    """Tracks progress during apt upgrade by parsing output lines.

    This class encapsulates the state and logic for tracking APT upgrade progress,
    parsing lines to detect downloads, unpacking, and installation phases.

    Progress is allocated as follows:
    - Normal mode: Downloading 0-50%, Installing 50-100%
    - Cache mode (no downloads): Unpacking 0-50%, Installing 50-100%

    Handles edge cases:
    - Unknown total: Uses estimation based on seen package count
    - Cached packages: Detects when packages are installed from cache
    """

    def __init__(self) -> None:
        """Initialize the progress tracker."""
        self.total_packages = 0
        self.download_count = 0
        self.install_count = 0
        self.unpack_count = 0
        self.current_package = ""
        self.last_progress = 0.0
        self._is_up_to_date = False
        self._pending_downloads: list[str] = []  # Track downloads before total known
        self._using_cache = False  # True if packages come from cache (no downloads)
        self._first_unpack_seen = False

    def parse_line(self, line: str) -> dict | None:
        """Parse a line of apt output and return progress info if applicable.

        Args:
            line: A single line of apt output.

        Returns:
            Dict with keys: phase, progress, current_package, total_packages,
            completed_packages, message. Returns None if no progress update.
        """
        # Check for total package count from summary line
        count_match = _COUNT_PATTERN.search(line)
        if count_match:
            new_total = int(count_match.group(1))
            if new_total > 0:
                self.total_packages = new_total
                # If we had pending downloads, recalculate and report progress
                if self._pending_downloads:
                    self.download_count = len(self._pending_downloads)
                    progress = (self.download_count / self.total_packages) * 0.5
                    if progress > self.last_progress:
                        self.last_progress = progress
                        return {
                            "phase": "downloading",
                            "progress": progress,
                            "current_package": self.current_package,
                            "total_packages": self.total_packages,
                            "completed_packages": self.download_count,
                        }

        # Check for "already up to date"
        if "up to date" in line.lower():
            self._is_up_to_date = True
            return {
                "phase": "complete",
                "progress": 1.0,
                "message": "Already up to date",
            }

        # Track download progress via Get: lines
        get_match = _GET_PATTERN.match(line)
        if get_match:
            pkg_num = int(get_match.group(1))
            self.download_count = pkg_num
            self.current_package = get_match.group(2).split(":")[0]

            if self.total_packages > 0:
                progress = (self.download_count / self.total_packages) * 0.5
                if progress > self.last_progress:
                    self.last_progress = progress
                    return {
                        "phase": "downloading",
                        "progress": progress,
                        "current_package": self.current_package,
                        "total_packages": self.total_packages,
                        "completed_packages": self.download_count,
                    }
            else:
                # Total not yet known - track and use estimated progress
                self._pending_downloads.append(self.current_package)
                # Conservative estimate: assume at least 2 more packages
                estimated = max(pkg_num + 2, len(self._pending_downloads) + 2)
                progress = (pkg_num / estimated) * 0.4  # Cap at 40% until total known
                if progress > self.last_progress:
                    self.last_progress = progress
                    return {
                        "phase": "downloading",
                        "progress": progress,
                        "current_package": self.current_package,
                        "total_packages": 0,  # Unknown
                        "completed_packages": pkg_num,
                        "message": f"Downloading {self.current_package}...",
                    }

        # Track unpacking progress
        unpack_match = _UNPACK_SIMPLE_PATTERN.search(line)
        if unpack_match:
            self.current_package = unpack_match.group(1).split(":")[0]
            self.unpack_count += 1

            if not self._first_unpack_seen:
                self._first_unpack_seen = True
                # If we never saw downloads but are unpacking, packages were cached
                if self.download_count == 0 and self.total_packages > 0:
                    self._using_cache = True
                    # Start at 0% for unpacking phase in cache mode
                    self.last_progress = 0.0

            # Report unpacking progress if using cache
            if self._using_cache and self.total_packages > 0:
                # In cache mode: unpacking is 0-50%, setting up is 50-100%
                progress = (self.unpack_count / self.total_packages) * 0.5
                if progress > self.last_progress:
                    self.last_progress = progress
                    return {
                        "phase": "installing",
                        "progress": progress,
                        "current_package": self.current_package,
                        "total_packages": self.total_packages,
                        "completed_packages": self.unpack_count,
                        "message": f"Unpacking {self.current_package}...",
                    }

        # Track installation progress via Setting up lines
        setup_match = _SETUP_SIMPLE_PATTERN.search(line)
        if setup_match:
            self.install_count += 1
            self.current_package = setup_match.group(1).split(":")[0]

            if self.total_packages > 0:
                if self._using_cache:
                    # Cache mode: unpacking 0-50%, setting up 50-100%
                    progress = 0.5 + (self.install_count / self.total_packages) * 0.5
                else:
                    # Normal mode: downloading 0-50%, setting up 50-100%
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
            elif self.install_count > 0:
                # Total not known, but we're installing - estimate progress
                estimated = max(self.install_count + 2, self.unpack_count)
                progress = 0.5 + (self.install_count / estimated) * 0.4
                if progress > self.last_progress:
                    self.last_progress = progress
                    return {
                        "phase": "installing",
                        "progress": progress,
                        "current_package": self.current_package,
                        "total_packages": 0,
                        "completed_packages": self.install_count,
                    }

        # Track processing triggers
        trigger_match = _TRIGGER_PATTERN.search(line)
        if trigger_match:
            self.current_package = trigger_match.group(1).split(":")[0]
            progress = 0.95 + (self.install_count / max(self.total_packages, 1)) * 0.05
            if progress > self.last_progress and progress <= 1.0:
                self.last_progress = progress
                return {
                    "phase": "installing",
                    "progress": min(progress, 0.99),
                    "current_package": self.current_package,
                    "total_packages": self.total_packages,
                    "completed_packages": self.install_count,
                    "message": "Processing triggers...",
                }

        return None

    @property
    def is_up_to_date(self) -> bool:
        """Check if the system was already up to date."""
        return self._is_up_to_date


class AptUpdateProgressTracker:
    """Tracks progress during apt update by counting repository lines.

    During 'apt update', APT outputs lines like:
    - "Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease"
    - "Get:2 http://security.ubuntu.com/ubuntu jammy-security InRelease [110 kB]"

    This class counts these lines to provide progress updates during the
    checking phase, which otherwise would show 0% until complete.
    """

    def __init__(self, estimated_repos: int = 10) -> None:
        """Initialize the progress tracker.

        Args:
            estimated_repos: Estimated number of repositories. Used for
                initial progress calculation before we know the actual count.
        """
        self.estimated_repos = estimated_repos
        self.seen_repos = 0
        self.last_progress = 0.0

    def parse_line(self, line: str) -> float | None:
        """Parse a line and return progress (0.0-1.0) if applicable.

        Args:
            line: A single line of apt update output.

        Returns:
            Progress value (0.0-0.95) if this line indicates a repository
            being checked, None otherwise. Never returns 1.0 as completion
            is signaled separately when the process exits successfully.
        """
        if line.startswith("Hit:") or line.startswith("Get:"):
            self.seen_repos += 1
            # Use asymptotic approach: never claim 100% until done
            # As we see more repos, we increase our estimate
            estimated = max(self.estimated_repos, self.seen_repos + 2)
            progress = min(0.95, self.seen_repos / estimated)
            if progress > self.last_progress:
                self.last_progress = progress
                return progress
        return None

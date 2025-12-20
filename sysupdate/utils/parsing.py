"""Output parsing utilities for APT and Flatpak."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..updaters.base import Package


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

    # Pattern for "Unpacking package (new_version) over (old_version)"
    unpack_pattern = re.compile(
        r"Unpacking\s+(\S+)\s+\(([^)]+)\)\s+over\s+\(([^)]+)\)"
    )

    # Pattern for "Setting up package (version)"
    setup_pattern = re.compile(
        r"Setting up\s+(\S+)\s+\(([^)]+)\)"
    )

    for line in output.splitlines():
        # Check for unpack line (has old and new version)
        match = unpack_pattern.search(line)
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
        match = setup_pattern.search(line)
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


def parse_apt_progress(line: str) -> tuple[str, float] | None:
    """
    Parse APT progress from a line of output.

    APT can output progress like:
    - "Progress: [ 45%]"
    - "Get:1 http://... package 123 kB"

    Args:
        line: Single line of APT output

    Returns:
        Tuple of (current_package, progress) or None
    """
    # Progress percentage pattern
    progress_match = re.search(r"Progress:\s*\[\s*(\d+)%\]", line)
    if progress_match:
        return ("", int(progress_match.group(1)) / 100.0)

    # Download line pattern
    get_match = re.search(r"Get:\d+\s+\S+\s+(\S+)", line)
    if get_match:
        return (get_match.group(1), -1.0)  # -1 means unknown progress

    # Unpacking line
    unpack_match = re.search(r"Unpacking\s+(\S+)", line)
    if unpack_match:
        return (unpack_match.group(1).split(":")[0], -1.0)

    # Setting up line
    setup_match = re.search(r"Setting up\s+(\S+)", line)
    if setup_match:
        return (setup_match.group(1).split(":")[0], -1.0)

    return None


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

    packages: dict[str, Package] = {}

    # Skip runtimes, locales, extensions
    skip_patterns = ["Locale", "Extension", "Platform", "GL.", "Sdk"]

    # Pattern for numbered list format
    numbered_pattern = re.compile(
        r"^\s*\d+\.\s+(\S+)\s+(\S+)(?:\s+(\S+))?"
    )

    # Pattern for update/install lines
    action_pattern = re.compile(
        r"(?:Updating|Installing)\s+(\S+)"
    )

    for line in output.splitlines():
        # Skip runtime/extension lines
        if any(skip in line for skip in skip_patterns):
            continue

        # Check numbered list format
        match = numbered_pattern.match(line)
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
        match = action_pattern.search(line)
        if match:
            name = match.group(1)
            display_name = name.split(".")[-1] if "." in name else name
            if name not in packages:
                packages[name] = Package(
                    name=display_name,
                    status="complete"
                )

    return list(packages.values())


def parse_flatpak_progress(line: str) -> tuple[str, float] | None:
    """
    Parse Flatpak progress from a line of output.

    Args:
        line: Single line of Flatpak output

    Returns:
        Tuple of (current_app, progress) or None
    """
    # Downloading pattern with percentage
    download_match = re.search(
        r"Downloading\s+([\w.]+).*?(\d+)%",
        line
    )
    if download_match:
        name = download_match.group(1).rstrip(".")
        name = name.split(".")[-1] if "." in name else name
        progress = int(download_match.group(2)) / 100.0
        return (name, progress)

    # Installing/Updating action
    action_match = re.search(
        r"(?:Installing|Updating)\s+(\S+)",
        line
    )
    if action_match:
        name = action_match.group(1).split(".")[-1]
        return (name, -1.0)

    return None


def count_apt_upgrades(output: str) -> int:
    """
    Count the number of packages to be upgraded from APT output.

    Args:
        output: APT update/upgrade output

    Returns:
        Number of packages to upgrade
    """
    # Pattern: "X upgraded, Y newly installed"
    match = re.search(r"(\d+)\s+upgraded", output)
    if match:
        return int(match.group(1))

    # Alternative: count "Setting up" lines
    setting_up = len(re.findall(r"Setting up\s+\S+", output))
    if setting_up > 0:
        return setting_up

    # Check for "All packages are up to date"
    if "up to date" in output.lower():
        return 0

    return 0


class AptUpgradeProgressTracker:
    """Tracks progress during apt upgrade by parsing output lines.

    This class encapsulates the state and logic for tracking APT upgrade progress,
    parsing lines to detect downloads, unpacking, and installation phases.
    """

    def __init__(self) -> None:
        """Initialize the progress tracker."""
        self.total_packages = 0
        self.download_count = 0
        self.install_count = 0
        self.current_package = ""
        self.last_progress = 0.0
        self._is_up_to_date = False

    def parse_line(self, line: str) -> dict | None:
        """Parse a line of apt output and return progress info if applicable.

        Args:
            line: A single line of apt output.

        Returns:
            Dict with keys: phase, progress, current_package, total_packages,
            completed_packages, message. Returns None if no progress update.
        """
        # Check for total package count from summary line
        count_match = re.search(r"(\d+)\s+upgraded", line)
        if count_match:
            self.total_packages = int(count_match.group(1))

        # Check for "already up to date"
        if "up to date" in line.lower():
            self._is_up_to_date = True
            return {
                "phase": "complete",
                "progress": 1.0,
                "message": "Already up to date",
            }

        # Track download progress via Get: lines
        get_match = re.match(r"Get:(\d+)\s+\S+\s+(\S+)\s+", line)
        if get_match:
            self.download_count = int(get_match.group(1))
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

        # Track unpacking progress
        unpack_match = re.search(r"Unpacking\s+(\S+)", line)
        if unpack_match:
            self.current_package = unpack_match.group(1).split(":")[0]
            # Don't return here, just update state

        # Track installation progress via Setting up lines
        setup_match = re.search(r"Setting up\s+(\S+)", line)
        if setup_match:
            self.install_count += 1
            self.current_package = setup_match.group(1).split(":")[0]

            if self.total_packages > 0:
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

        # Track processing triggers
        trigger_match = re.search(r"Processing triggers for\s+(\S+)", line)
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


def parse_aria2_progress(line: str) -> tuple[str, float, str, str] | None:
    """
    Parse aria2c progress from output line.

    aria2c outputs lines like:
    - "[#abc123 50% CN:5 DL:2.5MiB/s ETA:30s]"
    - "[#def456 100%]"
    - "Download complete: /path/to/file.deb"

    Args:
        line: Single line of aria2c output

    Returns:
        Tuple of (gid, progress, speed, eta) or None if not a progress line.
        gid is the download ID (e.g., "abc123")
        progress is 0.0-1.0
        speed is string like "2.5MiB/s" or ""
        eta is string like "30s" or ""
    """
    # Progress line pattern: [#abc123 50% CN:5 DL:2.5MiB/s ETA:30s]
    progress_pattern = re.compile(
        r"\[#([a-f0-9]+)\s+(\d+)%(?:.*?DL:(\S+))?(?:.*?ETA:(\S+))?\]"
    )

    match = progress_pattern.search(line)
    if match:
        gid = match.group(1)
        progress = int(match.group(2)) / 100.0
        speed = match.group(3) or ""
        eta = match.group(4) or ""
        return (gid, progress, speed, eta)

    # Complete line pattern: Download complete: /path/to/file.deb
    complete_pattern = re.compile(r"Download complete:\s*(\S+)")

    match = complete_pattern.search(line)
    if match:
        filepath = match.group(1)
        # Extract GID from filepath if it contains it, otherwise use the path
        # For completed downloads, return 100% progress
        gid = filepath.split("/")[-1]  # Use filename as identifier
        return (gid, 1.0, "", "")

    return None

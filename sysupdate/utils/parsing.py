"""Output parsing utilities for APT and Flatpak."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..updaters.base import Package

# Import at runtime to avoid circular import - use lazy import in function
# FLATPAK_SKIP_PATTERNS will be imported from flatpak module when needed


# Precompiled regex patterns shared by APT output parsing
_UNPACK_PATTERN = re.compile(r"Unpacking\s+(\S+)\s+\(([^)]+)\)\s+over\s+\(([^)]+)\)")
_SETUP_PATTERN = re.compile(r"Setting up\s+(\S+)\s+\(([^)]+)\)")
_NUMBERED_PATTERN = re.compile(r"^\s*\d+\.\s+(\S+)\s+(\S+)(?:\s+(\S+))?")
_ACTION_PATTERN = re.compile(r"(?:Installing|Updating)\s+(\S+)")


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
    from ..updaters.base import Package, PackageStatus

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
                status=PackageStatus.COMPLETE,
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
                    status=PackageStatus.COMPLETE,
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
    from ..updaters.base import Package, PackageStatus
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
                status=PackageStatus.COMPLETE,
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
                    status=PackageStatus.COMPLETE,
                )

    return list(packages.values())


# Re-exports for backwards compatibility: test imports and other modules that
# import these classes from sysupdate.utils.parsing will continue to work.
# Lazy imports via __getattr__ to avoid circular import with updaters package.
_COMPAT_REEXPORTS = {
    "AptUpgradeProgressTracker": ("sysupdate.updaters.apt_parsing", "AptUpgradeProgressTracker"),
    "AptUpdateProgressTracker": ("sysupdate.updaters.apt_parsing", "AptUpdateProgressTracker"),
    "DnfUpgradeProgressTracker": ("sysupdate.updaters.dnf_parsing", "DnfUpgradeProgressTracker"),
    "parse_dnf_check_output": ("sysupdate.updaters.dnf_parsing", "parse_dnf_check_output"),
}


def __getattr__(name: str):  # noqa: E302
    """Lazy re-exports for backwards compatibility."""
    if name in _COMPAT_REEXPORTS:
        module_path, attr_name = _COMPAT_REEXPORTS[name]
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

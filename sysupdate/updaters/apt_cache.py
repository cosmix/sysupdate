"""Wrapper for python3-apt to extract package metadata for parallel downloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Shared path constants for APT cache directories
APT_ARCHIVES_DIR = Path("/var/cache/apt/archives")
APT_PARTIAL_DIR = APT_ARCHIVES_DIR / "partial"

# python3-apt is a system package, imported conditionally
# Type checkers can't find type stubs for these system packages
try:
    import apt  # type: ignore[import-untyped]

    APT_AVAILABLE = True
except ImportError:
    APT_AVAILABLE = False
    apt = None  # type: ignore[assignment]


@dataclass
class PackageInfo:
    """Package information extracted from APT cache."""

    name: str
    version: str
    old_version: str
    uris: list[str] = field(default_factory=list)
    filename: str = ""
    size: int = 0
    sha256: str = ""
    sha1: str = ""
    md5: str = ""

    @property
    def destfile(self) -> str:
        """Get the destination filename for the package."""
        if self.filename:
            return Path(self.filename).name
        # Encode colons in version as %3a (APT convention)
        version_encoded = self.version.replace(":", "%3a")
        return f"{self.name}_{version_encoded}_amd64.deb"


class AptCacheWrapper:
    """Wrapper around python3-apt for package metadata extraction."""

    # Reference module-level constants for backwards compatibility
    APT_ARCHIVES_DIR = APT_ARCHIVES_DIR
    APT_PARTIAL_DIR = APT_PARTIAL_DIR

    def __init__(self) -> None:
        if not APT_AVAILABLE:
            raise RuntimeError("python3-apt is not available")
        self._cache: Any = None

    def _get_cache(self) -> Any:
        """Get or create the APT cache."""
        if self._cache is None:
            self._cache = apt.Cache()  # type: ignore[union-attr]
        return self._cache

    def get_upgradable_packages(self) -> list[PackageInfo]:
        """Get list of upgradable packages with download information.

        Returns:
            List of PackageInfo objects for packages that can be upgraded.
        """
        cache = self._get_cache()
        cache.upgrade(dist_upgrade=True)

        packages: list[PackageInfo] = []
        for pkg in cache.get_changes():
            if not pkg.marked_upgrade and not pkg.marked_install:
                continue

            candidate = pkg.candidate
            if candidate is None:
                continue

            # Get all URIs from configured mirrors
            uris: list[str] = []
            try:
                for uri in candidate.uris:
                    if uri:
                        uris.append(uri)
            except Exception:
                # Some packages may not have URIs available
                pass

            if not uris:
                continue

            # Get hash values (prefer SHA256)
            sha256 = ""
            sha1 = ""
            md5 = ""
            try:
                sha256 = candidate.sha256 or ""
                sha1 = candidate.sha1 or ""
                md5 = candidate.md5 or ""
            except Exception:
                pass

            # Get old version if upgrading
            old_version = ""
            if pkg.installed:
                old_version = pkg.installed.version

            # Get filename from first URI
            filename = ""
            if uris:
                filename = Path(uris[0]).name

            packages.append(
                PackageInfo(
                    name=pkg.shortname,
                    version=candidate.version,
                    old_version=old_version,
                    uris=uris,
                    filename=filename,
                    size=candidate.size,
                    sha256=sha256,
                    sha1=sha1,
                    md5=md5,
                )
            )

        return packages


def is_apt_available() -> bool:
    """Check if python3-apt is available."""
    return APT_AVAILABLE

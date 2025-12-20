"""Wrapper for python3-apt to extract package metadata for parallel downloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Any

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

    APT_ARCHIVES_DIR = Path("/var/cache/apt/archives")
    APT_PARTIAL_DIR = APT_ARCHIVES_DIR / "partial"

    def __init__(self) -> None:
        if not APT_AVAILABLE:
            raise RuntimeError("python3-apt is not available")
        self._cache: Any = None

    def _get_cache(self) -> Any:
        """Get or create the APT cache."""
        if self._cache is None:
            self._cache = apt.Cache()  # type: ignore[union-attr]
        return self._cache

    def refresh_cache(self) -> None:
        """Refresh the APT cache (equivalent to apt update)."""
        self._cache = None
        cache = self._get_cache()
        cache.update()
        cache.open(None)

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

    def get_already_downloaded(self, packages: list[PackageInfo]) -> set[str]:
        """Check which packages are already downloaded in the cache.

        Args:
            packages: List of packages to check.

        Returns:
            Set of package names that are already downloaded.
        """
        downloaded: set[str] = set()
        for pkg in packages:
            archive_path = self.APT_ARCHIVES_DIR / pkg.destfile
            if archive_path.exists() and archive_path.stat().st_size == pkg.size:
                downloaded.add(pkg.name)
        return downloaded

    def install_downloaded_packages(self) -> tuple[bool, str]:
        """Install packages that have been downloaded to the cache.

        This runs dpkg to install all .deb files in the archives directory.

        Returns:
            Tuple of (success, error_message).
        """
        try:
            # Use apt-get to install from cache
            result = subprocess.run(
                ["sudo", "apt-get", "-y", "--no-download", "dist-upgrade"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return False, result.stderr or "Installation failed"
            return True, ""
        except subprocess.TimeoutExpired:
            return False, "Installation timed out"
        except Exception as e:
            return False, str(e)

    def move_from_partial(self, filename: str) -> bool:
        """Move a downloaded file from partial to archives directory.

        Args:
            filename: Name of the file to move.

        Returns:
            True if successful, False otherwise.
        """
        partial_path = self.APT_PARTIAL_DIR / filename
        archive_path = self.APT_ARCHIVES_DIR / filename

        if not partial_path.exists():
            return False

        try:
            partial_path.rename(archive_path)
            return True
        except Exception:
            return False

    def clear_cache(self) -> None:
        """Clear the internal cache to force refresh."""
        self._cache = None


def is_apt_available() -> bool:
    """Check if python3-apt is available."""
    return APT_AVAILABLE

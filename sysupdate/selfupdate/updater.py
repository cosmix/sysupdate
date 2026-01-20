"""Main self-update orchestration and coordination."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from packaging.version import InvalidVersion, Version

from .binary import (
    get_architecture,
    get_binary_path,
    get_expected_asset_name,
    replace_binary,
)
from .checksum import compute_sha256, parse_sha256sums, verify_checksum
from .github import GitHubClient, Release


@dataclass
class UpdateCheckResult:
    """Result of checking for available updates."""

    current_version: str
    latest_version: str | None
    update_available: bool
    release: Release | None
    error_message: str


@dataclass
class UpdateResult:
    """Result of performing a self-update."""

    success: bool
    old_version: str
    new_version: str
    error_message: str


class SelfUpdater:
    """Orchestrates self-update operations."""

    def __init__(self) -> None:
        """Initialize self-updater."""
        self._github_client = GitHubClient()

    async def check_for_update(self, current_version: str) -> UpdateCheckResult:
        """Check if a newer version is available on GitHub.

        Args:
            current_version: Current installed version string

        Returns:
            UpdateCheckResult with availability information
        """
        try:
            async with self._github_client as client:
                release = await client.get_latest_release()

                if release is None:
                    return UpdateCheckResult(
                        current_version=current_version,
                        latest_version=None,
                        update_available=False,
                        release=None,
                        error_message="Failed to fetch latest release from GitHub",
                    )

                latest_version = release.version
                is_newer = self._is_newer_version(current_version, latest_version)

                return UpdateCheckResult(
                    current_version=current_version,
                    latest_version=latest_version,
                    update_available=is_newer,
                    release=release if is_newer else None,
                    error_message="",
                )

        except Exception as e:
            return UpdateCheckResult(
                current_version=current_version,
                latest_version=None,
                update_available=False,
                release=None,
                error_message=f"Error checking for updates: {e}",
            )

    def _is_newer_version(self, current: str, latest: str) -> bool:
        """Compare version strings to determine if latest is newer.

        Uses PEP 440 version comparison via packaging library.

        Args:
            current: Current version string
            latest: Latest available version string

        Returns:
            True if latest is newer than current, False otherwise
        """
        try:
            current_ver = Version(current)
            latest_ver = Version(latest)
            return latest_ver > current_ver
        except InvalidVersion:
            # If version parsing fails, do string comparison as fallback
            return latest > current

    async def perform_update(
        self,
        current_version: str,
        release: Release,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> UpdateResult:
        """Perform the self-update by downloading and replacing the binary.

        Args:
            current_version: Current installed version string
            release: GitHub release to update to
            progress_callback: Optional callback(status_message, progress_percent)

        Returns:
            UpdateResult with success status and version information
        """
        current_binary_path = get_binary_path()

        try:
            # Get system architecture
            if progress_callback:
                progress_callback("Detecting system architecture", 5.0)

            arch = get_architecture()
            expected_binary_name = get_expected_asset_name(arch)

            # Find binary and checksums in release assets
            if progress_callback:
                progress_callback("Finding release assets", 10.0)

            binary_asset = None
            checksums_asset = None

            for asset in release.assets:
                if asset.name == expected_binary_name:
                    binary_asset = asset
                elif asset.name == "SHA256SUMS.txt":
                    checksums_asset = asset

            if binary_asset is None:
                return UpdateResult(
                    success=False,
                    old_version=current_version,
                    new_version=release.version,
                    error_message=(
                        f"Binary asset '{expected_binary_name}' not found in release. "
                        f"Your architecture ({arch}) may not be supported."
                    ),
                )

            if checksums_asset is None:
                return UpdateResult(
                    success=False,
                    old_version=current_version,
                    new_version=release.version,
                    error_message="SHA256SUMS.txt not found in release assets",
                )

            # Download and verify in temporary directory
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Download SHA256SUMS.txt
                if progress_callback:
                    progress_callback("Downloading checksums", 20.0)

                async with self._github_client as client:
                    checksums_text = await client.download_text(
                        checksums_asset.download_url
                    )

                checksums = parse_sha256sums(checksums_text)
                expected_hash = checksums.get(binary_asset.name)

                if expected_hash is None:
                    return UpdateResult(
                        success=False,
                        old_version=current_version,
                        new_version=release.version,
                        error_message=(
                            f"No checksum found for '{binary_asset.name}' "
                            "in SHA256SUMS.txt"
                        ),
                    )

                # Download binary
                if progress_callback:
                    progress_callback("Downloading binary", 30.0)

                new_binary_path = tmpdir_path / binary_asset.name

                def download_progress(percent: float, message: str) -> None:
                    """Map download progress to 30-70% range."""
                    if progress_callback:
                        mapped_percent = 30.0 + (percent * 0.4)
                        progress_callback(f"Downloading: {message}", mapped_percent)

                async with self._github_client as client:
                    download_success = await client.download_asset(
                        binary_asset.download_url,
                        new_binary_path,
                        download_progress,
                    )

                if not download_success:
                    return UpdateResult(
                        success=False,
                        old_version=current_version,
                        new_version=release.version,
                        error_message="Failed to download binary",
                    )

                # Verify checksum
                if progress_callback:
                    progress_callback("Verifying checksum", 75.0)

                if not verify_checksum(new_binary_path, expected_hash):
                    actual_hash = compute_sha256(new_binary_path)
                    return UpdateResult(
                        success=False,
                        old_version=current_version,
                        new_version=release.version,
                        error_message=(
                            f"Checksum verification failed. "
                            f"Expected: {expected_hash}, Got: {actual_hash}"
                        ),
                    )

                # Replace binary
                if progress_callback:
                    progress_callback("Replacing binary", 85.0)

                replace_success, replace_error = await replace_binary(
                    current_binary_path,
                    new_binary_path,
                )

                if not replace_success:
                    return UpdateResult(
                        success=False,
                        old_version=current_version,
                        new_version=release.version,
                        error_message=replace_error,
                    )

                if progress_callback:
                    progress_callback("Update complete", 100.0)

                return UpdateResult(
                    success=True,
                    old_version=current_version,
                    new_version=release.version,
                    error_message="",
                )

        except Exception as e:
            return UpdateResult(
                success=False,
                old_version=current_version,
                new_version=release.version,
                error_message=f"Unexpected error during update: {e}",
            )

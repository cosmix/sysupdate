"""GitHub API client for release management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import aiohttp


GITHUB_API_BASE = "https://api.github.com"
REPO_OWNER = "cosmix"
REPO_NAME = "sysupdate"


@dataclass
class ReleaseAsset:
    """GitHub release asset information."""

    name: str
    download_url: str
    size: int


@dataclass
class Release:
    """GitHub release information."""

    tag_name: str
    version: str
    name: str
    assets: list[ReleaseAsset]
    prerelease: bool


class GitHubClient:
    """Async GitHub API client for release operations."""

    def __init__(self, timeout: float = 30.0):
        """Initialize GitHub client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> GitHubClient:
        """Async context manager entry."""
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._session:
            await self._session.close()
            self._session = None

    async def get_latest_release(self) -> Release | None:
        """Get the latest release from GitHub.

        Returns:
            Release object if successful, None otherwise
        """
        if not self._session:
            raise RuntimeError("GitHubClient must be used as async context manager")

        url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    return None

                data = await response.json()

                # Parse assets
                assets = [
                    ReleaseAsset(
                        name=asset["name"],
                        download_url=asset["browser_download_url"],
                        size=asset["size"],
                    )
                    for asset in data.get("assets", [])
                ]

                # Extract version from tag (remove 'v' prefix if present)
                tag_name = data["tag_name"]
                version = tag_name.lstrip("v")

                return Release(
                    tag_name=tag_name,
                    version=version,
                    name=data.get("name", ""),
                    assets=assets,
                    prerelease=data.get("prerelease", False),
                )

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError):
            return None

    async def download_asset(
        self,
        url: str,
        dest_path: Path,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> bool:
        """Download an asset from URL to destination path.

        Args:
            url: Download URL
            dest_path: Destination file path
            progress_callback: Optional callback(progress_percent, status_message)

        Returns:
            True if download successful, False otherwise
        """
        if not self._session:
            raise RuntimeError("GitHubClient must be used as async context manager")

        try:
            async with self._session.get(url) as response:
                if response.status != 200:
                    if progress_callback:
                        progress_callback(0.0, f"Download failed: HTTP {response.status}")
                    return False

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                # Ensure parent directory exists
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                async with asyncio.Lock():
                    with dest_path.open("wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if progress_callback and total_size > 0:
                                progress_percent = (downloaded / total_size) * 100
                                progress_callback(
                                    progress_percent,
                                    f"Downloaded {downloaded}/{total_size} bytes",
                                )

                if progress_callback:
                    progress_callback(100.0, "Download complete")

                return True

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            if progress_callback:
                progress_callback(0.0, "Download failed")
            return False

    async def download_text(self, url: str) -> str:
        """Download text content from URL.

        Args:
            url: Download URL

        Returns:
            Text content as string

        Raises:
            aiohttp.ClientError: On network errors
            asyncio.TimeoutError: On timeout
        """
        if not self._session:
            raise RuntimeError("GitHubClient must be used as async context manager")

        async with self._session.get(url) as response:
            response.raise_for_status()
            return await response.text()

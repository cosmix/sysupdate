"""GitHub API client for release management."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import aiohttp

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
REPO_OWNER = "cosmix"
REPO_NAME = "sysupdate"

MAX_API_RESPONSE_BYTES = 2 * 1024 * 1024  # 2MB for JSON API responses
MAX_BINARY_DOWNLOAD_BYTES = 200 * 1024 * 1024  # 200MB for binary downloads
MAX_CHECKSUM_FILE_BYTES = 100 * 1024  # 100KB for SHA256SUMS


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

    async def _request_with_retry(
        self, url: str, max_retries: int = 3
    ) -> aiohttp.ClientResponse:
        """Make an HTTP GET request with exponential backoff retry.

        Retries on HTTP 429, 5xx, and connection/timeout errors.
        Propagates 4xx (except 429) immediately.

        Args:
            url: Request URL
            max_retries: Maximum number of attempts

        Returns:
            aiohttp.ClientResponse on success

        Raises:
            aiohttp.ClientError: On non-retryable HTTP errors
            asyncio.TimeoutError: If all retries are exhausted due to timeouts
        """
        if not self._session:
            raise RuntimeError("GitHubClient must be used as async context manager")

        last_error: BaseException | None = None
        for attempt in range(max_retries):
            try:
                response = await self._session.get(url)
                if response.status == 429 or response.status >= 500:
                    await response.release()
                    last_error = aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=(),
                        status=response.status,
                        message=f"HTTP {response.status}",
                    )
                    if attempt < max_retries - 1:
                        delay = 1 << attempt  # 1, 2, 4
                        logger.warning(
                            "Request to %s returned %d, retrying in %ds (attempt %d/%d)",
                            url, response.status, delay, attempt + 1, max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise last_error
                return response
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 1 << attempt
                    logger.warning(
                        "Request to %s failed with %s, retrying in %ds (attempt %d/%d)",
                        url, e, delay, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_error  # type: ignore[misc]  # last_error is always set after the loop

    async def get_latest_release(self) -> Release | None:
        """Get the latest release from GitHub.

        Returns:
            Release object if successful, None otherwise
        """
        if not self._session:
            raise RuntimeError("GitHubClient must be used as async context manager")

        url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

        try:
            response = await self._request_with_retry(url)
            try:
                if response.status != 200:
                    return None

                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_API_RESPONSE_BYTES:
                    logger.error(
                        "API response from %s exceeds size limit: %s bytes > %d byte limit",
                        url, content_length, MAX_API_RESPONSE_BYTES,
                    )
                    return None

                raw_body = await response.content.read(MAX_API_RESPONSE_BYTES)
                data = json.loads(raw_body)

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
            finally:
                await response.release()

        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, json.JSONDecodeError):
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
            response = await self._request_with_retry(url)
            try:
                if response.status != 200:
                    if progress_callback:
                        progress_callback(
                            0.0, f"Download failed: HTTP {response.status}"
                        )
                    return False

                total_size = int(response.headers.get("content-length", 0))
                if total_size > MAX_BINARY_DOWNLOAD_BYTES:
                    logger.error(
                        "Binary download from %s exceeds size limit: %d bytes > %d byte limit",
                        url, total_size, MAX_BINARY_DOWNLOAD_BYTES,
                    )
                    if progress_callback:
                        progress_callback(
                            0.0,
                            f"Download rejected: {total_size} bytes exceeds "
                            f"{MAX_BINARY_DOWNLOAD_BYTES} byte limit",
                        )
                    return False

                downloaded = 0

                # Ensure parent directory exists
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                with dest_path.open("wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        downloaded += len(chunk)
                        if downloaded > MAX_BINARY_DOWNLOAD_BYTES:
                            logger.error(
                                "Binary download from %s exceeded size limit during transfer: "
                                "%d bytes received > %d byte limit",
                                url, downloaded, MAX_BINARY_DOWNLOAD_BYTES,
                            )
                            f.close()
                            dest_path.unlink(missing_ok=True)
                            if progress_callback:
                                progress_callback(
                                    0.0,
                                    f"Download aborted: {downloaded} bytes received exceeds "
                                    f"{MAX_BINARY_DOWNLOAD_BYTES} byte limit",
                                )
                            return False
                        f.write(chunk)

                        if progress_callback and total_size > 0:
                            progress_percent = (downloaded / total_size) * 100
                            progress_callback(
                                progress_percent,
                                f"Downloaded {downloaded}/{total_size} bytes",
                            )

                if progress_callback:
                    progress_callback(100.0, "Download complete")

                return True
            finally:
                await response.release()

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
            ValueError: If response exceeds size limit
        """
        if not self._session:
            raise RuntimeError("GitHubClient must be used as async context manager")

        response = await self._request_with_retry(url)
        try:
            response.raise_for_status()

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_CHECKSUM_FILE_BYTES:
                raise ValueError(
                    f"Checksum file from {url} exceeds size limit: "
                    f"{content_length} bytes > {MAX_CHECKSUM_FILE_BYTES} byte limit"
                )

            raw_body = await response.content.read(MAX_CHECKSUM_FILE_BYTES)
            return raw_body.decode("utf-8")
        finally:
            await response.release()

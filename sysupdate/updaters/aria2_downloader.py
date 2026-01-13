"""Parallel package downloader using aria2c with Metalink XML format."""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .apt_cache import PackageInfo, APT_ARCHIVES_DIR, APT_PARTIAL_DIR
from ..utils import command_available


@dataclass
class DownloadProgress:
    """Progress information for a single download."""

    filename: str
    progress: float  # 0.0 to 1.0
    speed: str  # Human-readable speed (e.g., "2.5MiB/s")
    eta: str  # Human-readable ETA (e.g., "30s")


@dataclass
class DownloadResult:
    """Result of a download operation."""

    success: bool
    downloaded_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    error_message: str = ""


class Aria2Downloader:
    """Parallel package downloader using aria2c."""

    METALINK_NAMESPACE = "urn:ietf:params:xml:ns:metalink"

    def __init__(self) -> None:
        """Initialize the downloader."""
        self._progress_pattern = re.compile(
            r"\[#[a-f0-9]+\s+(\d+)%.*?DL:([\d.]+[KMGT]?i?B/s).*?ETA:([\d]+[smh])\]"
        )
        self._complete_pattern = re.compile(r"Download complete: (.+)")

    async def check_available(self) -> bool:
        """Check if aria2c is installed.

        Returns:
            True if aria2c is available, False otherwise.
        """
        return await command_available("aria2c", "--version")

    async def download_packages(
        self,
        packages: list[PackageInfo],
        callback: Callable[[DownloadProgress], None] | None = None,
    ) -> DownloadResult:
        """Download packages in parallel using aria2c.

        Args:
            packages: List of packages to download.
            callback: Optional callback for progress updates, called with DownloadProgress.

        Returns:
            DownloadResult with success status and file lists.
        """
        if not packages:
            return DownloadResult(success=True)

        # Ensure partial directory exists
        APT_PARTIAL_DIR.mkdir(parents=True, exist_ok=True)

        # Generate Metalink XML
        metalink_xml = self._generate_metalink_xml(packages)

        # Prepare aria2c command
        cmd = [
            "aria2c",
            "--metalink-file=-",  # Read from stdin
            f"--dir={APT_PARTIAL_DIR}",
            "--max-concurrent-downloads=5",
            "--file-allocation=none",
            "--continue=true",
            "--summary-interval=1",
            "--console-log-level=notice",
            "--enable-color=false",
        ]

        try:
            # Start aria2c process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # Send Metalink XML to stdin
            if process.stdin:
                process.stdin.write(metalink_xml.encode("utf-8"))
                await process.stdin.drain()
                process.stdin.close()

            # Monitor progress
            downloaded_files: list[str] = []
            failed_files: list[str] = []

            if process.stdout:
                async for line_bytes in process.stdout:
                    line = line_bytes.decode("utf-8", errors="replace").strip()

                    # Check for completion
                    complete_match = self._complete_pattern.search(line)
                    if complete_match:
                        filepath = complete_match.group(1)
                        filename = Path(filepath).name
                        downloaded_files.append(filename)
                        continue

                    # Parse progress updates
                    progress_match = self._progress_pattern.search(line)
                    if progress_match and callback:
                        percent = int(progress_match.group(1))
                        speed = progress_match.group(2)
                        eta = progress_match.group(3)

                        progress = DownloadProgress(
                            filename="",  # aria2c doesn't show filename in progress
                            progress=percent / 100.0,
                            speed=speed,
                            eta=eta,
                        )
                        callback(progress)

            # Wait for process to complete
            returncode = await process.wait()

            # Check which files failed
            expected_files = {pkg.destfile for pkg in packages}
            downloaded_set = set(downloaded_files)
            failed_files = list(expected_files - downloaded_set)

            # Move downloaded files from partial to archives
            for filename in downloaded_files:
                self._move_from_partial(filename)

            success = returncode == 0 and len(failed_files) == 0

            return DownloadResult(
                success=success,
                downloaded_files=downloaded_files,
                failed_files=failed_files,
                error_message="" if success else "Some downloads failed",
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=f"Download error: {e}",
            )

    def _generate_metalink_xml(self, packages: list[PackageInfo]) -> str:
        """Generate Metalink XML for package downloads.

        Args:
            packages: List of packages to include in the Metalink.

        Returns:
            XML string in Metalink format.
        """
        # Create root element with namespace
        metalink = ET.Element(
            "metalink",
            xmlns=self.METALINK_NAMESPACE,
        )

        for pkg in packages:
            # Create file element
            file_elem = ET.SubElement(metalink, "file", name=pkg.destfile)

            # Add size
            if pkg.size > 0:
                size_elem = ET.SubElement(file_elem, "size")
                size_elem.text = str(pkg.size)

            # Add hash (prefer SHA-256)
            if pkg.sha256:
                hash_elem = ET.SubElement(file_elem, "hash", type="sha-256")
                hash_elem.text = pkg.sha256
            elif pkg.sha1:
                hash_elem = ET.SubElement(file_elem, "hash", type="sha-1")
                hash_elem.text = pkg.sha1
            elif pkg.md5:
                hash_elem = ET.SubElement(file_elem, "hash", type="md5")
                hash_elem.text = pkg.md5

            # Add URLs with priority
            for i, uri in enumerate(pkg.uris):
                url_elem = ET.SubElement(
                    file_elem,
                    "url",
                    priority=str(i + 1),
                )
                url_elem.text = uri

        # Convert to string with XML declaration
        xml_str = ET.tostring(
            metalink,
            encoding="unicode",
            method="xml",
        )
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_str}'

    def _move_from_partial(self, filename: str) -> bool:
        """Move a downloaded file from partial to archives directory.

        Args:
            filename: Name of the file to move.

        Returns:
            True if successful, False otherwise.
        """
        partial_path = APT_PARTIAL_DIR / filename
        archive_path = APT_ARCHIVES_DIR / filename

        if not partial_path.exists():
            return False

        try:
            partial_path.rename(archive_path)
            return True
        except Exception:
            return False

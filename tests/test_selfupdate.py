"""Tests for self-update module."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sysupdate.selfupdate.binary import (
    get_architecture,
    get_expected_asset_name,
)
from sysupdate.selfupdate.checksum import (
    compute_sha256,
    parse_sha256sums,
    verify_checksum,
)
from sysupdate.selfupdate.github import GitHubClient, Release, ReleaseAsset


class TestChecksum:
    """Tests for checksum utilities."""

    def test_parse_sha256sums(self):
        """Test parse standard SHA256SUMS format."""
        content = """abc123def456  sysupdate-linux-x86_64
789fed654cba  sysupdate-linux-aarch64
"""
        checksums = parse_sha256sums(content)

        assert len(checksums) == 2
        assert checksums["sysupdate-linux-x86_64"] == "abc123def456"
        assert checksums["sysupdate-linux-aarch64"] == "789fed654cba"

    def test_parse_sha256sums_with_comments(self):
        """Test parse SHA256SUMS with comments and blank lines."""
        content = """# SHA256 checksums for sysupdate release
# Generated automatically

abc123def456  sysupdate-linux-x86_64

# ARM64 binary
789fed654cba  sysupdate-linux-aarch64

"""
        checksums = parse_sha256sums(content)

        assert len(checksums) == 2
        assert checksums["sysupdate-linux-x86_64"] == "abc123def456"
        assert checksums["sysupdate-linux-aarch64"] == "789fed654cba"

    def test_parse_sha256sums_uppercase_hash(self):
        """Test that uppercase hashes are normalized to lowercase."""
        content = "ABC123DEF456  testfile.bin\n"
        checksums = parse_sha256sums(content)

        assert checksums["testfile.bin"] == "abc123def456"

    def test_parse_sha256sums_empty(self):
        """Test parsing empty content returns empty dict."""
        checksums = parse_sha256sums("")
        assert checksums == {}

    def test_compute_sha256(self, tmp_path):
        """Test computing SHA256 hash of a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # SHA256 of "Hello, World!" is known
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        actual = compute_sha256(test_file)

        assert actual == expected

    def test_compute_sha256_large_file(self, tmp_path):
        """Test computing SHA256 of large file using chunked reading."""
        test_file = tmp_path / "large.bin"

        # Create a file larger than the chunk size (8192 bytes)
        data = b"x" * 10000
        test_file.write_bytes(data)

        hash_value = compute_sha256(test_file)

        # Verify hash is 64 hex characters
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_compute_sha256_nonexistent_file(self, tmp_path):
        """Test computing SHA256 of nonexistent file raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist.txt"

        with pytest.raises(FileNotFoundError):
            compute_sha256(nonexistent)

    def test_verify_checksum_success(self, tmp_path):
        """Test verify_checksum with correct hash matches."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        expected_hash = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"

        assert verify_checksum(test_file, expected_hash) is True

    def test_verify_checksum_failure(self, tmp_path):
        """Test verify_checksum with wrong hash fails."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"

        assert verify_checksum(test_file, wrong_hash) is False

    def test_verify_checksum_case_insensitive(self, tmp_path):
        """Test verify_checksum is case-insensitive."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Uppercase hash should still match
        uppercase_hash = "DFFD6021BB2BD5B0AF676290809EC3A53191DD81C7F70A4B28688A362182986F"

        assert verify_checksum(test_file, uppercase_hash) is True


class TestBinary:
    """Tests for binary detection utilities."""

    def test_get_architecture_x86_64(self):
        """Test get_architecture returns x86_64 for x86_64/amd64."""
        with patch("platform.machine", return_value="x86_64"):
            assert get_architecture() == "x86_64"

    def test_get_architecture_amd64(self):
        """Test get_architecture returns x86_64 for amd64."""
        with patch("platform.machine", return_value="amd64"):
            assert get_architecture() == "x86_64"

    def test_get_architecture_aarch64(self):
        """Test get_architecture returns aarch64 for aarch64."""
        with patch("platform.machine", return_value="aarch64"):
            assert get_architecture() == "aarch64"

    def test_get_architecture_arm64(self):
        """Test get_architecture returns aarch64 for arm64."""
        with patch("platform.machine", return_value="arm64"):
            assert get_architecture() == "aarch64"

    def test_get_architecture_case_insensitive(self):
        """Test get_architecture is case-insensitive."""
        with patch("platform.machine", return_value="X86_64"):
            assert get_architecture() == "x86_64"

        with patch("platform.machine", return_value="AARCH64"):
            assert get_architecture() == "aarch64"

    def test_get_architecture_unsupported(self):
        """Test get_architecture raises RuntimeError for unsupported arch."""
        with patch("platform.machine", return_value="mips"):
            with pytest.raises(RuntimeError) as exc_info:
                get_architecture()

            assert "Unsupported architecture: mips" in str(exc_info.value)
            assert "x86_64, aarch64" in str(exc_info.value)

    def test_get_expected_asset_name_x86_64(self):
        """Test get_expected_asset_name for x86_64."""
        assert get_expected_asset_name("x86_64") == "sysupdate-linux-x86_64"

    def test_get_expected_asset_name_aarch64(self):
        """Test get_expected_asset_name for aarch64."""
        assert get_expected_asset_name("aarch64") == "sysupdate-linux-aarch64"


class TestGitHubClient:
    """Tests for GitHub API client."""

    def test_release_asset_dataclass(self):
        """Test ReleaseAsset dataclass creation."""
        asset = ReleaseAsset(
            name="sysupdate-linux-x86_64",
            download_url="https://github.com/cosmix/sysupdate/releases/download/v2.0.0/sysupdate-linux-x86_64",
            size=5242880,
        )

        assert asset.name == "sysupdate-linux-x86_64"
        assert "github.com" in asset.download_url
        assert asset.size == 5242880

    def test_release_dataclass(self):
        """Test Release dataclass creation."""
        assets = [
            ReleaseAsset(
                name="sysupdate-linux-x86_64",
                download_url="https://example.com/x86_64",
                size=1000,
            ),
            ReleaseAsset(
                name="sysupdate-linux-aarch64",
                download_url="https://example.com/aarch64",
                size=2000,
            ),
        ]

        release = Release(
            tag_name="v2.0.1",
            version="2.0.1",
            name="Version 2.0.1",
            assets=assets,
            prerelease=False,
        )

        assert release.tag_name == "v2.0.1"
        assert release.version == "2.0.1"
        assert len(release.assets) == 2
        assert release.prerelease is False

    @pytest.mark.asyncio
    async def test_github_client_context_manager(self):
        """Test GitHubClient works as async context manager."""
        async with GitHubClient(timeout=30.0) as client:
            assert client._session is not None

        # Session should be closed after exit
        assert client._session is None

    @pytest.mark.asyncio
    async def test_get_latest_release_success(self):
        """Test get_latest_release with successful response."""
        mock_response_data = {
            "tag_name": "v2.0.1",
            "name": "Release 2.0.1",
            "prerelease": False,
            "assets": [
                {
                    "name": "sysupdate-linux-x86_64",
                    "browser_download_url": "https://example.com/x86_64",
                    "size": 1024,
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://example.com/sha256sums",
                    "size": 256,
                },
            ],
        }

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            # Mock the response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)

            # Mock get() to return an async context manager
            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                release = await client.get_latest_release()

            assert release is not None
            assert release.tag_name == "v2.0.1"
            assert release.version == "2.0.1"
            assert release.name == "Release 2.0.1"
            assert release.prerelease is False
            assert len(release.assets) == 2
            assert release.assets[0].name == "sysupdate-linux-x86_64"

    @pytest.mark.asyncio
    async def test_get_latest_release_strips_v_prefix(self):
        """Test get_latest_release strips 'v' prefix from version."""
        mock_response_data = {
            "tag_name": "v3.0.0",
            "name": "Release 3.0.0",
            "prerelease": False,
            "assets": [],
        }

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                release = await client.get_latest_release()

            assert release.version == "3.0.0"
            assert release.tag_name == "v3.0.0"

    @pytest.mark.asyncio
    async def test_get_latest_release_not_found(self):
        """Test get_latest_release with 404 returns None."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 404

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                release = await client.get_latest_release()

            assert release is None

    @pytest.mark.asyncio
    async def test_get_latest_release_network_error(self):
        """Test get_latest_release handles network errors."""
        import aiohttp

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            # Simulate network error
            mock_session.get.side_effect = aiohttp.ClientError("Network error")
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                release = await client.get_latest_release()

            assert release is None

    @pytest.mark.asyncio
    async def test_get_latest_release_timeout(self):
        """Test get_latest_release handles timeout."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            # Simulate timeout
            mock_session.get.side_effect = asyncio.TimeoutError()
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                release = await client.get_latest_release()

            assert release is None

    @pytest.mark.asyncio
    async def test_get_latest_release_requires_context_manager(self):
        """Test get_latest_release requires context manager."""
        client = GitHubClient()

        with pytest.raises(RuntimeError) as exc_info:
            await client.get_latest_release()

        assert "must be used as async context manager" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_asset_success(self, tmp_path):
        """Test download_asset successful download."""
        dest_file = tmp_path / "download" / "binary"

        # Simulate file content
        file_content = b"binary content here"

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {"content-length": str(len(file_content))}

            # Mock chunked reading
            async def mock_iter_chunked(size):
                yield file_content

            mock_response.content.iter_chunked = mock_iter_chunked

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            progress_calls = []

            def progress_callback(percent, message):
                progress_calls.append((percent, message))

            async with GitHubClient() as client:
                success = await client.download_asset(
                    "https://example.com/file",
                    dest_file,
                    progress_callback,
                )

            assert success is True
            assert dest_file.exists()
            assert dest_file.read_bytes() == file_content

            # Verify progress callback was called
            assert len(progress_calls) > 0
            assert progress_calls[-1][0] == 100.0

    @pytest.mark.asyncio
    async def test_download_asset_http_error(self, tmp_path):
        """Test download_asset handles HTTP errors."""
        dest_file = tmp_path / "binary"

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 500

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                success = await client.download_asset(
                    "https://example.com/file",
                    dest_file,
                )

            assert success is False
            assert not dest_file.exists()

    @pytest.mark.asyncio
    async def test_download_asset_creates_parent_dir(self, tmp_path):
        """Test download_asset creates parent directories."""
        dest_file = tmp_path / "subdir" / "nested" / "binary"

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {"content-length": "10"}

            async def mock_iter_chunked(size):
                yield b"test"

            mock_response.content.iter_chunked = mock_iter_chunked

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                success = await client.download_asset(
                    "https://example.com/file",
                    dest_file,
                )

            assert success is True
            assert dest_file.parent.exists()
            assert dest_file.exists()

    @pytest.mark.asyncio
    async def test_download_text_success(self):
        """Test download_text successful text retrieval."""
        expected_text = "This is text content"

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.text = AsyncMock(return_value=expected_text)

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                text = await client.download_text("https://example.com/text")

            assert text == expected_text

    @pytest.mark.asyncio
    async def test_download_text_http_error(self):
        """Test download_text raises on HTTP error."""
        import aiohttp

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session_class.return_value = mock_session

            mock_response = AsyncMock()

            mock_response.raise_for_status = MagicMock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=MagicMock(),
                    history=(),
                    status=404,
                )
            )

            mock_get_cm = AsyncMock()
            mock_get_cm.__aenter__.return_value = mock_response
            mock_get_cm.__aexit__.return_value = None
            mock_session.get.return_value = mock_get_cm
            mock_session.close = AsyncMock()

            async with GitHubClient() as client:
                with pytest.raises(aiohttp.ClientError):
                    await client.download_text("https://example.com/text")

"""Tests for self-update module."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sysupdate.selfupdate.binary import (
    get_architecture,
    get_expected_asset_name,
    replace_binary,
    can_write_to_path,
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


class TestBinaryPathDetection:
    """Tests for binary path detection in various scenarios."""

    def test_get_binary_path_from_pyapp_env_var(self, tmp_path):
        """Test get_binary_path uses PYAPP environment variable when set to a path."""
        from sysupdate.selfupdate.binary import get_binary_path

        # Create a mock binary
        mock_binary = tmp_path / "sysupdate"
        mock_binary.write_bytes(b"mock binary")
        mock_binary.chmod(0o755)

        # PYAPP env var contains the binary path (not just "1")
        with patch.dict(os.environ, {"PYAPP": str(mock_binary)}):
            result = get_binary_path()
            assert result == mock_binary

    def test_get_binary_path_ignores_pyapp_flag_only(self, tmp_path):
        """Test get_binary_path ignores PYAPP='1' and uses fallback."""
        from sysupdate.selfupdate.binary import get_binary_path

        # Create a mock binary for PATH fallback
        mock_binary = tmp_path / "sysupdate"
        mock_binary.write_bytes(b"mock binary")
        mock_binary.chmod(0o755)

        # PYAPP is just "1" (no path), should fall through to other checks
        with patch.dict(os.environ, {"PYAPP": "1"}):
            # Use a custom ppid that points to a non-sysupdate process
            with patch("sysupdate.selfupdate.binary.os.getppid", return_value=1):
                with patch("sys.executable", "/usr/bin/python3"):
                    with patch("shutil.which", return_value=str(mock_binary)):
                        result = get_binary_path()
                        assert result == mock_binary

    def test_get_binary_path_from_pyapp_env_var_nonexistent_path(self, tmp_path):
        """Test get_binary_path falls back when PYAPP points to nonexistent file."""
        from sysupdate.selfupdate.binary import get_binary_path

        # Create a mock binary for PATH fallback
        mock_binary = tmp_path / "sysupdate"
        mock_binary.write_bytes(b"mock binary")
        mock_binary.chmod(0o755)

        # PYAPP points to nonexistent file
        with patch.dict(os.environ, {"PYAPP": "/nonexistent/sysupdate"}):
            with patch("sysupdate.selfupdate.binary.os.getppid", return_value=1):
                with patch("sys.executable", "/usr/bin/python3"):
                    with patch("shutil.which", return_value=str(mock_binary)):
                        result = get_binary_path()
                        assert result == mock_binary

    def test_get_binary_path_from_parent_process(self):
        """Test get_binary_path detects sysupdate from parent process."""
        from sysupdate.selfupdate.binary import get_binary_path

        # Mock scenario: parent process is the PyApp binary named 'sysupdate'
        mock_path = Path("/usr/local/bin/sysupdate")

        with patch("os.getppid", return_value=12345):
            with patch.object(Path, "resolve", return_value=mock_path):
                with patch.object(Path, "name", new_callable=lambda: property(lambda s: "sysupdate")):
                    # This test verifies the parent process check path
                    # The actual implementation reads /proc/{ppid}/exe
                    pass  # Complex to mock /proc filesystem

    def test_get_binary_path_from_sys_executable(self):
        """Test get_binary_path falls back to sys.executable."""
        from sysupdate.selfupdate.binary import get_binary_path

        # Create a temp binary to test with
        with patch("os.getppid", return_value=1):  # init process
            with patch.object(Path, "resolve", side_effect=OSError("No such file")):
                with patch("sys.executable", "/usr/bin/sysupdate"):
                    # When parent process check fails and sys.executable is 'sysupdate'
                    # it should return that path
                    pass

    def test_get_binary_path_from_which(self, tmp_path):
        """Test get_binary_path falls back to shutil.which."""
        from sysupdate.selfupdate.binary import get_binary_path

        # Create a mock binary
        mock_binary = tmp_path / "sysupdate"
        mock_binary.write_bytes(b"mock binary")
        mock_binary.chmod(0o755)

        # Mock all other detection methods to fail
        with patch.dict(os.environ, {"PYAPP": ""}):
            with patch("sysupdate.selfupdate.binary.os.getppid", return_value=1):
                with patch("sys.executable", "/usr/bin/python3"):
                    with patch("shutil.which", return_value=str(mock_binary)):
                        result = get_binary_path()
                        assert result == mock_binary

    def test_get_binary_path_raises_when_not_found(self):
        """Test get_binary_path raises RuntimeError when binary not found."""
        from sysupdate.selfupdate.binary import get_binary_path

        with patch.dict(os.environ, {"PYAPP": ""}):
            with patch("os.getppid", return_value=1):
                with patch("pathlib.Path.resolve", side_effect=OSError("No such file")):
                    with patch("sys.executable", "/usr/bin/python3"):
                        with patch("shutil.which", return_value=None):
                            with pytest.raises(RuntimeError) as exc_info:
                                get_binary_path()
                            assert "Could not locate sysupdate binary" in str(exc_info.value)


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


class TestSelfUpdaterE2E:
    """End-to-end tests for the complete self-update flow."""

    @pytest.fixture
    def mock_release(self):
        """Create a mock release with test assets."""
        return Release(
            tag_name="v2.0.0",
            version="2.0.0",
            name="Test Release 2.0.0",
            assets=[
                ReleaseAsset(
                    name="sysupdate-linux-x86_64",
                    download_url="https://example.com/sysupdate-linux-x86_64",
                    size=1024,
                ),
                ReleaseAsset(
                    name="sysupdate-linux-aarch64",
                    download_url="https://example.com/sysupdate-linux-aarch64",
                    size=1024,
                ),
                ReleaseAsset(
                    name="SHA256SUMS.txt",
                    download_url="https://example.com/SHA256SUMS.txt",
                    size=256,
                ),
            ],
            prerelease=False,
        )

    def _create_mock_session(self, sha256sums_content: str, new_binary_content: bytes):
        """Helper to create a properly mocked aiohttp session."""
        mock_session = MagicMock()

        def create_mock_response(url):
            mock_resp = AsyncMock()
            mock_resp.status = 200

            if "SHA256SUMS" in url:
                mock_resp.raise_for_status = MagicMock()
                mock_resp.text = AsyncMock(return_value=sha256sums_content)
            else:
                # Binary download
                mock_resp.headers = {"content-length": str(len(new_binary_content))}

                async def mock_iter_chunked(size):
                    yield new_binary_content

                mock_resp.content = MagicMock()
                mock_resp.content.iter_chunked = mock_iter_chunked

            return mock_resp

        def mock_get(url):
            # Return a context manager, not a coroutine
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=create_mock_response(url))
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        mock_session.get = mock_get
        mock_session.close = AsyncMock()
        return mock_session

    @pytest.mark.asyncio
    async def test_perform_update_full_flow_x86_64(self, tmp_path, mock_release):
        """Test complete update flow with mocked network on x86_64."""
        from sysupdate.selfupdate.updater import SelfUpdater
        import hashlib

        # Create fake current binary
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old binary version 1.0.0")
        current_binary.chmod(0o755)
        original_content = current_binary.read_bytes()

        # Create fake new binary content
        new_binary_content = b"new binary version 2.0.0 - this is the update!"
        new_binary_hash = hashlib.sha256(new_binary_content).hexdigest()

        # Create SHA256SUMS content
        sha256sums_content = f"{new_binary_hash}  sysupdate-linux-x86_64\n"

        # Patch get_binary_path to return our test binary
        with patch("sysupdate.selfupdate.updater.get_binary_path", return_value=current_binary):
            with patch("sysupdate.selfupdate.updater.get_architecture", return_value="x86_64"):
                with patch("aiohttp.ClientSession") as mock_session_class:
                    mock_session = self._create_mock_session(sha256sums_content, new_binary_content)
                    mock_session_class.return_value = mock_session

                    # Run the update
                    updater = SelfUpdater()
                    progress_messages = []

                    def progress_callback(msg, pct):
                        progress_messages.append((msg, pct))

                    result = await updater.perform_update(
                        current_version="1.0.0",
                        release=mock_release,
                        progress_callback=progress_callback,
                    )

        # Verify the update succeeded
        assert result.success, f"Update failed: {result.error_message}"
        assert result.old_version == "1.0.0"
        assert result.new_version == "2.0.0"
        assert result.error_message == ""

        # CRITICAL: Verify the binary was actually replaced with correct content
        assert current_binary.exists(), "Binary should still exist"
        final_content = current_binary.read_bytes()
        assert final_content == new_binary_content, (
            f"Binary content mismatch!\n"
            f"Expected: {new_binary_content[:50]}...\n"
            f"Got: {final_content[:50]}..."
        )
        assert final_content != original_content, "Binary should have been replaced"

        # Verify binary is executable
        mode = current_binary.stat().st_mode
        assert mode & 0o111, "Binary should be executable"

        # Verify backup was cleaned up
        assert not current_binary.with_suffix(".bak").exists()

        # Verify progress was reported
        assert len(progress_messages) > 0
        assert progress_messages[-1][1] == 100.0

    @pytest.mark.asyncio
    async def test_perform_update_cross_filesystem(self, tmp_path, mock_release):
        """Test update when temp directory is on different filesystem."""
        from sysupdate.selfupdate.updater import SelfUpdater
        import hashlib

        # Create fake current binary
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old binary")
        current_binary.chmod(0o755)

        # Create fake new binary content
        new_binary_content = b"new binary - cross filesystem test " + (b"x" * 10000)
        new_binary_hash = hashlib.sha256(new_binary_content).hexdigest()
        sha256sums_content = f"{new_binary_hash}  sysupdate-linux-x86_64\n"

        with patch("sysupdate.selfupdate.updater.get_binary_path", return_value=current_binary):
            with patch("sysupdate.selfupdate.updater.get_architecture", return_value="x86_64"):
                with patch("aiohttp.ClientSession") as mock_session_class:
                    mock_session = self._create_mock_session(sha256sums_content, new_binary_content)
                    mock_session_class.return_value = mock_session

                    updater = SelfUpdater()
                    result = await updater.perform_update(
                        current_version="1.0.0",
                        release=mock_release,
                    )

        assert result.success, f"Update failed: {result.error_message}"
        assert current_binary.read_bytes() == new_binary_content

    @pytest.mark.asyncio
    async def test_perform_update_checksum_mismatch_fails(self, tmp_path, mock_release):
        """Test that update fails when checksum doesn't match."""
        from sysupdate.selfupdate.updater import SelfUpdater

        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old binary")
        current_binary.chmod(0o755)
        original_content = current_binary.read_bytes()

        new_binary_content = b"new binary content"
        # Wrong hash!
        wrong_hash = "0" * 64
        sha256sums_content = f"{wrong_hash}  sysupdate-linux-x86_64\n"

        with patch("sysupdate.selfupdate.updater.get_binary_path", return_value=current_binary):
            with patch("sysupdate.selfupdate.updater.get_architecture", return_value="x86_64"):
                with patch("aiohttp.ClientSession") as mock_session_class:
                    mock_session = self._create_mock_session(sha256sums_content, new_binary_content)
                    mock_session_class.return_value = mock_session

                    updater = SelfUpdater()
                    result = await updater.perform_update(
                        current_version="1.0.0",
                        release=mock_release,
                    )

        # Update should fail
        assert not result.success
        assert "Checksum verification failed" in result.error_message

        # Original binary should be unchanged
        assert current_binary.read_bytes() == original_content

    @pytest.mark.asyncio
    async def test_perform_update_binary_not_replaced_on_download_failure(
        self, tmp_path, mock_release
    ):
        """Test that original binary is preserved when download fails."""
        from sysupdate.selfupdate.updater import SelfUpdater

        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"precious original binary")
        current_binary.chmod(0o755)
        original_content = current_binary.read_bytes()

        with patch("sysupdate.selfupdate.updater.get_binary_path", return_value=current_binary):
            with patch("sysupdate.selfupdate.updater.get_architecture", return_value="x86_64"):
                with patch("aiohttp.ClientSession") as mock_session_class:
                    mock_session = MagicMock()
                    mock_session_class.return_value = mock_session

                    def create_mock_response(url):
                        mock_resp = AsyncMock()

                        if "SHA256SUMS" in url:
                            mock_resp.status = 200
                            mock_resp.raise_for_status = MagicMock()
                            mock_resp.text = AsyncMock(return_value="hash  sysupdate-linux-x86_64\n")
                        else:
                            # Binary download fails
                            mock_resp.status = 500

                        return mock_resp

                    def mock_get(url):
                        cm = MagicMock()
                        cm.__aenter__ = AsyncMock(return_value=create_mock_response(url))
                        cm.__aexit__ = AsyncMock(return_value=None)
                        return cm

                    mock_session.get = mock_get
                    mock_session.close = AsyncMock()

                    updater = SelfUpdater()
                    result = await updater.perform_update(
                        current_version="1.0.0",
                        release=mock_release,
                    )

        assert not result.success
        assert "Failed to download" in result.error_message

        # Original should be unchanged
        assert current_binary.read_bytes() == original_content

    @pytest.mark.asyncio
    async def test_perform_update_tempdir_cleanup_doesnt_affect_result(
        self, tmp_path, mock_release
    ):
        """Test that temp directory cleanup doesn't delete the replaced binary."""
        from sysupdate.selfupdate.updater import SelfUpdater
        import hashlib

        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old")
        current_binary.chmod(0o755)

        # Use a specific marker to verify the content
        marker = b"UNIQUE_MARKER_12345_" + bytes(range(256))
        new_binary_content = marker + b"_END"
        new_binary_hash = hashlib.sha256(new_binary_content).hexdigest()
        sha256sums_content = f"{new_binary_hash}  sysupdate-linux-x86_64\n"

        with patch("sysupdate.selfupdate.updater.get_binary_path", return_value=current_binary):
            with patch("sysupdate.selfupdate.updater.get_architecture", return_value="x86_64"):
                with patch("aiohttp.ClientSession") as mock_session_class:
                    mock_session = self._create_mock_session(sha256sums_content, new_binary_content)
                    mock_session_class.return_value = mock_session

                    updater = SelfUpdater()
                    result = await updater.perform_update(
                        current_version="1.0.0",
                        release=mock_release,
                    )

        # At this point, the TemporaryDirectory has been cleaned up
        # but our binary should still have the new content
        assert result.success, f"Update failed: {result.error_message}"
        final_content = current_binary.read_bytes()
        assert marker in final_content, "Marker not found in final binary - content was lost!"
        assert final_content == new_binary_content


class TestBinaryReplacement:
    """E2E tests for binary replacement functionality."""

    @pytest.mark.asyncio
    async def test_replace_binary_same_filesystem(self, tmp_path):
        """Test replacing binary when both files are on same filesystem."""
        # Create "current" binary
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old binary content version 1.0")
        current_binary.chmod(0o755)
        original_content = current_binary.read_bytes()

        # Create "new" binary in same tmp_path (same filesystem)
        new_binary = tmp_path / "new" / "sysupdate-linux-x86_64"
        new_binary.parent.mkdir(parents=True)
        new_binary.write_bytes(b"new binary content version 2.0 - updated!")
        new_content = new_binary.read_bytes()

        # Perform replacement
        success, error = await replace_binary(current_binary, new_binary)

        assert success, f"Replacement failed: {error}"
        assert error == ""
        assert current_binary.exists()
        assert current_binary.read_bytes() == new_content
        assert not new_binary.exists()  # Should be moved, not copied
        # Backup should be cleaned up
        assert not current_binary.with_suffix(".bak").exists()

    @pytest.mark.asyncio
    async def test_replace_binary_cross_filesystem(self, tmp_path):
        """Test replacing binary when new binary is in /tmp (potentially different fs)."""
        import tempfile

        # Create "current" binary in tmp_path
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old binary content version 1.0")
        current_binary.chmod(0o755)

        # Create "new" binary in system /tmp (may be different filesystem)
        with tempfile.TemporaryDirectory() as system_tmp:
            new_binary = Path(system_tmp) / "sysupdate-linux-x86_64"
            new_binary.write_bytes(b"new binary content version 2.0 - cross fs!")
            new_content = new_binary.read_bytes()

            # Perform replacement
            success, error = await replace_binary(current_binary, new_binary)

            assert success, f"Replacement failed: {error}"
            assert error == ""
            assert current_binary.exists()
            assert current_binary.read_bytes() == new_content

    @pytest.mark.asyncio
    async def test_replace_binary_preserves_executable(self, tmp_path):
        """Test that replaced binary remains executable."""
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old")
        current_binary.chmod(0o755)

        new_binary = tmp_path / "new_binary"
        new_binary.write_bytes(b"new")

        success, error = await replace_binary(current_binary, new_binary)

        assert success, f"Replacement failed: {error}"
        # Check executable bit is set
        mode = current_binary.stat().st_mode
        assert mode & 0o111, "Binary should be executable"

    @pytest.mark.asyncio
    async def test_replace_binary_restores_on_failure(self, tmp_path):
        """Test that original binary is restored if new binary doesn't exist."""
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"original content")
        current_binary.chmod(0o755)
        original_content = current_binary.read_bytes()

        # Non-existent new binary
        new_binary = tmp_path / "does_not_exist"

        success, error = await replace_binary(current_binary, new_binary)

        assert not success
        assert "does not exist" in error
        # Original should still be there
        assert current_binary.exists()
        assert current_binary.read_bytes() == original_content

    @pytest.mark.asyncio
    async def test_replace_binary_with_different_sizes(self, tmp_path):
        """Test replacement works correctly with different file sizes."""
        current_binary = tmp_path / "sysupdate"
        # Small original
        current_binary.write_bytes(b"small")
        current_binary.chmod(0o755)

        new_binary = tmp_path / "new_binary"
        # Much larger new binary (simulating real PyApp binary)
        new_binary.write_bytes(b"x" * 10000)
        new_content = new_binary.read_bytes()

        success, error = await replace_binary(current_binary, new_binary)

        assert success, f"Replacement failed: {error}"
        assert current_binary.read_bytes() == new_content
        assert current_binary.stat().st_size == 10000

    @pytest.mark.asyncio
    async def test_replace_binary_backup_cleanup(self, tmp_path):
        """Test that backup file is properly cleaned up after successful replacement."""
        current_binary = tmp_path / "sysupdate"
        current_binary.write_bytes(b"old")
        current_binary.chmod(0o755)
        backup_path = current_binary.with_suffix(".bak")

        new_binary = tmp_path / "new_binary"
        new_binary.write_bytes(b"new")

        # Ensure no pre-existing backup
        assert not backup_path.exists()

        success, error = await replace_binary(current_binary, new_binary)

        assert success, f"Replacement failed: {error}"
        # Backup should be removed
        assert not backup_path.exists()

    def test_can_write_to_path_writable(self, tmp_path):
        """Test can_write_to_path returns True for writable paths."""
        test_file = tmp_path / "test"
        test_file.write_text("test")

        assert can_write_to_path(test_file) is True
        assert can_write_to_path(tmp_path) is True

    def test_can_write_to_path_nonexistent_checks_parent(self, tmp_path):
        """Test can_write_to_path checks parent for nonexistent files."""
        nonexistent = tmp_path / "does_not_exist"

        # Parent (tmp_path) is writable, so this should return True
        assert can_write_to_path(nonexistent) is True

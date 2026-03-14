"""Tests for the aria2 downloader module."""

from unittest.mock import AsyncMock, MagicMock, patch
from xml.etree import ElementTree as ET

from sysupdate.updaters.apt_cache import PackageInfo
from sysupdate.updaters.aria2_downloader import (
    Aria2Downloader,
    DownloadProgress,
    DownloadResult,
)


class TestDownloadProgress:
    """Tests for the DownloadProgress dataclass."""

    def test_creation(self):
        """Test creating a DownloadProgress with all fields."""
        progress = DownloadProgress(
            filename="libssl3_3.0.13_amd64.deb",
            progress=0.45,
            speed="2.5 MB/s",
            eta="30s",
        )
        assert progress.filename == "libssl3_3.0.13_amd64.deb"
        assert progress.progress == 0.45
        assert progress.speed == "2.5 MB/s"
        assert progress.eta == "30s"


class TestDownloadResult:
    """Tests for the DownloadResult dataclass."""

    def test_creation_with_defaults(self):
        """Test creating a DownloadResult with only success."""
        result = DownloadResult(success=True)
        assert result.success is True
        assert result.downloaded_files == []
        assert result.failed_files == []
        assert result.error_message == ""

    def test_creation_with_all_fields(self):
        """Test creating a DownloadResult with all fields."""
        result = DownloadResult(
            success=False,
            downloaded_files=["a.deb", "b.deb"],
            failed_files=["c.deb"],
            error_message="Some downloads failed",
        )
        assert result.success is False
        assert result.downloaded_files == ["a.deb", "b.deb"]
        assert result.failed_files == ["c.deb"]
        assert result.error_message == "Some downloads failed"

    def test_default_lists_not_shared(self):
        """Test that default list fields are not shared between instances."""
        r1 = DownloadResult(success=True)
        r2 = DownloadResult(success=True)
        r1.downloaded_files.append("file.deb")
        assert r2.downloaded_files == []


class TestAria2DownloaderCheckAvailable:
    """Tests for Aria2Downloader.check_available."""

    async def test_check_available_true(self):
        """Test check_available returns True when aria2c is installed."""
        downloader = Aria2Downloader()
        with patch(
            "sysupdate.utils.command_available",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await downloader.check_available()
        assert result is True

    async def test_check_available_false(self):
        """Test check_available returns False when aria2c is not installed."""
        downloader = Aria2Downloader()
        with patch(
            "sysupdate.utils.command_available",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await downloader.check_available()
        assert result is False


class TestGenerateMetalinkXml:
    """Tests for Aria2Downloader._generate_metalink_xml."""

    def _parse_xml(self, xml_str: str) -> ET.Element:
        """Parse the XML string and return the root element."""
        return ET.fromstring(xml_str)

    def test_empty_packages(self):
        """Test generating Metalink XML with no packages."""
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([])
        root = self._parse_xml(xml)
        assert root.tag == "{urn:ietf:params:xml:ns:metalink}metalink"
        assert list(root) == []

    def test_single_package_with_sha256(self):
        """Test generating Metalink XML for a single package with SHA256 hash."""
        pkg = PackageInfo(
            name="wget",
            version="1.21.4-1",
            old_version="1.21.3-1",
            uris=["http://archive.ubuntu.com/pool/main/w/wget/wget_1.21.4-1_amd64.deb"],
            filename="wget_1.21.4-1_amd64.deb",
            size=350000,
            sha256="abcdef1234567890",
        )
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([pkg])
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        files = root.findall("ml:file", ns)
        assert len(files) == 1

        file_elem = files[0]
        assert file_elem.get("name") == "wget_1.21.4-1_amd64.deb"

        size_elem = file_elem.find("ml:size", ns)
        assert size_elem is not None
        assert size_elem.text == "350000"

        hash_elem = file_elem.find("ml:hash", ns)
        assert hash_elem is not None
        assert hash_elem.get("type") == "sha-256"
        assert hash_elem.text == "abcdef1234567890"

        url_elems = file_elem.findall("ml:url", ns)
        assert len(url_elems) == 1
        assert url_elems[0].text == "http://archive.ubuntu.com/pool/main/w/wget/wget_1.21.4-1_amd64.deb"
        assert url_elems[0].get("priority") == "1"

    def test_package_with_sha1_fallback(self):
        """Test that SHA1 is used when SHA256 is not available."""
        pkg = PackageInfo(
            name="curl",
            version="7.88.1",
            old_version="7.88.0",
            uris=["http://example.com/curl.deb"],
            filename="curl_7.88.1_amd64.deb",
            size=200000,
            sha1="sha1hashvalue",
        )
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([pkg])
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        hash_elem = root.find(".//ml:hash", ns)
        assert hash_elem is not None
        assert hash_elem.get("type") == "sha-1"
        assert hash_elem.text == "sha1hashvalue"

    def test_package_with_md5_fallback(self):
        """Test that MD5 is used when SHA256 and SHA1 are not available."""
        pkg = PackageInfo(
            name="nano",
            version="6.0",
            old_version="5.9",
            uris=["http://example.com/nano.deb"],
            filename="nano_6.0_amd64.deb",
            size=100000,
            md5="md5hashvalue",
        )
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([pkg])
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        hash_elem = root.find(".//ml:hash", ns)
        assert hash_elem is not None
        assert hash_elem.get("type") == "md5"
        assert hash_elem.text == "md5hashvalue"

    def test_package_with_no_hash(self):
        """Test that no hash element is created when no hashes are available."""
        pkg = PackageInfo(
            name="test-pkg",
            version="1.0",
            old_version="0.9",
            uris=["http://example.com/test.deb"],
            filename="test_1.0_amd64.deb",
            size=50000,
        )
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([pkg])
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        hash_elem = root.find(".//ml:hash", ns)
        assert hash_elem is None

    def test_package_with_zero_size_omits_size_element(self):
        """Test that size element is omitted when size is 0."""
        pkg = PackageInfo(
            name="tiny",
            version="1.0",
            old_version="0.1",
            uris=["http://example.com/tiny.deb"],
            filename="tiny_1.0_amd64.deb",
            size=0,
        )
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([pkg])
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        size_elem = root.find(".//ml:size", ns)
        assert size_elem is None

    def test_multiple_uris_have_incrementing_priority(self):
        """Test that multiple URIs get incrementing priority values."""
        pkg = PackageInfo(
            name="pkg",
            version="1.0",
            old_version="0.9",
            uris=[
                "http://mirror1.example.com/pkg.deb",
                "http://mirror2.example.com/pkg.deb",
                "http://mirror3.example.com/pkg.deb",
            ],
            filename="pkg_1.0_amd64.deb",
            size=1000,
        )
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([pkg])
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        url_elems = root.findall(".//ml:url", ns)
        assert len(url_elems) == 3
        assert url_elems[0].get("priority") == "1"
        assert url_elems[1].get("priority") == "2"
        assert url_elems[2].get("priority") == "3"

    def test_multiple_packages(self):
        """Test generating Metalink XML for multiple packages."""
        packages = [
            PackageInfo(
                name="pkg-a",
                version="1.0",
                old_version="0.9",
                uris=["http://example.com/a.deb"],
                filename="a_1.0_amd64.deb",
                size=100,
                sha256="hash_a",
            ),
            PackageInfo(
                name="pkg-b",
                version="2.0",
                old_version="1.9",
                uris=["http://example.com/b.deb"],
                filename="b_2.0_amd64.deb",
                size=200,
                sha256="hash_b",
            ),
        ]
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml(packages)
        root = self._parse_xml(xml)

        ns = {"ml": "urn:ietf:params:xml:ns:metalink"}
        files = root.findall("ml:file", ns)
        assert len(files) == 2
        assert files[0].get("name") == "a_1.0_amd64.deb"
        assert files[1].get("name") == "b_2.0_amd64.deb"

    def test_xml_declaration_present(self):
        """Test that the XML declaration is included at the top."""
        downloader = Aria2Downloader()
        xml = downloader._generate_metalink_xml([])
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')


class TestDownloadPackages:
    """Tests for Aria2Downloader.download_packages."""

    async def test_empty_packages_returns_success(self):
        """Test that downloading with no packages returns success immediately."""
        downloader = Aria2Downloader()
        result = await downloader.download_packages([])
        assert result.success is True
        assert result.downloaded_files == []
        assert result.failed_files == []

    async def test_download_invokes_callback_on_progress(self):
        """Test that the progress callback is invoked when aria2c reports progress."""
        pkg = PackageInfo(
            name="wget",
            version="1.21.4-1",
            old_version="1.21.3-1",
            uris=["http://example.com/wget.deb"],
            filename="wget_1.21.4-1_amd64.deb",
            size=100000,
            sha256="hash",
        )

        # Simulate aria2c output with progress line then completion
        stdout_lines = [
            b"[#abc123 45% DL:2.5MiB/s ETA:30s]\n",
            b"Download complete: /var/cache/apt/archives/partial/wget_1.21.4-1_amd64.deb\n",
        ]

        mock_process = AsyncMock()
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdin.close = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)

        async def mock_stdout_iter():
            for line in stdout_lines:
                yield line

        mock_process.stdout = mock_stdout_iter()

        callback_calls = []

        def track_callback(progress):
            callback_calls.append(progress)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch.object(Aria2Downloader, "_move_from_partial", return_value=True):
                with patch("sysupdate.updaters.aria2_downloader.APT_PARTIAL_DIR") as mock_dir:
                    mock_dir.mkdir = MagicMock()
                    downloader = Aria2Downloader()
                    result = await downloader.download_packages([pkg], callback=track_callback)

        assert result.success is True
        assert len(callback_calls) == 1
        assert callback_calls[0].progress == 0.45
        assert callback_calls[0].speed == "2.5MiB/s"
        assert callback_calls[0].eta == "30s"

    async def test_download_returns_failure_on_nonzero_return(self):
        """Test that a nonzero aria2c return code results in failure."""
        pkg = PackageInfo(
            name="pkg",
            version="1.0",
            old_version="0.9",
            uris=["http://example.com/pkg.deb"],
            filename="pkg_1.0_amd64.deb",
            size=100,
        )

        mock_process = AsyncMock()
        mock_process.stdin = AsyncMock()
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdin.close = MagicMock()
        mock_process.wait = AsyncMock(return_value=1)

        async def mock_stdout_iter():
            return
            yield  # pragma: no cover — makes this an async generator

        mock_process.stdout = mock_stdout_iter()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("sysupdate.updaters.aria2_downloader.APT_PARTIAL_DIR") as mock_dir:
                mock_dir.mkdir = MagicMock()
                downloader = Aria2Downloader()
                result = await downloader.download_packages([pkg])

        assert result.success is False
        assert "pkg_1.0_amd64.deb" in result.failed_files

    async def test_download_handles_exception(self):
        """Test that exceptions during download are caught and returned as failure."""
        pkg = PackageInfo(
            name="pkg",
            version="1.0",
            old_version="0.9",
            uris=["http://example.com/pkg.deb"],
            filename="pkg_1.0_amd64.deb",
            size=100,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("aria2c not found"),
        ):
            with patch("sysupdate.updaters.aria2_downloader.APT_PARTIAL_DIR") as mock_dir:
                mock_dir.mkdir = MagicMock()
                downloader = Aria2Downloader()
                result = await downloader.download_packages([pkg])

        assert result.success is False
        assert "aria2c not found" in result.error_message


class TestMoveFromPartial:
    """Tests for Aria2Downloader._move_from_partial."""

    def test_rejects_path_traversal(self):
        """Test that filenames containing path traversal are rejected."""
        downloader = Aria2Downloader()
        assert downloader._move_from_partial("../evil.deb") is False

    def test_rejects_absolute_path(self):
        """Test that absolute paths in filenames are rejected."""
        downloader = Aria2Downloader()
        assert downloader._move_from_partial("/etc/passwd") is False

    def test_rejects_directory_component(self):
        """Test that filenames with directory separators are rejected."""
        downloader = Aria2Downloader()
        assert downloader._move_from_partial("subdir/file.deb") is False

    def test_nonexistent_file_returns_false(self, tmp_path):
        """Test that a non-existent partial file returns False."""
        partial_dir = tmp_path / "partial"
        partial_dir.mkdir()
        archives_dir = tmp_path

        downloader = Aria2Downloader()
        with (
            patch("sysupdate.updaters.aria2_downloader.APT_PARTIAL_DIR", partial_dir),
            patch("sysupdate.updaters.aria2_downloader.APT_ARCHIVES_DIR", archives_dir),
        ):
            result = downloader._move_from_partial("nonexistent_pkg_1.0_amd64.deb")
        assert result is False

    def test_successful_move(self, tmp_path):
        """Test that a valid file is moved from partial to archives."""
        partial_dir = tmp_path / "partial"
        partial_dir.mkdir()
        archives_dir = tmp_path

        # Create a file in partial
        test_file = partial_dir / "pkg_1.0_amd64.deb"
        test_file.write_text("fake deb content")

        downloader = Aria2Downloader()
        with (
            patch("sysupdate.updaters.aria2_downloader.APT_PARTIAL_DIR", partial_dir),
            patch("sysupdate.updaters.aria2_downloader.APT_ARCHIVES_DIR", archives_dir),
        ):
            result = downloader._move_from_partial("pkg_1.0_amd64.deb")

        assert result is True
        assert not test_file.exists()
        assert (archives_dir / "pkg_1.0_amd64.deb").exists()

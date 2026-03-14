"""Tests for the APT cache wrapper module."""

from unittest.mock import MagicMock, patch

import pytest

from sysupdate.updaters.apt_cache import PackageInfo, AptCacheWrapper


class TestPackageInfo:
    """Tests for the PackageInfo dataclass."""

    def test_creation_with_all_fields(self):
        """Test creating a PackageInfo with all fields specified."""
        pkg = PackageInfo(
            name="libssl3",
            version="3.0.13-0ubuntu1",
            old_version="3.0.11-0ubuntu1",
            uris=["http://archive.ubuntu.com/pool/main/o/openssl/libssl3_3.0.13_amd64.deb"],
            filename="libssl3_3.0.13-0ubuntu1_amd64.deb",
            size=1234567,
            sha256="abc123def456",
            sha1="sha1hash",
            md5="md5hash",
        )
        assert pkg.name == "libssl3"
        assert pkg.version == "3.0.13-0ubuntu1"
        assert pkg.old_version == "3.0.11-0ubuntu1"
        assert len(pkg.uris) == 1
        assert pkg.filename == "libssl3_3.0.13-0ubuntu1_amd64.deb"
        assert pkg.size == 1234567
        assert pkg.sha256 == "abc123def456"
        assert pkg.sha1 == "sha1hash"
        assert pkg.md5 == "md5hash"

    def test_creation_with_defaults(self):
        """Test creating a PackageInfo with only required fields."""
        pkg = PackageInfo(name="wget", version="1.21.4-1", old_version="1.21.3-1")
        assert pkg.name == "wget"
        assert pkg.version == "1.21.4-1"
        assert pkg.old_version == "1.21.3-1"
        assert pkg.uris == []
        assert pkg.filename == ""
        assert pkg.size == 0
        assert pkg.sha256 == ""
        assert pkg.sha1 == ""
        assert pkg.md5 == ""

    def test_default_uris_not_shared_between_instances(self):
        """Test that the default uris list is not shared between instances."""
        pkg1 = PackageInfo(name="a", version="1", old_version="0")
        pkg2 = PackageInfo(name="b", version="1", old_version="0")
        pkg1.uris.append("http://example.com/a.deb")
        assert pkg2.uris == []


class TestPackageInfoDestfile:
    """Tests for the PackageInfo.destfile property."""

    def test_destfile_with_filename(self):
        """Test destfile returns basename of filename when set."""
        pkg = PackageInfo(
            name="libssl3",
            version="3.0.13-0ubuntu1",
            old_version="3.0.11",
            filename="pool/main/o/openssl/libssl3_3.0.13-0ubuntu1_amd64.deb",
        )
        assert pkg.destfile == "libssl3_3.0.13-0ubuntu1_amd64.deb"

    def test_destfile_without_filename_no_epoch(self):
        """Test destfile generates name from package info when no filename, no epoch."""
        pkg = PackageInfo(
            name="wget",
            version="1.21.4-1",
            old_version="1.21.3-1",
        )
        assert pkg.destfile == "wget_1.21.4-1_amd64.deb"

    def test_destfile_without_filename_with_epoch(self):
        """Test destfile encodes colons as %3a (APT convention for epoch versions)."""
        pkg = PackageInfo(
            name="vim",
            version="2:9.0.1000-1",
            old_version="2:8.2.500-1",
        )
        assert pkg.destfile == "vim_2%3a9.0.1000-1_amd64.deb"

    def test_destfile_with_multiple_colons(self):
        """Test destfile encodes all colons in version string."""
        pkg = PackageInfo(
            name="test-pkg",
            version="1:2:3",
            old_version="0",
        )
        assert pkg.destfile == "test-pkg_1%3a2%3a3_amd64.deb"

    def test_destfile_with_simple_filename(self):
        """Test destfile with a filename that has no directory components."""
        pkg = PackageInfo(
            name="curl",
            version="7.88.1",
            old_version="7.88.0",
            filename="curl_7.88.1_amd64.deb",
        )
        assert pkg.destfile == "curl_7.88.1_amd64.deb"


class TestAptCacheWrapper:
    """Tests for the AptCacheWrapper class."""

    def test_init_raises_when_apt_unavailable(self):
        """Test that AptCacheWrapper raises RuntimeError when apt module is missing."""
        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="python3-apt is not available"):
                AptCacheWrapper()

    def test_init_succeeds_when_apt_available(self):
        """Test that AptCacheWrapper initializes when apt module is present."""
        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            assert wrapper._cache is None

    def test_get_upgradable_packages_returns_package_infos(self):
        """Test that get_upgradable_packages returns correctly populated PackageInfo objects."""
        # Build mock package objects
        mock_installed = MagicMock()
        mock_installed.version = "3.0.11"

        mock_candidate = MagicMock()
        mock_candidate.version = "3.0.13"
        mock_candidate.uris = [
            "http://archive.ubuntu.com/pool/main/o/openssl/libssl3_3.0.13_amd64.deb"
        ]
        mock_candidate.size = 1234567
        mock_candidate.sha256 = "abc123"
        mock_candidate.sha1 = "sha1val"
        mock_candidate.md5 = "md5val"

        mock_pkg = MagicMock()
        mock_pkg.shortname = "libssl3"
        mock_pkg.marked_upgrade = True
        mock_pkg.marked_install = False
        mock_pkg.candidate = mock_candidate
        mock_pkg.installed = mock_installed

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [mock_pkg]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert len(packages) == 1
        pkg = packages[0]
        assert isinstance(pkg, PackageInfo)
        assert pkg.name == "libssl3"
        assert pkg.version == "3.0.13"
        assert pkg.old_version == "3.0.11"
        assert pkg.sha256 == "abc123"
        assert pkg.sha1 == "sha1val"
        assert pkg.md5 == "md5val"
        assert pkg.size == 1234567
        assert len(pkg.uris) == 1

    def test_get_upgradable_packages_skips_non_upgrade(self):
        """Test that packages not marked for upgrade or install are skipped."""
        mock_pkg = MagicMock()
        mock_pkg.marked_upgrade = False
        mock_pkg.marked_install = False

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [mock_pkg]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert packages == []

    def test_get_upgradable_packages_skips_no_candidate(self):
        """Test that packages with no candidate are skipped."""
        mock_pkg = MagicMock()
        mock_pkg.marked_upgrade = True
        mock_pkg.marked_install = False
        mock_pkg.candidate = None

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [mock_pkg]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert packages == []

    def test_get_upgradable_packages_skips_no_uris(self):
        """Test that packages with empty URIs are skipped."""
        mock_candidate = MagicMock()
        mock_candidate.version = "1.0"
        mock_candidate.uris = []
        mock_candidate.size = 100

        mock_pkg = MagicMock()
        mock_pkg.marked_upgrade = True
        mock_pkg.marked_install = False
        mock_pkg.candidate = mock_candidate

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [mock_pkg]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert packages == []

    def test_get_upgradable_packages_handles_uri_attribute_error(self):
        """Test that AttributeError when accessing URIs is handled gracefully."""
        mock_candidate = MagicMock()
        mock_candidate.version = "1.0"
        mock_candidate.uris = property(lambda self: (_ for _ in ()).throw(AttributeError))
        type(mock_candidate).uris = property(lambda self: (_ for _ in ()).throw(AttributeError))

        mock_pkg = MagicMock()
        mock_pkg.marked_upgrade = True
        mock_pkg.marked_install = False
        mock_pkg.candidate = mock_candidate

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [mock_pkg]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert packages == []

    def test_get_upgradable_packages_no_installed_version(self):
        """Test handling of packages with no installed version (new installs)."""
        mock_candidate = MagicMock()
        mock_candidate.version = "1.0"
        mock_candidate.uris = ["http://example.com/pkg_1.0_amd64.deb"]
        mock_candidate.size = 500
        mock_candidate.sha256 = "hash256"
        mock_candidate.sha1 = ""
        mock_candidate.md5 = ""

        mock_pkg = MagicMock()
        mock_pkg.shortname = "new-pkg"
        mock_pkg.marked_upgrade = False
        mock_pkg.marked_install = True
        mock_pkg.candidate = mock_candidate
        mock_pkg.installed = None

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [mock_pkg]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert len(packages) == 1
        assert packages[0].old_version == ""

    def test_get_upgradable_packages_multiple(self):
        """Test getting multiple upgradable packages."""

        def make_mock_pkg(name, old_ver, new_ver):
            mock_installed = MagicMock()
            mock_installed.version = old_ver

            mock_candidate = MagicMock()
            mock_candidate.version = new_ver
            mock_candidate.uris = [f"http://example.com/{name}_{new_ver}_amd64.deb"]
            mock_candidate.size = 1000
            mock_candidate.sha256 = "hash"
            mock_candidate.sha1 = ""
            mock_candidate.md5 = ""

            mock_pkg = MagicMock()
            mock_pkg.shortname = name
            mock_pkg.marked_upgrade = True
            mock_pkg.marked_install = False
            mock_pkg.candidate = mock_candidate
            mock_pkg.installed = mock_installed
            return mock_pkg

        mock_cache = MagicMock()
        mock_cache.get_changes.return_value = [
            make_mock_pkg("libssl3", "3.0.11", "3.0.13"),
            make_mock_pkg("openssl", "3.0.11", "3.0.13"),
            make_mock_pkg("wget", "1.21.3", "1.21.4"),
        ]

        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            wrapper = AptCacheWrapper()
            wrapper._cache = mock_cache

            packages = wrapper.get_upgradable_packages()

        assert len(packages) == 3
        assert [p.name for p in packages] == ["libssl3", "openssl", "wget"]


class TestIsAptAvailable:
    """Tests for the is_apt_available function."""

    def test_returns_true_when_apt_available(self):
        """Test is_apt_available returns True when python3-apt is importable."""
        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", True):
            from sysupdate.updaters.apt_cache import is_apt_available

            assert is_apt_available() is True

    def test_returns_false_when_apt_unavailable(self):
        """Test is_apt_available returns False when python3-apt is not importable."""
        with patch("sysupdate.updaters.apt_cache.APT_AVAILABLE", False):
            from sysupdate.updaters.apt_cache import is_apt_available

            assert is_apt_available() is False

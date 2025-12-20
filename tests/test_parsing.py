"""Tests for output parsing utilities."""

from sysupdate.utils.parsing import (
    parse_apt_output,
    parse_apt_progress,
    parse_flatpak_output,
    parse_flatpak_progress,
    count_apt_upgrades,
    AptUpgradeProgressTracker,
    AptUpdateProgressTracker,
)


class TestParseAptOutput:
    """Tests for parse_apt_output function."""

    def test_parse_upgrade_output(self, apt_upgrade_output):
        """Test parsing APT upgrade output with packages."""
        packages = parse_apt_output(apt_upgrade_output)

        assert len(packages) == 5
        package_names = {p.name for p in packages}
        assert "libssl3" in package_names
        assert "openssl" in package_names
        assert "python3.11" in package_names
        assert "wget" in package_names

    def test_parse_package_versions(self, apt_upgrade_output):
        """Test that package versions are correctly extracted."""
        packages = parse_apt_output(apt_upgrade_output)

        libssl = next((p for p in packages if p.name == "libssl3"), None)
        assert libssl is not None
        assert libssl.old_version == "3.0.11"
        assert libssl.new_version == "3.0.13"

    def test_parse_no_updates(self, apt_no_updates_output):
        """Test parsing when no packages are updated."""
        packages = parse_apt_output(apt_no_updates_output)
        assert len(packages) == 0

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        packages = parse_apt_output("")
        assert len(packages) == 0

    def test_removes_architecture_suffix(self):
        """Test that architecture suffixes are removed from package names."""
        output = "Unpacking libssl3:amd64 (3.0.13) over (3.0.11) ..."
        packages = parse_apt_output(output)

        assert len(packages) == 1
        assert packages[0].name == "libssl3"

    def test_status_is_complete(self, apt_upgrade_output):
        """Test that parsed packages have complete status."""
        packages = parse_apt_output(apt_upgrade_output)

        for pkg in packages:
            assert pkg.status == "complete"


class TestParseAptProgress:
    """Tests for parse_apt_progress function."""

    def test_parse_progress_percentage(self):
        """Test parsing progress percentage line."""
        result = parse_apt_progress("Progress: [ 45%]")

        assert result is not None
        _package, progress = result
        assert progress == 0.45

    def test_parse_get_line(self):
        """Test parsing Get: download line."""
        result = parse_apt_progress("Get:1 http://archive.ubuntu.com libssl3")

        assert result is not None
        package, progress = result
        assert package == "libssl3"
        assert progress == -1.0  # Unknown progress

    def test_parse_unpacking_line(self):
        """Test parsing Unpacking line."""
        result = parse_apt_progress("Unpacking libssl3:amd64 (3.0.13) over (3.0.11)")

        assert result is not None
        package, _progress = result
        assert package == "libssl3"

    def test_parse_setting_up_line(self):
        """Test parsing Setting up line."""
        result = parse_apt_progress("Setting up python3.11 (3.11.8) ...")

        assert result is not None
        package, _progress = result
        assert package == "python3.11"

    def test_parse_irrelevant_line(self):
        """Test parsing line with no progress info."""
        result = parse_apt_progress("Reading package lists... Done")
        assert result is None

    def test_parse_empty_line(self):
        """Test parsing empty line."""
        result = parse_apt_progress("")
        assert result is None


class TestCountAptUpgrades:
    """Tests for count_apt_upgrades function."""

    def test_count_from_summary(self):
        """Test counting from upgrade summary line."""
        output = "5 upgraded, 2 newly installed, 0 to remove and 0 not upgraded."
        count = count_apt_upgrades(output)
        assert count == 5

    def test_count_from_setting_up(self):
        """Test counting from Setting up lines when no summary."""
        output = """
Setting up libssl3:amd64 (3.0.13) ...
Setting up openssl (3.0.13) ...
Setting up python3.11 (3.11.8) ...
"""
        count = count_apt_upgrades(output)
        assert count == 3

    def test_count_no_updates(self, apt_no_updates_output):
        """Test counting when all packages are up to date."""
        count = count_apt_upgrades(apt_no_updates_output)
        assert count == 0

    def test_count_empty_output(self):
        """Test counting with empty output."""
        count = count_apt_upgrades("")
        assert count == 0


class TestParseFlatpakOutput:
    """Tests for parse_flatpak_output function."""

    def test_parse_update_output(self, flatpak_update_output):
        """Test parsing Flatpak update output."""
        packages = parse_flatpak_output(flatpak_update_output)

        # Should only get actual apps, not runtimes
        package_names = {p.name for p in packages}
        assert "firefox" in package_names
        assert "GIMP" in package_names
        assert "LibreOffice" in package_names

        # Should NOT include runtimes/extensions
        assert "Platform" not in package_names
        assert "Locale" not in package_names

    def test_parse_no_updates(self, flatpak_no_updates_output):
        """Test parsing when no updates available."""
        packages = parse_flatpak_output(flatpak_no_updates_output)
        assert len(packages) == 0

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        packages = parse_flatpak_output("")
        assert len(packages) == 0

    def test_extracts_display_name(self):
        """Test that display name is extracted from full ref."""
        output = "1. org.mozilla.firefox stable"
        packages = parse_flatpak_output(output)

        assert len(packages) == 1
        assert packages[0].name == "firefox"

    def test_status_is_complete(self, flatpak_update_output):
        """Test that parsed packages have complete status."""
        packages = parse_flatpak_output(flatpak_update_output)

        for pkg in packages:
            assert pkg.status == "complete"


class TestParseFlatpakProgress:
    """Tests for parse_flatpak_progress function."""

    def test_parse_download_progress(self):
        """Test parsing download progress line."""
        result = parse_flatpak_progress("Downloading org.mozilla.firefox... 45%")

        assert result is not None
        app, progress = result
        assert app == "firefox"
        assert progress == 0.45

    def test_parse_installing_line(self):
        """Test parsing Installing line."""
        result = parse_flatpak_progress("Installing org.gimp.GIMP")

        assert result is not None
        app, progress = result
        assert app == "GIMP"
        assert progress == -1.0  # Unknown progress

    def test_parse_updating_line(self):
        """Test parsing Updating line."""
        result = parse_flatpak_progress("Updating org.libreoffice.LibreOffice")

        assert result is not None
        app, _progress = result
        assert app == "LibreOffice"

    def test_parse_irrelevant_line(self):
        """Test parsing line with no progress info."""
        result = parse_flatpak_progress("Looking for updates...")
        assert result is None

    def test_parse_empty_line(self):
        """Test parsing empty line."""
        result = parse_flatpak_progress("")
        assert result is None


class TestAptUpgradeProgressTracker:
    """Tests for AptUpgradeProgressTracker class."""

    def test_initialization(self):
        """Test tracker starts with default values."""
        tracker = AptUpgradeProgressTracker()

        assert tracker.total_packages == 0
        assert tracker.download_count == 0
        assert tracker.install_count == 0
        assert tracker.current_package == ""
        assert tracker.last_progress == 0.0
        assert not tracker.is_up_to_date

    def test_parse_total_package_count(self):
        """Test parsing the package count from summary line."""
        tracker = AptUpgradeProgressTracker()

        tracker.parse_line("5 upgraded, 2 newly installed, 0 to remove.")
        assert tracker.total_packages == 5

    def test_parse_up_to_date(self):
        """Test detecting 'up to date' message."""
        tracker = AptUpgradeProgressTracker()

        result = tracker.parse_line("All packages are up to date.")

        assert result is not None
        assert result["phase"] == "complete"
        assert result["progress"] == 1.0
        assert tracker.is_up_to_date

    def test_parse_download_progress(self):
        """Test tracking download progress via Get: lines."""
        tracker = AptUpgradeProgressTracker()

        # First set total
        tracker.parse_line("5 upgraded, 0 newly installed, 0 to remove.")
        assert tracker.total_packages == 5

        # Then track downloads
        result = tracker.parse_line("Get:1 http://archive.ubuntu.com libssl3 3.0.13 [1,234 kB]")

        assert result is not None
        assert result["phase"] == "downloading"
        assert result["current_package"] == "libssl3"
        assert result["progress"] == 0.1  # 1/5 * 0.5 = 0.1

    def test_parse_install_progress(self):
        """Test tracking installation progress via Setting up lines."""
        tracker = AptUpgradeProgressTracker()

        # First set total
        tracker.parse_line("4 upgraded, 0 newly installed, 0 to remove.")
        assert tracker.total_packages == 4

        # Simulate download complete (set last_progress to 0.5)
        tracker.last_progress = 0.5

        # Then track installation
        result = tracker.parse_line("Setting up libssl3 (3.0.13) ...")

        assert result is not None
        assert result["phase"] == "installing"
        assert result["current_package"] == "libssl3"
        assert result["completed_packages"] == 1
        # Progress should be 0.5 + (1/4 * 0.5) = 0.625
        assert result["progress"] == 0.625

    def test_progress_only_increases(self):
        """Test that progress never decreases."""
        tracker = AptUpgradeProgressTracker()

        tracker.parse_line("10 upgraded, 0 newly installed, 0 to remove.")

        result1 = tracker.parse_line("Get:5 http://archive.ubuntu.com pkg5 1.0 [100 kB]")
        assert result1 is not None
        assert result1["progress"] == 0.25  # 5/10 * 0.5

        # Earlier package should not decrease progress
        result2 = tracker.parse_line("Get:3 http://archive.ubuntu.com pkg3 1.0 [100 kB]")
        assert result2 is None  # No update because progress would decrease

    def test_removes_architecture_suffix(self):
        """Test that architecture suffixes are removed from package names."""
        tracker = AptUpgradeProgressTracker()

        tracker.parse_line("2 upgraded, 0 newly installed, 0 to remove.")
        tracker.parse_line("Get:1 http://archive.ubuntu.com libssl3:amd64 3.0.13 [100 kB]")

        assert tracker.current_package == "libssl3"

    def test_trigger_processing(self):
        """Test tracking trigger processing phase."""
        tracker = AptUpgradeProgressTracker()

        tracker.parse_line("2 upgraded, 0 newly installed, 0 to remove.")
        tracker.last_progress = 0.9
        tracker.install_count = 2

        result = tracker.parse_line("Processing triggers for man-db (2.12.0-1) ...")

        assert result is not None
        assert result["phase"] == "installing"
        assert result["message"] == "Processing triggers..."
        assert result["progress"] <= 0.99

    def test_full_upgrade_sequence(self):
        """Test a complete upgrade sequence."""
        tracker = AptUpgradeProgressTracker()

        # Start
        result = tracker.parse_line("Reading package lists... Done")
        assert result is None

        # Package count
        result = tracker.parse_line("2 upgraded, 0 newly installed, 0 to remove.")
        assert result is None
        assert tracker.total_packages == 2

        # Download 1
        result = tracker.parse_line("Get:1 http://archive.ubuntu.com pkg1 1.0 [100 kB]")
        assert result is not None
        assert result["phase"] == "downloading"
        assert result["progress"] == 0.25  # 1/2 * 0.5

        # Download 2
        result = tracker.parse_line("Get:2 http://archive.ubuntu.com pkg2 2.0 [200 kB]")
        assert result is not None
        assert result["phase"] == "downloading"
        assert result["progress"] == 0.5  # 2/2 * 0.5

        # Install 1
        result = tracker.parse_line("Setting up pkg1 (1.0) ...")
        assert result is not None
        assert result["phase"] == "installing"
        assert result["progress"] == 0.75  # 0.5 + 1/2 * 0.5

        # Install 2
        result = tracker.parse_line("Setting up pkg2 (2.0) ...")
        assert result is not None
        assert result["phase"] == "installing"
        assert result["progress"] == 1.0  # 0.5 + 2/2 * 0.5

    def test_cached_packages_detection(self):
        """Test detection when packages come from cache (no downloads)."""
        tracker = AptUpgradeProgressTracker()

        # Set total packages
        tracker.parse_line("3 upgraded, 0 newly installed, 0 to remove.")
        assert tracker.total_packages == 3

        # Go straight to unpacking (no Get: lines)
        result = tracker.parse_line("Unpacking libssl3:amd64 (3.0.13) over (3.0.11) ...")

        assert tracker._using_cache is True
        assert result is not None
        assert result["phase"] == "installing"
        assert result["progress"] > 0.0
        assert result["progress"] <= 0.5  # Unpacking is 0-50% in cache mode

    def test_cached_packages_full_sequence(self):
        """Test complete sequence when packages are cached."""
        tracker = AptUpgradeProgressTracker()

        # Package count
        tracker.parse_line("2 upgraded, 0 newly installed, 0 to remove.")

        # Unpacking (no downloads, from cache)
        result = tracker.parse_line("Unpacking pkg1:amd64 (1.0) over (0.9) ...")
        assert result is not None
        assert result["phase"] == "installing"
        assert result["progress"] == 0.25  # 1/2 * 0.5

        result = tracker.parse_line("Unpacking pkg2:amd64 (2.0) over (1.9) ...")
        assert result is not None
        assert result["progress"] == 0.5  # 2/2 * 0.5

        # Setting up
        result = tracker.parse_line("Setting up pkg1 (1.0) ...")
        assert result is not None
        assert result["progress"] == 0.75  # 0.5 + 1/2 * 0.5

        result = tracker.parse_line("Setting up pkg2 (2.0) ...")
        assert result is not None
        assert result["progress"] == 1.0  # 0.5 + 2/2 * 0.5

    def test_progress_without_total(self):
        """Test progress reporting when total is not yet known."""
        tracker = AptUpgradeProgressTracker()

        # Get: lines before summary
        result = tracker.parse_line("Get:1 http://archive.ubuntu.com libssl3 3.0.13 [100 kB]")

        assert result is not None
        assert result["progress"] > 0.0
        assert result["progress"] < 0.5  # Conservative before knowing total
        assert result["total_packages"] == 0  # Unknown

    def test_progress_recalculated_when_total_known(self):
        """Test that progress is recalculated when total becomes known."""
        tracker = AptUpgradeProgressTracker()

        # Downloads before we know the total
        tracker.parse_line("Get:1 http://archive.ubuntu.com pkg1 1.0 [100 kB]")
        tracker.parse_line("Get:2 http://archive.ubuntu.com pkg2 1.0 [100 kB]")

        assert len(tracker._pending_downloads) == 2

        # Now we learn the total
        result = tracker.parse_line("4 upgraded, 0 newly installed, 0 to remove.")

        # Should recalculate and report correct progress
        assert result is not None
        assert result["progress"] == 0.25  # 2/4 * 0.5
        assert result["total_packages"] == 4


class TestAptUpdateProgressTracker:
    """Tests for AptUpdateProgressTracker class."""

    def test_initialization(self):
        """Test tracker starts with default values."""
        tracker = AptUpdateProgressTracker()

        assert tracker.estimated_repos == 10
        assert tracker.seen_repos == 0
        assert tracker.last_progress == 0.0

    def test_initialization_custom_estimate(self):
        """Test tracker with custom estimated repos."""
        tracker = AptUpdateProgressTracker(estimated_repos=20)
        assert tracker.estimated_repos == 20

    def test_tracks_hit_lines(self):
        """Test tracking Hit: repository lines."""
        tracker = AptUpdateProgressTracker(estimated_repos=5)

        progress = tracker.parse_line("Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease")

        assert progress is not None
        assert progress > 0.0
        assert progress < 1.0
        assert tracker.seen_repos == 1

    def test_tracks_get_lines(self):
        """Test tracking Get: repository lines."""
        tracker = AptUpdateProgressTracker(estimated_repos=5)

        progress = tracker.parse_line("Get:1 http://security.ubuntu.com jammy-security InRelease [110 kB]")

        assert progress is not None
        assert progress > 0.0
        assert tracker.seen_repos == 1

    def test_ignores_irrelevant_lines(self):
        """Test that non-Hit/Get lines are ignored."""
        tracker = AptUpdateProgressTracker()

        result = tracker.parse_line("Reading package lists... Done")
        assert result is None

        result = tracker.parse_line("Building dependency tree... Done")
        assert result is None

    def test_progress_never_reaches_100(self):
        """Test that progress never reaches 100% until completion."""
        tracker = AptUpdateProgressTracker(estimated_repos=3)

        # Process many lines
        for i in range(1, 10):
            tracker.parse_line(f"Hit:{i} http://archive.ubuntu.com/ubuntu repo{i}")

        # Progress should cap at 95%
        assert tracker.last_progress <= 0.95

    def test_progress_increases_monotonically(self):
        """Test that progress only increases."""
        tracker = AptUpdateProgressTracker(estimated_repos=10)
        last = 0.0

        lines = [
            "Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease",
            "Hit:2 http://archive.ubuntu.com/ubuntu jammy-updates InRelease",
            "Get:3 http://security.ubuntu.com jammy-security InRelease [110 kB]",
            "Hit:4 http://archive.ubuntu.com/ubuntu jammy-backports InRelease",
        ]

        for line in lines:
            progress = tracker.parse_line(line)
            if progress is not None:
                assert progress > last
                last = progress

    def test_estimate_adjusts_with_more_repos(self):
        """Test that estimate grows as we see more repos than expected."""
        tracker = AptUpdateProgressTracker(estimated_repos=3)

        # Process more repos than estimated
        for i in range(1, 8):
            tracker.parse_line(f"Hit:{i} http://archive.ubuntu.com/ubuntu repo{i}")

        # Should have adjusted estimate
        assert tracker.seen_repos == 7
        # Progress should still be < 1.0
        assert tracker.last_progress < 1.0

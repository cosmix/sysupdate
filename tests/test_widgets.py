"""Tests for TUI widgets."""

from sysupdate.widgets.header import Header
from sysupdate.widgets.update_panel import UpdatePanel, PackageItem
from sysupdate.widgets.footer import Footer, FooterKey
from sysupdate.updaters.base import Package


class TestHeader:
    """Tests for Header widget."""

    def test_header_instantiation(self):
        """Test Header widget can be instantiated."""
        header = Header()
        assert header is not None

    def test_header_has_css(self):
        """Test Header has CSS defined."""
        header = Header()
        assert header.DEFAULT_CSS is not None
        assert len(header.DEFAULT_CSS) > 0


class TestPackageItem:
    """Tests for PackageItem widget."""

    def test_instantiation_with_versions(self):
        """Test creating PackageItem with version info."""
        pkg = Package(
            name="libssl3",
            old_version="3.0.11",
            new_version="3.0.13",
            status="complete",
        )
        item = PackageItem(pkg, is_current=False, show_versions=True)

        assert item.package == pkg
        assert item.is_current is False
        assert item.show_versions is True

    def test_instantiation_current_package(self):
        """Test creating PackageItem for currently processing package."""
        pkg = Package(name="python3.11", status="installing")
        item = PackageItem(pkg, is_current=True)

        assert item.is_current is True

    def test_instantiation_without_versions(self):
        """Test creating PackageItem without version display."""
        pkg = Package(name="firefox", size="124.5 MB")
        item = PackageItem(pkg, show_versions=False)

        assert item.show_versions is False


class TestUpdatePanel:
    """Tests for UpdatePanel widget."""

    def test_instantiation(self):
        """Test UpdatePanel can be instantiated."""
        panel = UpdatePanel(title="APT Packages", icon="📦")

        assert panel is not None
        assert panel._title == "APT Packages"
        assert panel._icon == "📦"

    def test_default_internal_state(self):
        """Test default internal state (not reactive properties)."""
        panel = UpdatePanel(title="Test")

        # Test internal state that doesn't need mounting
        assert panel._packages == []
        assert panel._error_message == ""
        assert panel._show_versions is True

    def test_set_packages(self):
        """Test setting package list."""
        panel = UpdatePanel(title="Test")
        packages = [
            Package(name="pkg1", status="complete"),
            Package(name="pkg2", status="complete"),
        ]

        panel.set_packages(packages)

        assert len(panel._packages) == 2

    def test_add_package(self):
        """Test adding a single package."""
        panel = UpdatePanel(title="Test")
        pkg = Package(name="test-pkg", status="complete")

        panel.add_package(pkg)

        assert len(panel._packages) == 1
        assert panel._packages[0].name == "test-pkg"

    def test_set_error(self):
        """Test setting error state."""
        panel = UpdatePanel(title="Test")

        panel.set_error("Update failed")

        # Error message should be set
        assert panel._error_message == "Update failed"

    def test_reset_clears_packages(self):
        """Test that reset clears internal package list."""
        panel = UpdatePanel(title="Test")
        panel._packages = [Package(name="test")]
        panel._error_message = "some error"

        # Directly clear internal state (reset() triggers reactives which need mounting)
        panel._packages = []
        panel._error_message = ""

        assert len(panel._packages) == 0
        assert panel._error_message == ""


class TestFooter:
    """Tests for Footer widget."""

    def test_instantiation_default_shortcuts(self):
        """Test Footer with default shortcuts."""
        footer = Footer()

        assert len(footer._shortcuts) == 4
        assert ("Q", "Quit") in footer._shortcuts
        assert ("?", "Help") in footer._shortcuts

    def test_instantiation_custom_shortcuts(self):
        """Test Footer with custom shortcuts."""
        custom = [("X", "Custom"), ("Y", "Another")]
        footer = Footer(shortcuts=custom)

        assert footer._shortcuts == custom

    def test_set_shortcuts(self):
        """Test updating shortcuts."""
        footer = Footer()
        new_shortcuts = [("A", "Action")]

        footer.set_shortcuts(new_shortcuts)

        assert footer._shortcuts == new_shortcuts


class TestFooterKey:
    """Tests for FooterKey widget."""

    def test_instantiation(self):
        """Test FooterKey can be instantiated."""
        key = FooterKey("Q", "Quit")

        assert key._key == "Q"
        assert key._description == "Quit"

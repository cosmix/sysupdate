"""Update panel widget showing progress for a package manager."""

from textual.app import ComposeResult
from textual.widgets import Static, ProgressBar
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive

from ..updaters.base import UpdatePhase, Package


class PackageItem(Static):
    """A single package item in the recent list."""

    DEFAULT_CSS = """
    PackageItem {
        height: 1;
        padding: 0;
    }

    PackageItem .pkg-icon {
        width: 2;
    }

    PackageItem .pkg-icon.complete {
        color: #9ece6a;
    }

    PackageItem .pkg-icon.active {
        color: #7dcfff;
    }

    PackageItem .pkg-name {
        width: 20;
        color: #c0caf5;
    }

    PackageItem .pkg-version {
        color: #565f89;
        width: 12;
    }

    PackageItem .pkg-arrow {
        color: #565f89;
        width: 2;
    }

    PackageItem .pkg-new-version {
        color: #9ece6a;
        width: 12;
    }

    PackageItem .pkg-size {
        color: #7dcfff;
    }
    """

    def __init__(
        self,
        package: Package,
        is_current: bool = False,
        show_versions: bool = True,
    ) -> None:
        super().__init__()
        self.package = package
        self.is_current = is_current
        self.show_versions = show_versions

    def compose(self) -> ComposeResult:
        """Create the package item content."""
        icon_class = "active" if self.is_current else "complete"
        icon = "⟳ " if self.is_current else "✓ "

        with Horizontal():
            yield Static(icon, classes=f"pkg-icon {icon_class}")
            yield Static(
                self.package.name[:24],
                classes="pkg-name"
            )

            if self.show_versions and self.package.old_version:
                yield Static(self.package.old_version[:15], classes="pkg-version")
                yield Static(" → ", classes="pkg-arrow")
                yield Static(self.package.new_version[:15], classes="pkg-new-version")
            elif self.package.size:
                yield Static(self.package.size, classes="pkg-size")


class UpdatePanel(Static):
    """Panel showing update progress for a package manager."""

    DEFAULT_CSS = """
    UpdatePanel {
        height: auto;
        min-height: 6;
        max-height: 12;
        margin: 0;
        padding: 1;
        background: #24283b;
        border: solid #414868;
        border-title-color: #7dcfff;
        border-title-style: bold;
    }

    UpdatePanel.running {
        border: solid #7dcfff;
        border-title-color: #7dcfff;
    }

    UpdatePanel.success {
        border: solid #9ece6a;
        border-title-color: #9ece6a;
    }

    UpdatePanel.error {
        border: solid #f7768e;
        border-title-color: #f7768e;
    }

    UpdatePanel .progress-row {
        height: 1;
        margin: 0;
    }

    UpdatePanel .progress-bar {
        width: 1fr;
    }

    UpdatePanel .progress-text {
        width: 20;
        text-align: right;
        color: #c0caf5;
    }

    UpdatePanel .status-row {
        height: 1;
        margin: 0;
    }

    UpdatePanel .status-label {
        color: #565f89;
        width: 8;
    }

    UpdatePanel .status-value {
        color: #c0caf5;
        width: 1fr;
    }

    UpdatePanel .status-value.speed {
        color: #7dcfff;
    }

    UpdatePanel .status-value.eta {
        color: #e0af68;
    }

    UpdatePanel .status-value.current {
        color: #9ece6a;
        text-style: italic;
    }

    UpdatePanel .recent-label {
        color: #565f89;
        height: 1;
        margin: 0;
    }

    UpdatePanel .package-list {
        height: auto;
        max-height: 3;
        margin: 0;
        overflow-y: auto;
    }

    UpdatePanel .empty-message {
        color: #565f89;
        text-style: italic;
        padding: 0;
    }

    UpdatePanel .complete-message {
        color: #9ece6a;
        text-style: bold;
        padding: 0;
    }

    UpdatePanel .error-message {
        color: #f7768e;
        padding: 0;
    }
    """

    # Reactive properties
    phase = reactive(UpdatePhase.IDLE)
    progress = reactive(0.0)
    total_packages = reactive(0)
    completed_packages = reactive(0)
    current_package = reactive("")
    speed = reactive("")
    eta = reactive("")

    def __init__(
        self,
        title: str,
        icon: str = "",
        show_versions: bool = True,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.border_title = f"{icon} {title}" if icon else title
        self._title = title
        self._icon = icon
        self._show_versions = show_versions
        self._packages: list[Package] = []
        self._error_message = ""

    def compose(self) -> ComposeResult:
        """Create the panel content."""
        with Vertical():
            # Progress bar row
            with Horizontal(classes="progress-row"):
                yield ProgressBar(
                    total=100,
                    show_eta=False,
                    classes="progress-bar",
                    id="progress-bar",
                )
                yield Static("0%  0/0 packages", classes="progress-text", id="progress-text")

            # Status row
            with Horizontal(classes="status-row"):
                yield Static("Status:", classes="status-label")
                yield Static("Waiting...", classes="status-value", id="status-current")
                yield Static("", classes="status-value speed", id="status-speed")
                yield Static("", classes="status-value eta", id="status-eta")

            # Package list
            yield Static("Recent:", classes="recent-label", id="recent-label")
            yield Vertical(id="package-list", classes="package-list")

    def watch_phase(self, phase: UpdatePhase) -> None:
        """React to phase changes."""
        self.remove_class("running", "success", "error")

        if phase == UpdatePhase.IDLE:
            pass
        elif phase in (UpdatePhase.CHECKING, UpdatePhase.DOWNLOADING, UpdatePhase.INSTALLING):
            self.add_class("running")
        elif phase == UpdatePhase.COMPLETE:
            self.add_class("success")
        elif phase == UpdatePhase.ERROR:
            self.add_class("error")

        self._update_status_display()

    def watch_progress(self, progress: float) -> None:
        """Update progress bar."""
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(progress=progress * 100)
        self._update_progress_text()

    def watch_current_package(self, _package: str) -> None:  # type: ignore[reportUnusedParameter]
        """Update current package display."""
        self._update_status_display()

    def _update_progress_text(self) -> None:
        """Update the progress text display."""
        try:
            text = self.query_one("#progress-text", Static)
            if self.phase == UpdatePhase.COMPLETE:
                text.update(f"100%  {self.completed_packages}/{self.total_packages} packages")
            elif self.total_packages > 0:
                pct = int(self.progress * 100)
                text.update(f"{pct}%  {self.completed_packages}/{self.total_packages} packages")
            else:
                text.update("Checking...")
        except Exception:
            pass

    def _update_status_display(self) -> None:
        """Update the status line."""
        try:
            status = self.query_one("#status-current", Static)
            speed_label = self.query_one("#status-speed", Static)
            eta_label = self.query_one("#status-eta", Static)

            if self.phase == UpdatePhase.IDLE:
                status.update("Waiting...")
                speed_label.update("")
                eta_label.update("")
            elif self.phase == UpdatePhase.CHECKING:
                status.update("Checking for updates...")
                speed_label.update("")
                eta_label.update("")
            elif self.phase == UpdatePhase.DOWNLOADING:
                if self.current_package:
                    status.update(f"Downloading: {self.current_package}")
                else:
                    status.update("Downloading...")
                if self.speed:
                    speed_label.update(f"  ↓ {self.speed}")
                if self.eta:
                    eta_label.update(f"  ETA: {self.eta}")
            elif self.phase == UpdatePhase.INSTALLING:
                if self.current_package:
                    status.update(f"Installing: {self.current_package}")
                else:
                    status.update("Installing...")
                speed_label.update("")
                eta_label.update("")
            elif self.phase == UpdatePhase.COMPLETE:
                if self.completed_packages > 0:
                    status.update(f"Complete! Updated {self.completed_packages} packages")
                else:
                    status.update("Already up to date")
                speed_label.update("")
                eta_label.update("")
            elif self.phase == UpdatePhase.ERROR:
                status.update(f"Error: {self._error_message or 'Update failed'}")
                speed_label.update("")
                eta_label.update("")
        except Exception:
            pass

    def add_package(self, package: Package, is_current: bool = False) -> None:
        """Add a package to the recent list."""
        self._packages.append(package)
        self._refresh_package_list(is_current_name=package.name if is_current else None)

    def set_packages(self, packages: list[Package]) -> None:
        """Set the complete package list."""
        self._packages = packages
        self._refresh_package_list()

    def _refresh_package_list(self, is_current_name: str | None = None) -> None:
        """Refresh the package list display."""
        try:
            container = self.query_one("#package-list", Vertical)
            container.remove_children()

            # Show last 5 packages
            recent = self._packages[-5:]
            for pkg in reversed(recent):
                is_current = pkg.name == is_current_name
                container.mount(PackageItem(
                    pkg,
                    is_current=is_current,
                    show_versions=self._show_versions
                ))
        except Exception:
            pass

    def set_error(self, message: str) -> None:
        """Set error state with message."""
        self._error_message = message
        self.phase = UpdatePhase.ERROR

    def reset(self) -> None:
        """Reset the panel to initial state."""
        self.phase = UpdatePhase.IDLE
        self.progress = 0.0
        self.total_packages = 0
        self.completed_packages = 0
        self.current_package = ""
        self.speed = ""
        self.eta = ""
        self._packages = []
        self._error_message = ""
        self._refresh_package_list()

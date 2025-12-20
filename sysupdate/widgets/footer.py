"""Footer widget with keyboard shortcuts."""

from textual.app import ComposeResult
from textual.widgets import Static


class FooterKey(Static):
    """A single keyboard shortcut display in the footer."""

    def __init__(self, key: str, description: str) -> None:
        super().__init__()
        self._key = key
        self._description = description


class Footer(Static):
    """Application footer with keyboard shortcuts."""

    DEFAULT_CSS = """
    Footer {
        dock: bottom;
        height: 1;
        background: #24283b;
        border-top: solid #414868;
        content-align: center middle;
        color: #c0caf5;
    }
    """

    def __init__(self, shortcuts: list[tuple[str, str]] | None = None) -> None:
        super().__init__()
        self._shortcuts = shortcuts or [
            ("Q", "Quit"),
            ("L", "Logs"),
            ("D", "Details"),
            ("?", "Help"),
        ]
        self._update_text()

    def compose(self) -> ComposeResult:
        """Create the footer content."""
        return []

    def on_mount(self) -> None:
        """Update display when mounted."""
        self._update_text()

    def set_shortcuts(self, shortcuts: list[tuple[str, str]]) -> None:
        """Update the displayed shortcuts."""
        self._shortcuts = shortcuts
        self._update_text()

    def _update_text(self) -> None:
        """Update the footer text with current shortcuts."""
        parts = []
        for key, desc in self._shortcuts:
            parts.append(f"[#414868 on #7dcfff] {key} [/] {desc}")
        self.update(" " * 2 + "  ".join(parts))

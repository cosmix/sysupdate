"""Header widget with title."""

from textual.app import ComposeResult
from textual.widgets import Static


class Header(Static):
    """Application header with title."""

    DEFAULT_CSS = """
    Header {
        dock: top;
        height: 1;
        background: #24283b;
        border-bottom: solid #414868;
        padding: 0 2;
        content-align: center middle;
    }

    Header .title {
        text-align: center;
        color: #7dcfff;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the header content."""
        return []

    def on_mount(self) -> None:
        """Update display when mounted."""
        self.update(
            "[bold #7dcfff]SYSUPDATE[/] [#565f89]System Update Manager[/] [#9ece6a]v2.0[/]"
        )

"""Rich UI components for System Update Manager."""

import re

from rich.console import Console
from rich.progress import (
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    Task as RichTask,
)
from rich.table import Table
from rich.text import Text

from .updaters.base import Package

# ============================================================================
# Module-level constants
# ============================================================================

# Fixed width for description column (prefix + label + detail text)
DESC_WIDTH = 30

# Progress thresholds - fraction of progress bar reserved for checking phase
CHECKING_PROGRESS_END = 0.1

# Gradient colors for ASCII art header (cyan -> blue -> magenta)
HEADER_COLORS = ["cyan", "dodger_blue2", "blue", "purple", "magenta"]

# Logo width for centering version text under ASCII art header
LOGO_WIDTH = 50

# Progress bar width in characters
BAR_WIDTH = 16

# Precompiled pattern for stripping Rich markup tags
_MARKUP_PATTERN = re.compile(r"\[(green|red|dim|/)\]")


class StatusColumn(SpinnerColumn):
    """Status badge with phase-aware colors and ASCII fallback support."""

    # Unicode phase symbols for terminals with full Unicode support
    PHASE_STYLES: dict[str, tuple[str, str]] = {
        "checking": ("dim", "\u25cb"),
        "downloading": ("cyan", "\u2193"),
        "installing": ("yellow", "\u2699"),
        "complete": ("green", "\u2713"),
        "error": ("red", "\u2717"),
    }

    # ASCII fallback symbols for terminals without Unicode support
    ASCII_PHASE_STYLES: dict[str, tuple[str, str]] = {
        "checking": ("dim", "o"),
        "downloading": ("cyan", "v"),
        "installing": ("yellow", "*"),
        "complete": ("green", "+"),
        "error": ("red", "x"),
    }

    def __init__(self, *args, use_ascii: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_ascii = use_ascii

    def render(self, task: RichTask) -> Text:
        styles = self.ASCII_PHASE_STYLES if self.use_ascii else self.PHASE_STYLES

        if task.finished:
            if task.fields.get("success", True):
                symbol = "+" if self.use_ascii else "\u2713"
                return Text(symbol, style="green")
            symbol = "x" if self.use_ascii else "\u2717"
            return Text(symbol, style="red")

        phase = task.fields.get("phase", "checking")
        default_symbol = "." if self.use_ascii else "\u25cf"
        style, symbol = styles.get(phase, ("white", default_symbol))
        return Text(symbol, style=style)


class PhaseAwareProgressColumn(TaskProgressColumn):
    """Task progress column that shows dim placeholder during indeterminate phase."""

    def render(self, task: RichTask) -> Text:
        # When total is None (indeterminate), show placeholder to maintain width
        if task.total is None:
            # Match width of "100%" (4 chars)
            return Text("  - ", style="dim")
        return super().render(task)


class SpeedColumn(ProgressColumn):
    """Shows download speed when available."""

    def render(self, task: RichTask) -> Text:
        speed = task.fields.get("speed", "")
        if speed:
            return Text(f"{speed:>10}", style="cyan")
        return Text(" " * 10, style="dim")


class ETAColumn(ProgressColumn):
    """Shows ETA when available with fixed width."""

    # Fixed width for ETA column (e.g., "ETA 10m30s" = 10 chars)
    ETA_WIDTH = 10

    def render(self, task: RichTask) -> Text:
        eta = task.fields.get("eta", "")
        if eta:
            text = f"ETA {eta}"
            # Pad or truncate to fixed width
            if len(text) < self.ETA_WIDTH:
                text = text + " " * (self.ETA_WIDTH - len(text))
            elif len(text) > self.ETA_WIDTH:
                text = text[: self.ETA_WIDTH]
            return Text(text, style="dim")
        return Text(" " * self.ETA_WIDTH, style="dim")


def print_header(
    console: Console,
    version: str,
    dry_run: bool,
    use_ascii: bool,
) -> None:
    """Print gradient-colored ASCII art header.

    Args:
        console: Rich Console instance for output.
        version: Application version string.
        dry_run: Whether dry-run mode is active.
        use_ascii: Whether to use ASCII fallback characters.
    """
    # Use regular strings with escaped backslashes to avoid raw string issues
    lines = [
        "                                 _       _       ",
        "   ___ _   _ ___ _   _ _ __   __| | __ _| |_ ___ ",
        "  / __| | | / __| | | | '_ \\ / _` |/ _` | __/ _ \\",
        "  \\__ \\ |_| \\__ \\ |_| | |_) | (_| | (_| | ||  __/",
        "  |___/\\__, |___/\\__,_| .__/ \\__,_|\\__,_|\\__\\___|",
        "       |___/          |_|                        ",
    ]

    console.print()
    for line in lines:
        text = Text()
        line_len = len(line)
        for i, char in enumerate(line):
            color_idx = int(i / line_len * len(HEADER_COLORS))
            text.append(
                char,
                style=f"bold {HEADER_COLORS[min(color_idx, len(HEADER_COLORS) - 1)]}",
            )
        console.print(text)

    # Version centered under the logo
    version_str = f"v{version}"
    padding = (LOGO_WIDTH - len(version_str)) // 2
    version_text = Text()
    version_text.append(" " * padding + version_str, style="dim")
    console.print(version_text)

    # Show dry-run indicator if in dry-run mode
    if dry_run:
        console.print()
        console.print("   [dim][DRY RUN] No changes will be made[/]")

    console.print()


def print_summary(
    console: Console,
    results_by_label: dict[str, list[Package]],
    use_ascii: bool,
) -> None:
    """Print minimal summary of updated packages.

    Args:
        console: Rich Console instance for output.
        results_by_label: Dict mapping updater label to list of updated packages.
        use_ascii: Whether to use ASCII fallback characters.
    """
    # Table display configuration per label
    table_config = {
        "APT": {
            "title": "APT Packages",
            "name_col": "Package",
            "show_versions": True,
        },
        "Flatpak": {
            "title": "Flatpak Apps",
            "name_col": "App",
            "show_versions": False,
        },
        "Snap": {"title": "Snap Apps", "name_col": "App", "show_versions": True},
        "DNF": {
            "title": "DNF Packages",
            "name_col": "Package",
            "show_versions": True,
        },
        "Pacman": {
            "title": "Pacman Packages",
            "name_col": "Package",
            "show_versions": True,
        },
    }

    # ASCII fallback symbols
    line_char = "-" if use_ascii else "\u2500"
    check_char = "+" if use_ascii else "\u2713"

    total = sum(len(pkgs) for pkgs in results_by_label.values())
    console.print("   [dim]" + line_char * 40 + "[/]")

    if total == 0:
        console.print()
        console.print(f"   [green]{check_char}[/] System is up to date")
        console.print()
        return

    # Count summary
    parts = [
        f"{len(pkgs)} {label}" for label, pkgs in results_by_label.items() if pkgs
    ]
    console.print()
    console.print(
        f"   [green]{check_char}[/] Updated [bold]{total}[/] packages ({', '.join(parts)})"
    )
    console.print()

    # Print tables for each manager with updates
    for label, packages in results_by_label.items():
        if not packages:
            continue

        cfg = table_config.get(
            label, {"title": label, "name_col": "Package", "show_versions": True}
        )
        console.print(f"   [bold]{cfg['title']}[/] [dim]({len(packages)})[/]")
        console.print()
        print_package_table(console, packages, cfg["name_col"], cfg["show_versions"], use_ascii)
        console.print()

    console.print("   [dim]" + line_char * 40 + "[/]")
    console.print()


def print_package_table(
    console: Console,
    packages: list[Package],
    name_col: str,
    show_versions: bool,
    use_ascii: bool,
) -> None:
    """Print a table of packages.

    Args:
        console: Rich Console instance for output.
        packages: List of Package objects to display.
        name_col: Column header for package name.
        show_versions: Whether to show old/new version columns.
        use_ascii: Whether to use ASCII fallback characters.
    """
    # ASCII fallback for arrow symbol
    arrow = "->" if use_ascii else "\u2192"

    table = Table(
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 3),
        collapse_padding=True,
    )
    table.add_column(name_col, style="white")

    if show_versions:
        table.add_column("Old", style="dim", justify="right")
        table.add_column("", style="dim", justify="center", width=3)
        table.add_column("New", style="white", justify="left")
        for pkg in packages:
            old_ver = pkg.old_version or "-"
            new_ver = pkg.new_version or "-"
            table.add_row(pkg.name, old_ver, arrow, new_ver)
    else:
        table.add_column("Branch", style="dim", justify="right")
        for pkg in packages:
            branch = pkg.new_version or pkg.old_version or "stable"
            table.add_row(pkg.name, branch)

    console.print(table)

"""Update summary rendering for System Update Manager."""

import re

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from .banner import (
    DEFAULT_ACCENT,
    ERROR_STYLE,
    SUCCESS_STYLE,
    gradient_rule,
    hex_to_rgb,
    sheen_sweep_line,
)
from .updaters.base import Package

# Accent color per package manager, sampled along the banner gradient
MANAGER_ACCENTS = {
    "APT": "#22d3ee",
    "Flatpak": "#3b82f6",
    "Snap": "#8b5cf6",
    "DNF": "#d946ef",
    "Pacman": "#f472b6",
}

# Width of summary section rules and of the per-manager count bars
RULE_WIDTH = 40
COUNT_BAR_WIDTH = 20

# Maximum length of an inline failure message before truncation
FAILURE_MSG_WIDTH = 60

# Neutral text tones used in the swept count line
_TEXT_RGB = (226, 232, 240)
_MUTED_RGB = (148, 163, 184)

# Separators between version components, kept when tokenizing for diffs
_VERSION_SEP = re.compile(r"([.\-+~:_])")

# Table display configuration per manager label
TABLE_CONFIG = {
    "APT": {"title": "APT Packages", "name_col": "Package", "show_versions": True},
    "Flatpak": {"title": "Flatpak Apps", "name_col": "App", "show_versions": False},
    "Snap": {"title": "Snap Apps", "name_col": "App", "show_versions": True},
    "DNF": {"title": "DNF Packages", "name_col": "Package", "show_versions": True},
    "Pacman": {
        "title": "Pacman Packages",
        "name_col": "Package",
        "show_versions": True,
    },
}


def format_elapsed(seconds: float) -> str:
    """Format an elapsed duration as '42s' or '2m 05s'."""
    seconds = max(seconds, 0.0)
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s"


def version_diff_text(old: str | None, new: str | None) -> Text:
    """Render a new version with only the changed part highlighted.

    The unchanged leading components are dimmed so the eye lands on what
    actually changed: 3.0.11 -> 3.0.13 renders '3.0.' dim and '13' bold.
    """
    if not new:
        return Text("-", style="dim")
    if not old or old == new:
        return Text(new)
    old_parts = _VERSION_SEP.split(old)
    new_parts = _VERSION_SEP.split(new)
    common = 0
    for a, b in zip(old_parts, new_parts):
        if a != b:
            break
        common += 1
    changed = "".join(new_parts[common:])
    if not changed:
        return Text(new)
    text = Text()
    prefix = "".join(new_parts[:common])
    if prefix:
        text.append(prefix, style="dim")
    text.append(changed, style="bold white")
    return text


def _print_count_line(
    console: Console,
    active: list[tuple[str, int]],
    total: int,
    use_ascii: bool,
    animate: bool,
) -> None:
    """Print the 'Updated N packages' line with a celebratory sheen sweep."""
    check = "+" if use_ascii else "✓"
    joiner = ", " if use_ascii else " · "
    segments = [
        (check, hex_to_rgb(SUCCESS_STYLE), "bold"),
        (" Updated ", _TEXT_RGB, ""),
        (str(total), (255, 255, 255), "bold"),
        (" packages (", _TEXT_RGB, ""),
    ]
    for i, (label, count) in enumerate(active):
        if i:
            segments.append((joiner, _MUTED_RGB, ""))
        accent = hex_to_rgb(MANAGER_ACCENTS.get(label, DEFAULT_ACCENT))
        segments.append((f"{count} {label}", accent, ""))
    segments.append((")", _TEXT_RGB, ""))
    sheen_sweep_line(console, segments, indent=3, animate=animate)


def _print_count_bars(
    console: Console, active: list[tuple[str, int]], use_ascii: bool
) -> None:
    """Print compact accent-colored count bars, one per manager."""
    if len(active) < 2:
        return
    bar_char = "=" if use_ascii else "━"
    label_width = max(len(label) for label, _ in active)
    peak = max(count for _, count in active)
    for label, count in active:
        accent = MANAGER_ACCENTS.get(label, DEFAULT_ACCENT)
        cells = max(1, round(count / peak * COUNT_BAR_WIDTH))
        console.print(
            f"   {label:<{label_width}}  [{accent}]{bar_char * cells}[/]"
            f" [dim]{count}[/]"
        )
    console.print()


def _print_failures(
    console: Console,
    failures: list[tuple[str, str]],
    log_dir: str | None,
    use_ascii: bool,
) -> None:
    """Print failed updaters with a pointer to the log directory."""
    cross = "x" if use_ascii else "✗"
    sep = "|" if use_ascii else "·"
    for label, message in failures:
        msg = (message or "").strip()
        if len(msg) > FAILURE_MSG_WIDTH:
            ellipsis = "..." if use_ascii else "…"
            msg = msg[: FAILURE_MSG_WIDTH - 1] + ellipsis
        line = f"   [bold {ERROR_STYLE}]{cross} {label} failed[/]"
        if msg:
            line += f" [dim]{sep} {escape(msg)}[/]"
        console.print(line)
    if log_dir:
        console.print(f"   [dim]Logs {sep} {escape(log_dir)}[/]")
    console.print()


def print_summary(
    console: Console,
    results_by_label: dict[str, list[Package]],
    use_ascii: bool,
    elapsed: float | None = None,
    failures: list[tuple[str, str]] | None = None,
    log_dir: str | None = None,
    animate: bool = True,
) -> None:
    """Print the end-of-run summary of updated packages.

    Args:
        console: Rich Console instance for output.
        results_by_label: Dict mapping updater label to updated packages.
        use_ascii: Whether to use ASCII fallback characters.
        elapsed: Total run duration in seconds, for the timing tagline.
        failures: (label, error message) pairs for failed updaters.
        log_dir: Log directory path shown when there are failures.
        animate: Whether the count-line sheen sweep may animate.
    """
    failures = failures or []
    check = "+" if use_ascii else "✓"
    dash = "--" if use_ascii else "—"

    total = sum(len(pkgs) for pkgs in results_by_label.values())
    active = [(label, len(pkgs)) for label, pkgs in results_by_label.items() if pkgs]

    console.print(gradient_rule(RULE_WIDTH, use_ascii))
    console.print()

    if total == 0 and not failures:
        console.print(
            f"   [bold {SUCCESS_STYLE}]{check}[/] System is up to date"
            f" [dim]{dash} nothing to do[/]"
        )
        # Indented to align with the text column above (past the glyph)
        _print_footer(console, elapsed, "Checked in", indent=5)
        return

    if total:
        _print_count_line(console, active, total, use_ascii, animate)
        console.print()
        _print_count_bars(console, active, use_ascii)
        for label, packages in results_by_label.items():
            if not packages:
                continue
            cfg = TABLE_CONFIG.get(
                label, {"title": label, "name_col": "Package", "show_versions": True}
            )
            accent = MANAGER_ACCENTS.get(label, DEFAULT_ACCENT)
            chip = "*" if use_ascii else "▪"
            console.print(
                f"   [{accent}]{chip}[/] [bold]{cfg['title']}[/]"
                f" [dim]({len(packages)})[/]"
            )
            console.print()
            print_package_table(
                console,
                packages,
                cfg["name_col"],
                cfg["show_versions"],
                use_ascii,
                accent,
            )
            console.print()

    if failures:
        _print_failures(console, failures, log_dir, use_ascii)

    console.print(gradient_rule(RULE_WIDTH, use_ascii))
    _print_footer(console, elapsed, "Done in")


def _print_footer(
    console: Console, elapsed: float | None, verb: str, indent: int = 3
) -> None:
    """Print the optional timing tagline and closing blank line."""
    if elapsed is not None:
        console.print(" " * indent + f"[dim]{verb} {format_elapsed(elapsed)}[/]")
    console.print()


def print_package_table(
    console: Console,
    packages: list[Package],
    name_col: str,
    show_versions: bool,
    use_ascii: bool,
    accent: str = DEFAULT_ACCENT,
) -> None:
    """Print a table of packages.

    Args:
        console: Rich Console instance for output.
        packages: List of Package objects to display.
        name_col: Column header for package name.
        show_versions: Whether to show old/new version columns.
        use_ascii: Whether to use ASCII fallback characters.
        accent: Accent color for the version-change arrow.
    """
    # ASCII fallback for arrow symbol
    arrow = "->" if use_ascii else "→"

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
        table.add_column("", style=accent, justify="center", width=3)
        table.add_column("New", style="white", justify="left")
        for pkg in packages:
            old_ver = pkg.old_version or "-"
            table.add_row(
                pkg.name,
                old_ver,
                arrow,
                version_diff_text(pkg.old_version, pkg.new_version),
            )
    else:
        table.add_column("Branch", style="dim", justify="right")
        for pkg in packages:
            branch = pkg.new_version or pkg.old_version or "stable"
            table.add_row(pkg.name, branch)

    console.print(table)

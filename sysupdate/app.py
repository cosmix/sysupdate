"""Minimal CLI interface for System Update Manager using Rich."""

import asyncio
import re
from dataclasses import dataclass
from typing import Callable
from rich.console import Console
from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    Task as RichTask,
)
from rich.table import Table
from rich.text import Text

from . import __version__
from .updaters.base import UpdatePhase, UpdateProgress, Package, UpdaterProtocol
from .updaters.apt import AptUpdater
from .updaters.flatpak import FlatpakUpdater
from .updaters.snap import SnapUpdater
from .updaters.dnf import DnfUpdater
from .updaters.pacman import PacmanUpdater
from .updaters.aria2_downloader import Aria2Downloader
from .utils.logging import setup_logging
from .utils.aria2 import prompt_install_aria2

# Precompiled pattern for stripping Rich markup tags
_MARKUP_PATTERN = re.compile(r"\[(green|red|dim|/)\]")


@dataclass
class UpdaterConfig:
    """Configuration for an updater in the CLI."""
    updater: UpdaterProtocol
    label: str
    max_pkg_len: int = 12


class StatusColumn(SpinnerColumn):
    """Status badge with phase-aware colors."""

    PHASE_STYLES: dict[str, tuple[str, str]] = {
        "checking": ("dim", "○"),
        "downloading": ("cyan", "↓"),
        "installing": ("yellow", "⚙"),
        "complete": ("green", "✓"),
        "error": ("red", "✗"),
    }

    def render(self, task: RichTask) -> Text:
        if task.finished:
            if task.fields.get("success", True):
                return Text("✓", style="green")
            return Text("✗", style="red")

        phase = task.fields.get("phase", "checking")
        style, symbol = self.PHASE_STYLES.get(phase, ("white", "●"))
        return Text(symbol, style=style)


class SpeedColumn(ProgressColumn):
    """Shows download speed when available."""

    def render(self, task: RichTask) -> Text:
        speed = task.fields.get("speed", "")
        if speed:
            return Text(f"{speed:>10}", style="cyan")
        return Text(" " * 10, style="dim")


class ETAColumn(ProgressColumn):
    """Shows ETA when available."""

    def render(self, task: RichTask) -> Text:
        eta = task.fields.get("eta", "")
        if eta:
            return Text(f"ETA {eta}", style="dim")
        return Text("", style="dim")


class SysUpdateCLI:
    """Minimal CLI for system updates with Rich progress display."""

    # Fixed width for the entire description (prefix + label + detail)
    DESC_WIDTH = 24

    def __init__(self, verbose: bool = False, dry_run: bool = False) -> None:
        self.verbose = verbose
        self.dry_run = dry_run
        self.console = Console()
        self._logger = setup_logging(verbose)
        self._updaters = [
            UpdaterConfig(AptUpdater(), "APT", max_pkg_len=12),
            UpdaterConfig(FlatpakUpdater(), "Flatpak", max_pkg_len=10),
            UpdaterConfig(SnapUpdater(), "Snap", max_pkg_len=12),
            UpdaterConfig(DnfUpdater(), "DNF", max_pkg_len=12),
            UpdaterConfig(PacmanUpdater(), "Pacman", max_pkg_len=12),
        ]

    def run(self) -> int:
        """Run the update process."""
        self._print_header()

        try:
            return asyncio.run(self._run_updates())
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted[/]")
            return 130

    def _print_header(self) -> None:
        """Print gradient-colored ASCII art header."""
        # Use regular strings with escaped backslashes to avoid raw string issues
        lines = [
            "                                 _       _       ",
            "   ___ _   _ ___ _   _ _ __   __| | __ _| |_ ___ ",
            "  / __| | | / __| | | | '_ \\ / _` |/ _` | __/ _ \\",
            "  \\__ \\ |_| \\__ \\ |_| | |_) | (_| | (_| | ||  __/",
            "  |___/\\__, |___/\\__,_| .__/ \\__,_|\\__,_|\\__\\___|",
            "       |___/          |_|                        ",
        ]

        # Gradient from cyan -> blue -> magenta
        colors = ["cyan", "dodger_blue2", "blue", "purple", "magenta"]

        self.console.print()
        for line in lines:
            text = Text()
            line_len = len(line)
            for i, char in enumerate(line):
                color_idx = int(i / line_len * len(colors))
                text.append(char, style=f"bold {colors[min(color_idx, len(colors) - 1)]}")
            self.console.print(text)

        # Version centered under the logo (logo is 50 chars wide)
        version_str = f"v{__version__}"
        logo_width = 50
        padding = (logo_width - len(version_str)) // 2
        version_text = Text()
        version_text.append(" " * padding + version_str, style="dim")
        self.console.print(version_text)
        self.console.print()

    def _format_desc(self, prefix: str, label: str, detail: str = "") -> str:
        """Format description with fixed width (truncate or pad as needed).

        Args:
            prefix: Status indicator (e.g., "  " for spinner, "✓ " for complete)
            label: Main label (APT or Flatpak)
            detail: Optional detail text
        """
        if detail:
            text = f"{prefix}{label} {detail}"
        else:
            text = f"{prefix}{label}"

        # Calculate visible length (strip Rich markup)
        visible = _MARKUP_PATTERN.sub("", text)
        visible_len = len(visible)

        if visible_len < self.DESC_WIDTH:
            # Pad to fixed width
            return text + " " * (self.DESC_WIDTH - visible_len)
        elif visible_len > self.DESC_WIDTH:
            # Truncate: find how much to trim from the end
            excess = visible_len - self.DESC_WIDTH
            # Remove markup, truncate, but keep the structure
            if detail:
                # Truncate detail portion
                detail_visible = _MARKUP_PATTERN.sub("", detail)
                if len(detail_visible) > excess:
                    new_detail = detail_visible[:-excess-1] + "…"
                    return f"{prefix}{label} [dim]{new_detail}[/]"
            return text[:self.DESC_WIDTH]
        return text

    def _create_progress_callback(
        self,
        progress: Progress,
        task_id,
        label: str,
        max_pkg_len: int = 12,
    ) -> Callable[[UpdateProgress], None]:
        """Create a progress callback for an updater.

        Args:
            progress: Rich Progress instance to update
            task_id: Task ID returned by progress.add_task()
            label: Label for the updater (e.g., "APT", "Flatpak")
            max_pkg_len: Maximum length for package name display
        """
        def on_progress(update: UpdateProgress) -> None:
            pct = int(update.progress * 100)
            phase_value = update.phase.value if update.phase else "checking"

            if update.phase == UpdatePhase.CHECKING:
                # Show message if available (e.g., "Querying snap store...")
                if update.message:
                    # Extract short status from message
                    msg = update.message.rstrip(".")
                    if len(msg) > 15:
                        msg = msg[:14] + "…"
                    desc = self._format_desc("", label, f"[dim]{msg}[/]")
                else:
                    desc = self._format_desc("", label, "[dim]checking...[/]")
            elif update.phase in (UpdatePhase.DOWNLOADING, UpdatePhase.INSTALLING):
                phase_text = "downloading" if update.phase == UpdatePhase.DOWNLOADING else "installing"
                if update.current_package:
                    pkg = update.current_package[:max_pkg_len]
                    desc = self._format_desc("", f"{label} [dim]|[/] {pkg}")
                else:
                    desc = self._format_desc("", label, f"[dim]{phase_text}...[/]")
            else:
                desc = self._format_desc("", label)

            progress.update(
                task_id,
                completed=pct,
                description=desc,
                phase=phase_value,
                speed=update.speed,
                eta=update.eta,
            )
        return on_progress

    async def _run_updates(self) -> int:
        """Run all available package manager updates concurrently."""
        # Check for aria2c availability (for parallel APT downloads)
        downloader = Aria2Downloader()
        aria2_available = await downloader.check_available()
        if not aria2_available:
            await prompt_install_aria2(self.console)

        # Check which updaters are available
        availability = await asyncio.gather(
            *[cfg.updater.check_available() for cfg in self._updaters]
        )
        available_updaters = [
            (cfg, avail) for cfg, avail in zip(self._updaters, availability)
        ]

        # Collect results by label
        results_by_label: dict[str, list[Package]] = {cfg.label: [] for cfg in self._updaters}

        with Progress(
            TextColumn("  "),
            StatusColumn(spinner_name="dots", style="white"),
            TextColumn("{task.description}"),
            BarColumn(bar_width=16, style="dim", complete_style="white", finished_style="green"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            SpeedColumn(),
            ETAColumn(),
            console=self.console,
            transient=False,
            expand=False,
        ) as progress:
            coroutines = []
            labels = []

            for cfg, is_available in available_updaters:
                if is_available:
                    task_id = progress.add_task(self._format_desc("", cfg.label), total=100)
                    coroutines.append(self._run_updater(progress, task_id, cfg))
                    labels.append(cfg.label)
                else:
                    self.console.print(f"[dim]   {cfg.label} not available[/]")

            if coroutines:
                self.console.print()
                results = await asyncio.gather(*coroutines, return_exceptions=True)

                for label, result in zip(labels, results):
                    if isinstance(result, Exception):
                        self._logger.error(f"{label} update failed: {result}")
                    else:
                        results_by_label[label] = result

        self.console.print()
        self.console.print()
        self._print_summary(results_by_label)
        return 0

    async def _run_updater(
        self,
        progress: Progress,
        task_id,
        cfg: UpdaterConfig,
    ) -> list[Package]:
        """Run an updater with progress tracking."""
        on_progress = self._create_progress_callback(
            progress, task_id, label=cfg.label, max_pkg_len=cfg.max_pkg_len
        )

        result = await cfg.updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        progress.update(
            task_id,
            completed=100,
            success=result.success,
            description=self._format_desc("", cfg.label)
        )
        return result.packages

    def _print_summary(self, results_by_label: dict[str, list[Package]]) -> None:
        """Print minimal summary of updated packages."""
        # Table display configuration per label
        table_config = {
            "APT": {"title": "APT Packages", "name_col": "Package", "show_versions": True},
            "Flatpak": {"title": "Flatpak Apps", "name_col": "App", "show_versions": False},
            "Snap": {"title": "Snap Apps", "name_col": "App", "show_versions": True},
            "DNF": {"title": "DNF Packages", "name_col": "Package", "show_versions": True},
            "Pacman": {"title": "Pacman Packages", "name_col": "Package", "show_versions": True},
        }

        total = sum(len(pkgs) for pkgs in results_by_label.values())
        self.console.print("   [dim]" + "\u2500" * 40 + "[/]")

        if total == 0:
            self.console.print()
            self.console.print("   [green]\u2713[/] System is up to date")
            self.console.print()
            return

        # Count summary
        parts = [f"{len(pkgs)} {label}" for label, pkgs in results_by_label.items() if pkgs]
        self.console.print()
        self.console.print(f"   [green]\u2713[/] Updated [bold]{total}[/] packages ({', '.join(parts)})")
        self.console.print()

        # Print tables for each manager with updates
        for label, packages in results_by_label.items():
            if not packages:
                continue

            cfg = table_config.get(label, {"title": label, "name_col": "Package", "show_versions": True})
            self.console.print(f"   [bold]{cfg['title']}[/] [dim]({len(packages)})[/]")
            self.console.print()
            self._print_package_table(packages, cfg["name_col"], cfg["show_versions"])
            self.console.print()

        self.console.print("   [dim]" + "\u2500" * 40 + "[/]")
        self.console.print()

    def _print_package_table(
        self,
        packages: list[Package],
        name_col: str,
        show_versions: bool,
    ) -> None:
        """Print a table of packages."""
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
                table.add_row(pkg.name, old_ver, "\u2192", new_ver)
        else:
            table.add_column("Branch", style="dim", justify="right")
            for pkg in packages:
                branch = pkg.new_version or pkg.old_version or "stable"
                table.add_row(pkg.name, branch)

        self.console.print(table)

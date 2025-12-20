"""Minimal CLI interface for System Update Manager using Rich."""

import asyncio
from typing import cast
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from . import __version__
from .updaters.base import UpdatePhase, UpdateProgress, Package
from .updaters.apt import AptUpdater
from .updaters.flatpak import FlatpakUpdater
from .updaters.aria2_downloader import Aria2Downloader
from .utils.logging import setup_logging


class StatusColumn(SpinnerColumn):
    """Spinner that shows ✓ or ✗ when task completes."""

    def render(self, task):
        if task.finished:
            if task.fields.get("success", True):
                return Text("✓", style="green")
            return Text("✗", style="red")
        return super().render(task)


class SysUpdateCLI:
    """Minimal CLI for system updates with Rich progress display."""

    # Fixed width for the entire description (prefix + label + detail)
    DESC_WIDTH = 24

    def __init__(self, verbose: bool = False, dry_run: bool = False) -> None:
        self.verbose = verbose
        self.dry_run = dry_run
        self.console = Console()
        self._logger = setup_logging(verbose)
        self._apt_updater = AptUpdater()
        self._flatpak_updater = FlatpakUpdater()

    def run(self) -> int:
        """Run the update process."""
        self._print_header()

        try:
            return asyncio.run(self._run_updates())
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted[/]")
            return 130

    def _print_header(self) -> None:
        """Print ASCII art header."""
        logo = r"""
[bold]                                 _       _       
   ___ _   _ ___ _   _ _ __   __| | __ _| |_ ___
  / __| | | / __| | | | '_ \ / _` |/ _` | __/ _ \
  \__ \ |_| \__ \ |_| | |_) | (_| | (_| | ||  __/
  |___/\__, |___/\__,_| .__/ \__,_|\__,_|\__\___|
       |___/          |_|[/]  [dim]v{version}[/]
"""
        self.console.print(logo.format(version=__version__))

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
        visible = text.replace("[green]", "").replace("[red]", "").replace("[dim]", "").replace("[/]", "")
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
                detail_visible = detail.replace("[dim]", "").replace("[/]", "")
                if len(detail_visible) > excess:
                    new_detail = detail_visible[:-excess-1] + "…"
                    return f"{prefix}{label} [dim]{new_detail}[/]"
            return text[:self.DESC_WIDTH]
        return text

    async def _run_updates(self) -> int:
        """Run APT and Flatpak updates concurrently."""
        apt_available = await self._apt_updater.check_available()
        flatpak_available = await self._flatpak_updater.check_available()

        # Check for aria2c availability
        downloader = Aria2Downloader()
        aria2_available = await downloader.check_available()
        if not aria2_available:
            self.console.print("[yellow]\u26a0[/] aria2c not installed - using sequential downloads")
            self.console.print("[dim]  Install: sudo apt install aria2[/]")
            self.console.print()

        apt_packages: list[Package] = []
        flatpak_packages: list[Package] = []

        # Run updates with progress display
        with Progress(
            TextColumn("  "),  # 2-char indent
            StatusColumn(spinner_name="dots", style="white"),
            TextColumn("{task.description}"),
            BarColumn(bar_width=16, style="dim", complete_style="white", finished_style="green"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
            expand=False,
        ) as progress:
            coroutines = []
            task_mapping = []

            if apt_available:
                apt_task_id = progress.add_task(
                    self._format_desc("", "APT"),
                    total=100
                )
                coroutines.append(self._run_apt(progress, apt_task_id))
                task_mapping.append("apt")
            else:
                self.console.print("[dim]   APT not available[/]")

            if flatpak_available:
                flatpak_task_id = progress.add_task(
                    self._format_desc("", "Flatpak"),
                    total=100
                )
                coroutines.append(self._run_flatpak(progress, flatpak_task_id))
                task_mapping.append("flatpak")
            else:
                self.console.print("[dim]   Flatpak not available[/]")

            # Run all updates concurrently
            if coroutines:
                results = await asyncio.gather(*coroutines, return_exceptions=True)

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        self._logger.error(f"Update failed: {result}")
                        continue
                    if task_mapping[i] == "apt":
                        apt_packages = cast(list[Package], result)
                    else:
                        flatpak_packages = cast(list[Package], result)

        self.console.print()

        # Print summary
        self._print_summary(apt_packages, flatpak_packages)

        return 0

    async def _run_apt(self, progress: Progress, task_id) -> list[Package]:
        """Run APT update with progress."""

        def on_progress(update: UpdateProgress) -> None:
            pct = int(update.progress * 100)

            if update.phase == UpdatePhase.CHECKING:
                desc = self._format_desc("", "APT", "[dim]checking...[/]")
            elif update.phase == UpdatePhase.DOWNLOADING:
                if update.current_package:
                    pkg = update.current_package[:12]
                    desc = self._format_desc("", f"APT [dim]|[/] {pkg}")
                else:
                    desc = self._format_desc("", "APT", "[dim]downloading...[/]")
            elif update.phase == UpdatePhase.INSTALLING:
                if update.current_package:
                    pkg = update.current_package[:12]
                    desc = self._format_desc("", f"APT [dim]|[/] {pkg}")
                else:
                    desc = self._format_desc("", "APT", "[dim]installing...[/]")
            elif update.phase == UpdatePhase.COMPLETE:
                desc = self._format_desc("", "APT")
            elif update.phase == UpdatePhase.ERROR:
                desc = self._format_desc("", "APT")
            else:
                desc = self._format_desc("", "APT")

            progress.update(task_id, completed=pct, description=desc)

        result = await self._apt_updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        if result.success:
            progress.update(
                task_id,
                completed=100,
                success=True,
                description=self._format_desc("", "APT")
            )
        else:
            progress.update(
                task_id,
                completed=100,
                success=False,
                description=self._format_desc("", "APT")
            )

        return result.packages

    async def _run_flatpak(self, progress: Progress, task_id) -> list[Package]:
        """Run Flatpak update with progress."""

        def on_progress(update: UpdateProgress) -> None:
            pct = int(update.progress * 100)

            if update.phase == UpdatePhase.CHECKING:
                desc = self._format_desc("", "Flatpak", "[dim]checking...[/]")
            elif update.phase == UpdatePhase.DOWNLOADING:
                if update.current_package:
                    pkg = update.current_package[:10]
                    desc = self._format_desc("", f"Flatpak [dim]|[/] {pkg}")
                else:
                    desc = self._format_desc("", "Flatpak", "[dim]downloading...[/]")
            elif update.phase == UpdatePhase.INSTALLING:
                if update.current_package:
                    pkg = update.current_package[:10]
                    desc = self._format_desc("", f"Flatpak [dim]|[/] {pkg}")
                else:
                    desc = self._format_desc("", "Flatpak", "[dim]installing...[/]")
            elif update.phase == UpdatePhase.COMPLETE:
                desc = self._format_desc("", "Flatpak")
            elif update.phase == UpdatePhase.ERROR:
                desc = self._format_desc("", "Flatpak")
            else:
                desc = self._format_desc("", "Flatpak")

            progress.update(task_id, completed=pct, description=desc)

        result = await self._flatpak_updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        if result.success:
            progress.update(
                task_id,
                completed=100,
                success=True,
                description=self._format_desc("", "Flatpak")
            )
        else:
            progress.update(
                task_id,
                completed=100,
                success=False,
                description=self._format_desc("", "Flatpak")
            )

        return result.packages

    def _print_summary(
        self, apt_packages: list[Package], flatpak_packages: list[Package]
    ) -> None:
        """Print minimal summary of updated packages."""
        apt_count = len(apt_packages)
        flatpak_count = len(flatpak_packages)
        total = apt_count + flatpak_count

        self.console.print("   [dim]" + "\u2500" * 40 + "[/]")

        if total == 0:
            self.console.print()
            self.console.print("   [green]\u2713[/] System is up to date")
            self.console.print()
            return

        # Count summary
        parts = []
        if apt_count > 0:
            parts.append(f"{apt_count} APT")
        if flatpak_count > 0:
            parts.append(f"{flatpak_count} Flatpak")

        self.console.print()
        self.console.print(f"   [green]\u2713[/] Updated [bold]{total}[/] packages ({', '.join(parts)})")
        self.console.print()

        # APT Packages Table
        if apt_packages:
            self.console.print(f"   [bold]APT Packages[/] [dim]({apt_count})[/]")
            self.console.print()
            apt_table = Table(
                show_header=True,
                header_style="dim",
                box=None,
                padding=(0, 3),
                collapse_padding=True,
            )
            apt_table.add_column("Package", style="white")
            apt_table.add_column("Old", style="dim", justify="right")
            apt_table.add_column("", style="dim", justify="center", width=3)
            apt_table.add_column("New", style="white", justify="left")

            for pkg in apt_packages[:12]:
                old_ver = pkg.old_version if pkg.old_version else "-"
                new_ver = pkg.new_version if pkg.new_version else "-"
                apt_table.add_row(pkg.name, old_ver, "\u2192", new_ver)

            self.console.print(apt_table)

            if len(apt_packages) > 12:
                self.console.print(f"  [dim]... and {len(apt_packages) - 12} more[/]")

            self.console.print()

        # Flatpak Apps Table
        if flatpak_packages:
            self.console.print(f"   [bold]Flatpak Apps[/] [dim]({flatpak_count})[/]")
            self.console.print()
            flatpak_table = Table(
                show_header=True,
                header_style="dim",
                box=None,
                padding=(0, 3),
                collapse_padding=True,
            )
            flatpak_table.add_column("App", style="white")
            flatpak_table.add_column("Branch", style="dim", justify="right")

            for pkg in flatpak_packages[:8]:
                branch = pkg.new_version or pkg.old_version or "stable"
                flatpak_table.add_row(pkg.name, branch)

            self.console.print(flatpak_table)

            if len(flatpak_packages) > 8:
                self.console.print(f"   [dim]... and {len(flatpak_packages) - 8} more[/]")

            self.console.print()

        self.console.print("   [dim]" + "\u2500" * 40 + "[/]")
        self.console.print()

"""Minimal CLI interface for System Update Manager using Rich."""

import asyncio
import re
from typing import Callable, cast
from rich.console import Console
from rich.progress import (
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    Task as RichTask,
)
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from . import __version__
from .updaters.base import UpdatePhase, UpdateProgress, Package
from .updaters.apt import AptUpdater
from .updaters.flatpak import FlatpakUpdater
from .updaters.snap import SnapUpdater
from .updaters.dnf import DnfUpdater
from .updaters.pacman import PacmanUpdater
from .updaters.aria2_downloader import Aria2Downloader
from .utils.logging import setup_logging

# Precompiled pattern for stripping Rich markup tags
_MARKUP_PATTERN = re.compile(r"\[(green|red|dim|/)\]")


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
        self._apt_updater = AptUpdater()
        self._flatpak_updater = FlatpakUpdater()
        self._snap_updater = SnapUpdater()
        self._dnf_updater = DnfUpdater()
        self._pacman_updater = PacmanUpdater()

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

    async def _handle_aria2_warning(self) -> bool:
        """Display prominent aria2 warning and offer to install it.

        Returns:
            True if aria2 is now available, False otherwise.
        """
        # Barber-pole border - yellow and dim (works on light and dark terminals)
        border_segments = []
        for i in range(48):
            if i % 2 == 0:
                border_segments.append("[bold yellow]█[/]")
            else:
                border_segments.append("[dim]░[/]")
        border = "".join(border_segments)

        # Yellow warning triangle - smooth edges with half blocks
        triangle = [
            "              [bold yellow]▄[/]",
            "             [bold yellow]▟█▙[/]",
            "            [bold yellow]▟███▙[/]",
        ]

        # Print the warning box
        self.console.print()
        self.console.print(f"  {border}")
        self.console.print()

        for line in triangle:
            self.console.print(line)

        self.console.print()
        self.console.print("  [bold]aria2c is not installed[/]")
        self.console.print("  [dim]Downloads will be sequential (slower)[/]")
        self.console.print()
        self.console.print("  aria2 enables parallel package downloads,")
        self.console.print("  significantly speeding up large updates.")
        self.console.print()
        self.console.print(f"  {border}")
        self.console.print()

        # Prompt user
        loop = asyncio.get_running_loop()
        install = await loop.run_in_executor(
            None,
            lambda: Confirm.ask(
                "  [yellow]I can install aria2 right now. It'll only take a few seconds.[/]",
                console=self.console,
                default=True,
            ),
        )

        if not install:
            self.console.print()
            self.console.print("  [dim]Continuing with standard apt. This will take longer![/]")
            self.console.print()
            return False

        return await self._install_aria2()

    async def _install_aria2(self) -> bool:
        """Install aria2 using apt.

        Returns:
            True if installation succeeded, False otherwise.
        """
        self.console.print()
        self.console.print("  [cyan]Installing aria2...[/]")
        self.console.print()

        try:
            process = await asyncio.create_subprocess_exec(
                "sudo", "apt", "install", "-y", "aria2",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            if process.stdout:
                async for line in process.stdout:
                    decoded = line.decode().strip()
                    if decoded:
                        self.console.print(f"  [dim]{decoded}[/]")

            returncode = await process.wait()

            if returncode == 0:
                self.console.print()
                self.console.print("  [green]✓ aria2 installed successfully![/]")
                self.console.print("  [dim]Parallel downloads are now enabled.[/]")
                self.console.print()
                return True
            else:
                self.console.print()
                self.console.print("  [red]✗ Failed to install aria2.[/]")
                self.console.print("  [dim]Continuing with standard apt. This will take longer![/]")
                self.console.print()
                return False

        except Exception as e:
            self.console.print()
            self.console.print(f"  [red]✗ Installation error: {e}[/]")
            self.console.print("  [dim]Continuing with standard apt. This will take longer![/]")
            self.console.print()
            return False

    async def _run_updates(self) -> int:
        """Run APT, Flatpak, Snap, DNF, and Pacman updates concurrently."""
        apt_available = await self._apt_updater.check_available()
        flatpak_available = await self._flatpak_updater.check_available()
        snap_available = await self._snap_updater.check_available()
        dnf_available = await self._dnf_updater.check_available()
        pacman_available = await self._pacman_updater.check_available()

        # Check for aria2c availability
        downloader = Aria2Downloader()
        aria2_available = await downloader.check_available()
        if not aria2_available:
            aria2_available = await self._handle_aria2_warning()

        apt_packages: list[Package] = []
        flatpak_packages: list[Package] = []
        snap_packages: list[Package] = []
        dnf_packages: list[Package] = []
        pacman_packages: list[Package] = []

        # Run updates with progress display
        with Progress(
            TextColumn("  "),  # 2-char indent
            StatusColumn(spinner_name="dots", style="white"),
            TextColumn("{task.description}"),
            BarColumn(bar_width=16, style="dim", complete_style="white", finished_style="green"),
            TaskProgressColumn(),
            SpeedColumn(),
            ETAColumn(),
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

            if snap_available:
                snap_task_id = progress.add_task(
                    self._format_desc("", "Snap"),
                    total=100
                )
                coroutines.append(self._run_snap(progress, snap_task_id))
                task_mapping.append("snap")
            else:
                self.console.print("[dim]   Snap not available[/]")

            if dnf_available:
                dnf_task_id = progress.add_task(
                    self._format_desc("", "DNF"),
                    total=100
                )
                coroutines.append(self._run_dnf(progress, dnf_task_id))
                task_mapping.append("dnf")
            else:
                self.console.print("[dim]   DNF not available[/]")

            if pacman_available:
                pacman_task_id = progress.add_task(
                    self._format_desc("", "Pacman"),
                    total=100
                )
                coroutines.append(self._run_pacman(progress, pacman_task_id))
                task_mapping.append("pacman")
            else:
                self.console.print("[dim]   Pacman not available[/]")

            # Add spacing between "not available" messages and progress bars
            if coroutines:
                self.console.print()

            # Run all updates concurrently
            if coroutines:
                results = await asyncio.gather(*coroutines, return_exceptions=True)

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        self._logger.error(f"Update failed: {result}")
                        continue
                    if task_mapping[i] == "apt":
                        apt_packages = cast(list[Package], result)
                    elif task_mapping[i] == "flatpak":
                        flatpak_packages = cast(list[Package], result)
                    elif task_mapping[i] == "snap":
                        snap_packages = cast(list[Package], result)
                    elif task_mapping[i] == "dnf":
                        dnf_packages = cast(list[Package], result)
                    elif task_mapping[i] == "pacman":
                        pacman_packages = cast(list[Package], result)

        self.console.print()
        self.console.print()

        # Print summary
        self._print_summary(apt_packages, flatpak_packages, snap_packages, dnf_packages, pacman_packages)

        return 0

    async def _run_apt(self, progress: Progress, task_id) -> list[Package]:
        """Run APT update with progress."""
        on_progress = self._create_progress_callback(
            progress, task_id, label="APT", max_pkg_len=12
        )

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
        on_progress = self._create_progress_callback(
            progress, task_id, label="Flatpak", max_pkg_len=10
        )

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

    async def _run_snap(self, progress: Progress, task_id) -> list[Package]:
        """Run Snap update with progress."""
        on_progress = self._create_progress_callback(
            progress, task_id, label="Snap", max_pkg_len=12
        )

        result = await self._snap_updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        if result.success:
            progress.update(
                task_id,
                completed=100,
                success=True,
                description=self._format_desc("", "Snap")
            )
        else:
            progress.update(
                task_id,
                completed=100,
                success=False,
                description=self._format_desc("", "Snap")
            )

        return result.packages

    async def _run_dnf(self, progress: Progress, task_id) -> list[Package]:
        """Run DNF update with progress."""
        on_progress = self._create_progress_callback(
            progress, task_id, label="DNF", max_pkg_len=12
        )

        result = await self._dnf_updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        if result.success:
            progress.update(
                task_id,
                completed=100,
                success=True,
                description=self._format_desc("", "DNF")
            )
        else:
            progress.update(
                task_id,
                completed=100,
                success=False,
                description=self._format_desc("", "DNF")
            )

        return result.packages

    async def _run_pacman(self, progress: Progress, task_id) -> list[Package]:
        """Run Pacman update with progress."""
        on_progress = self._create_progress_callback(
            progress, task_id, label="Pacman", max_pkg_len=12
        )

        result = await self._pacman_updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        if result.success:
            progress.update(
                task_id,
                completed=100,
                success=True,
                description=self._format_desc("", "Pacman")
            )
        else:
            progress.update(
                task_id,
                completed=100,
                success=False,
                description=self._format_desc("", "Pacman")
            )

        return result.packages

    def _print_summary(
        self,
        apt_packages: list[Package],
        flatpak_packages: list[Package],
        snap_packages: list[Package],
        dnf_packages: list[Package],
        pacman_packages: list[Package],
    ) -> None:
        """Print minimal summary of updated packages."""
        apt_count = len(apt_packages)
        flatpak_count = len(flatpak_packages)
        snap_count = len(snap_packages)
        dnf_count = len(dnf_packages)
        pacman_count = len(pacman_packages)
        total = apt_count + flatpak_count + snap_count + dnf_count + pacman_count

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
        if snap_count > 0:
            parts.append(f"{snap_count} Snap")
        if dnf_count > 0:
            parts.append(f"{dnf_count} DNF")
        if pacman_count > 0:
            parts.append(f"{pacman_count} Pacman")

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

            for pkg in apt_packages:
                old_ver = pkg.old_version if pkg.old_version else "-"
                new_ver = pkg.new_version if pkg.new_version else "-"
                apt_table.add_row(pkg.name, old_ver, "\u2192", new_ver)

            self.console.print(apt_table)
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

            for pkg in flatpak_packages:
                branch = pkg.new_version or pkg.old_version or "stable"
                flatpak_table.add_row(pkg.name, branch)

            self.console.print(flatpak_table)
            self.console.print()

        # Snap Apps Table
        if snap_packages:
            self.console.print(f"   [bold]Snap Apps[/] [dim]({snap_count})[/]")
            self.console.print()
            snap_table = Table(
                show_header=True,
                header_style="dim",
                box=None,
                padding=(0, 3),
                collapse_padding=True,
            )
            snap_table.add_column("App", style="white")
            snap_table.add_column("Old", style="dim", justify="right")
            snap_table.add_column("", style="dim", justify="center", width=3)
            snap_table.add_column("New", style="white", justify="left")

            for pkg in snap_packages:
                old_ver = pkg.old_version if pkg.old_version else "-"
                new_ver = pkg.new_version if pkg.new_version else "-"
                snap_table.add_row(pkg.name, old_ver, "\u2192", new_ver)

            self.console.print(snap_table)
            self.console.print()

        # DNF Packages Table
        if dnf_packages:
            self.console.print(f"   [bold]DNF Packages[/] [dim]({dnf_count})[/]")
            self.console.print()
            dnf_table = Table(
                show_header=True,
                header_style="dim",
                box=None,
                padding=(0, 3),
                collapse_padding=True,
            )
            dnf_table.add_column("Package", style="white")
            dnf_table.add_column("Old", style="dim", justify="right")
            dnf_table.add_column("", style="dim", justify="center", width=3)
            dnf_table.add_column("New", style="white", justify="left")

            for pkg in dnf_packages:
                old_ver = pkg.old_version if pkg.old_version else "-"
                new_ver = pkg.new_version if pkg.new_version else "-"
                dnf_table.add_row(pkg.name, old_ver, "\u2192", new_ver)

            self.console.print(dnf_table)
            self.console.print()

        # Pacman Packages Table
        if pacman_packages:
            self.console.print(f"   [bold]Pacman Packages[/] [dim]({pacman_count})[/]")
            self.console.print()
            pacman_table = Table(
                show_header=True,
                header_style="dim",
                box=None,
                padding=(0, 3),
                collapse_padding=True,
            )
            pacman_table.add_column("Package", style="white")
            pacman_table.add_column("Old", style="dim", justify="right")
            pacman_table.add_column("", style="dim", justify="center", width=3)
            pacman_table.add_column("New", style="white", justify="left")

            for pkg in pacman_packages:
                old_ver = pkg.old_version if pkg.old_version else "-"
                new_ver = pkg.new_version if pkg.new_version else "-"
                pacman_table.add_row(pkg.name, old_ver, "\u2192", new_ver)

            self.console.print(pacman_table)
            self.console.print()

        self.console.print("   [dim]" + "\u2500" * 40 + "[/]")
        self.console.print()

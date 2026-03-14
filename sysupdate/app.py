"""Minimal CLI interface for System Update Manager using Rich."""

import asyncio
from dataclasses import dataclass
from typing import Callable
from rich.console import Console
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskID,
    TimeElapsedColumn,
)

from . import __version__
from .ui import (
    StatusColumn,
    PhaseAwareProgressColumn,
    SpeedColumn,
    ETAColumn,
    BAR_WIDTH,
    DESC_WIDTH,
    _MARKUP_PATTERN,
    print_header,
    print_summary,
)
from .updaters.base import (
    UpdatePhase,
    UpdateProgress,
    Package,
    UpdaterProtocol,
    UpdateResult,
)
from .updaters.apt import AptUpdater
from .updaters.flatpak import FlatpakUpdater
from .updaters.snap import SnapUpdater
from .updaters.dnf import DnfUpdater
from .updaters.pacman import PacmanUpdater
from .updaters.aria2_downloader import Aria2Downloader
from .utils.logging import setup_logging
from .utils.aria2 import prompt_install_aria2


@dataclass
class UpdaterConfig:
    """Configuration for an updater in the CLI."""

    updater: UpdaterProtocol
    label: str
    max_pkg_len: int = 12


class SysUpdateCLI:
    """Minimal CLI for system updates with Rich progress display."""

    def __init__(self, verbose: bool = False, dry_run: bool = False) -> None:
        self.verbose = verbose
        self.dry_run = dry_run
        self.console = Console()
        self._logger = setup_logging(verbose)
        self._use_ascii = not self._supports_unicode()
        self._updaters = [
            UpdaterConfig(AptUpdater(), "APT", max_pkg_len=12),
            UpdaterConfig(FlatpakUpdater(), "Flatpak", max_pkg_len=10),
            UpdaterConfig(SnapUpdater(), "Snap", max_pkg_len=12),
            UpdaterConfig(DnfUpdater(), "DNF", max_pkg_len=12),
            UpdaterConfig(PacmanUpdater(), "Pacman", max_pkg_len=12),
        ]

    def _supports_unicode(self) -> bool:
        """Check if the console supports Unicode output."""
        encoding = self.console.encoding
        return encoding is not None and "utf" in encoding.lower()

    def run(self) -> int:
        """Run the update process."""
        self._print_header()

        try:
            return asyncio.run(self._run_updates())
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Interrupted[/]")
            return 130

    def _print_header(self) -> None:
        """Print gradient-colored ASCII art header (delegates to ui module)."""
        print_header(self.console, __version__, self.dry_run, self._use_ascii)

    def _format_desc(self, prefix: str, label: str, detail: str = "") -> str:
        """Format description with fixed width (truncate or pad as needed).

        Args:
            prefix: Status indicator (e.g., "  " for spinner, "check " for complete)
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

        if visible_len < DESC_WIDTH:
            # Pad to fixed width
            return text + " " * (DESC_WIDTH - visible_len)
        elif visible_len > DESC_WIDTH:
            # Truncate visible text and rebuild with markup
            truncated_visible = visible[: DESC_WIDTH - 1] + "\u2026"
            return truncated_visible
        return text

    def _create_progress_callback(
        self,
        progress: Progress,
        task_id: TaskID,
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
                # During checking, show pulse animation (don't set total/completed)
                if update.message:
                    # Extract short status from message (limit to 25 chars)
                    msg = update.message.rstrip(".")
                    if len(msg) > 25:
                        msg = msg[:24] + "\u2026"
                    desc = self._format_desc("", f"{label} [dim]|[/] {msg}")
                else:
                    desc = self._format_desc("", f"{label} [dim]|[/] checking")
                # Keep total=None for pulse animation, only update description
                progress.update(
                    task_id,
                    description=desc,
                    phase=phase_value,
                )
            elif update.phase in (UpdatePhase.DOWNLOADING, UpdatePhase.INSTALLING):
                phase_text = (
                    "downloading"
                    if update.phase == UpdatePhase.DOWNLOADING
                    else "installing"
                )
                if update.current_package:
                    pkg = update.current_package[:max_pkg_len]
                    desc = self._format_desc("", f"{label} [dim]|[/] {pkg}")
                else:
                    desc = self._format_desc("", f"{label} [dim]|[/] {phase_text}")
                # Transition to determinate progress: set total and completed
                progress.update(
                    task_id,
                    total=100,
                    completed=pct,
                    description=desc,
                    phase=phase_value,
                    speed=update.speed,
                    eta=update.eta,
                )
            else:
                desc = self._format_desc("", label)
                progress.update(
                    task_id,
                    total=100,
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
        availability = await asyncio.gather(*[
            cfg.updater.check_available() for cfg in self._updaters
        ])
        available_updaters = [
            (cfg, avail) for cfg, avail in zip(self._updaters, availability)
        ]

        # Collect results by label
        results_by_label: dict[str, list[Package]] = {
            cfg.label: [] for cfg in self._updaters
        }

        failure_count = 0

        with Progress(
            TextColumn("  "),
            StatusColumn(spinner_name="dots", style="white", use_ascii=self._use_ascii),
            TextColumn("{task.description}"),
            BarColumn(
                bar_width=BAR_WIDTH,
                style="dim",
                complete_style="white",
                finished_style="green",
                pulse_style="cyan",
            ),
            PhaseAwareProgressColumn(),
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
                    # Start with total=None for indeterminate pulse animation
                    task_id = progress.add_task(
                        self._format_desc("", cfg.label),
                        total=None,
                        phase="checking",
                    )
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
                        failure_count += 1
                    elif isinstance(result, UpdateResult):
                        if result.success:
                            results_by_label[label] = result.packages
                        else:
                            self._logger.error(
                                f"{label} update failed: {result.error_message}"
                            )
                            failure_count += 1

        self.console.print()
        self.console.print()
        self._print_summary(results_by_label)
        return 1 if failure_count > 0 else 0

    async def _run_updater(
        self,
        progress: Progress,
        task_id: TaskID,
        cfg: UpdaterConfig,
    ) -> UpdateResult:
        """Run an updater with progress tracking."""
        on_progress = self._create_progress_callback(
            progress, task_id, label=cfg.label, max_pkg_len=cfg.max_pkg_len
        )

        result = await cfg.updater.run_update(
            callback=on_progress,
            dry_run=self.dry_run,
        )

        # Ensure we transition to determinate mode and mark complete
        progress.update(
            task_id,
            total=100,
            completed=100,
            success=result.success,
            description=self._format_desc("", cfg.label),
        )
        return result

    def _print_summary(self, results_by_label: dict[str, list[Package]]) -> None:
        """Print minimal summary of updated packages (delegates to ui module)."""
        print_summary(self.console, results_by_label, self._use_ascii)

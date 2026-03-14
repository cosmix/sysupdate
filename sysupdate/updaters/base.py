"""Base protocol and data structures for package updaters."""

from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Protocol, Callable
from datetime import datetime


class UpdatePhase(Enum):
    """Phases of the update process."""

    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    COMPLETE = "complete"
    ERROR = "error"


class PackageStatus(str, Enum):
    """Status of a package during update.

    Extends str so that comparisons like ``status == "pending"`` still work.
    """

    PENDING = "pending"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Package:
    """Represents a package being updated."""

    name: str
    old_version: str = ""
    new_version: str = ""
    size: str = ""
    status: PackageStatus = PackageStatus.PENDING

    def __str__(self) -> str:
        if self.old_version and self.new_version:
            return f"{self.name}: {self.old_version} \u2192 {self.new_version}"
        return self.name


@dataclass
class UpdateProgress:
    """Progress information for an update operation."""

    phase: UpdatePhase = UpdatePhase.IDLE
    progress: float = 0.0  # 0.0 to 1.0
    total_packages: int = 0
    completed_packages: int = 0
    current_package: str = ""
    speed: str = ""  # e.g., "2.3 MB/s"
    eta: str = ""  # e.g., "00:42"
    message: str = ""


@dataclass
class UpdateResult:
    """Result of an update operation."""

    success: bool
    packages: list[Package] = field(default_factory=list)
    error_message: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None


# Type alias for progress callback
ProgressCallback = Callable[[UpdateProgress], None]


def create_scaled_callback(
    callback: ProgressCallback | None,
    scale_start: float,
    scale_end: float,
    phases_to_scale: set[UpdatePhase] | None = None,
) -> ProgressCallback:
    """Create a callback that scales progress from [0,1] to [scale_start, scale_end].

    Args:
        callback: The original callback to wrap. If None, returns a no-op.
        scale_start: The minimum scaled progress value.
        scale_end: The maximum scaled progress value.
        phases_to_scale: If provided, only scale progress for these phases.
            Other phases pass through unchanged.

    Returns:
        A new callback that scales the progress values.
    """

    def scaled(update: UpdateProgress) -> None:
        if callback is None:
            return
        if phases_to_scale is None or update.phase in phases_to_scale:
            scaled_progress = scale_start + (
                update.progress * (scale_end - scale_start)
            )
            callback(
                UpdateProgress(
                    phase=update.phase,
                    progress=scaled_progress,
                    total_packages=update.total_packages,
                    completed_packages=update.completed_packages,
                    current_package=update.current_package,
                    message=update.message,
                    speed=update.speed,
                    eta=update.eta,
                )
            )
        else:
            callback(update)

    return scaled


class UpdaterProtocol(Protocol):
    """Protocol defining the interface for package updaters."""

    name: str

    async def check_available(self) -> bool:
        """Check if this updater is available on the system."""
        ...

    async def check_updates(self) -> list[Package]:
        """Check for available updates without installing."""
        ...

    async def run_update(
        self,
        callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> UpdateResult:
        """
        Run the update process.

        Args:
            callback: Optional callback for progress updates
            dry_run: If True, don't actually install updates

        Returns:
            UpdateResult with success status and package list
        """
        ...


async def read_process_lines(
    stdout: asyncio.StreamReader,
    chunk_size: int = 1024,
) -> AsyncIterator[str]:
    """Async generator that yields lines from a process stdout.

    Handles both newline (``\\n``) and carriage-return (``\\r``) delimiters,
    stripping whitespace from each yielded line. Empty lines are skipped.

    Args:
        stdout: The stream reader from a subprocess stdout pipe.
        chunk_size: Number of bytes to read per chunk.

    Yields:
        Non-empty, stripped lines from the process output.
    """
    buffer = ""
    while True:
        chunk = await stdout.read(chunk_size)
        if not chunk:
            break
        buffer += chunk.decode(errors="replace")
        while "\n" in buffer or "\r" in buffer:
            newline_pos = buffer.find("\n")
            cr_pos = buffer.find("\r")
            if newline_pos == -1:
                split_pos = cr_pos
            elif cr_pos == -1:
                split_pos = newline_pos
            else:
                split_pos = min(newline_pos, cr_pos)
            line = buffer[:split_pos].strip()
            buffer = buffer[split_pos + 1:]
            if line:
                yield line


class BaseUpdater(abc.ABC):
    """Base class implementing the common update lifecycle.

    Subclasses must implement :meth:`name`, :meth:`check_available`,
    :meth:`check_updates`, and :meth:`_do_upgrade`.  The shared
    :meth:`run_update` template orchestrates the checking / dry-run /
    upgrade flow so each updater only contains its manager-specific logic.
    """

    def __init__(self) -> None:
        from ..utils.logging import UpdateLogger

        self._logger: UpdateLogger | None = None
        self._process: asyncio.subprocess.Process | None = None

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Display name for this updater (e.g. ``"DNF Packages"``)."""
        ...

    @property
    def _logger_name(self) -> str:
        """Name used for log file. Override if different from display name."""
        return self.name.split()[0].lower()

    @abc.abstractmethod
    async def check_available(self) -> bool:
        """Check if this updater is available on the system."""
        ...

    @abc.abstractmethod
    async def check_updates(self) -> list[Package]:
        """Check for available updates without installing."""
        ...

    @abc.abstractmethod
    async def _do_upgrade(
        self,
        report: ProgressCallback,
    ) -> tuple[list[Package], bool, str]:
        """Subclass-specific upgrade logic.

        Args:
            report: A progress callback (already scaled for the upgrade phase).

        Returns:
            Tuple of (packages, success, error_message).
        """
        ...

    async def run_update(
        self,
        callback: ProgressCallback | None = None,
        dry_run: bool = False,
    ) -> UpdateResult:
        """Run the update process using the template method pattern.

        Args:
            callback: Optional callback for progress updates.
            dry_run: If True, only check for updates without installing.

        Returns:
            UpdateResult with success status and package list.
        """
        from ..utils.logging import UpdateLogger

        result = UpdateResult(success=False)
        self._logger = UpdateLogger(self._logger_name)

        checking_end = 0.1

        def report(progress: UpdateProgress) -> None:
            if callback:
                callback(progress)

        try:
            report(UpdateProgress(
                phase=UpdatePhase.CHECKING,
                progress=0.0,
                message=f"Checking for {self.name.split()[0]} updates...",
            ))

            if dry_run:
                packages = await self.check_updates()
                result.packages = packages
                result.success = True
                report(UpdateProgress(
                    phase=UpdatePhase.COMPLETE,
                    progress=1.0,
                    completed_packages=len(packages),
                    total_packages=len(packages),
                ))
            else:
                scaled_callback = create_scaled_callback(
                    report,
                    scale_start=checking_end,
                    scale_end=1.0,
                    phases_to_scale={UpdatePhase.DOWNLOADING, UpdatePhase.INSTALLING},
                )
                packages, success, error = await self._do_upgrade(scaled_callback)
                result.packages = packages
                result.success = success
                result.error_message = error
                if success:
                    report(UpdateProgress(
                        phase=UpdatePhase.COMPLETE,
                        progress=1.0,
                        completed_packages=len(packages),
                        total_packages=len(packages),
                    ))
                else:
                    report(UpdateProgress(
                        phase=UpdatePhase.ERROR,
                        message=error,
                    ))
        except FileNotFoundError:
            result.error_message = f"{self.name} not found"
            report(UpdateProgress(
                phase=UpdatePhase.ERROR,
                message=result.error_message,
            ))
        except Exception as e:
            result.error_message = str(e)
            report(UpdateProgress(
                phase=UpdatePhase.ERROR,
                message=str(e),
            ))
        finally:
            if self._process:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
            if self._logger:
                self._logger.close()

        result.end_time = datetime.now()
        return result

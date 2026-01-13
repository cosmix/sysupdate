"""Base protocol and data structures for package updaters."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Callable
from datetime import datetime


class UpdatePhase(Enum):
    """Phases of the update process."""
    IDLE = "idle"
    CHECKING = "checking"
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
    status: str = "pending"  # pending, downloading, installing, complete, error

    def __str__(self) -> str:
        if self.old_version and self.new_version:
            return f"{self.name}: {self.old_version} → {self.new_version}"
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
            scaled_progress = scale_start + (update.progress * (scale_end - scale_start))
            callback(UpdateProgress(
                phase=update.phase,
                progress=scaled_progress,
                total_packages=update.total_packages,
                completed_packages=update.completed_packages,
                current_package=update.current_package,
                message=update.message,
                speed=update.speed,
                eta=update.eta,
            ))
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

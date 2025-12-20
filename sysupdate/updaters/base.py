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

    @property
    def percentage(self) -> int:
        """Return progress as integer percentage."""
        return int(self.progress * 100)


@dataclass
class UpdateResult:
    """Result of an update operation."""
    success: bool
    packages: list[Package] = field(default_factory=list)
    error_message: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def duration(self) -> float:
        """Return duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def package_count(self) -> int:
        """Return number of packages updated."""
        return len([p for p in self.packages if p.status == "complete"])


# Type alias for progress callback
ProgressCallback = Callable[[UpdateProgress], None]


class UpdaterProtocol(Protocol):
    """Protocol defining the interface for package updaters."""

    name: str
    icon: str

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

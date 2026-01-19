"""Package manager update backends."""

from .base import Package, UpdateResult, UpdaterProtocol
from .apt import AptUpdater
from .flatpak import FlatpakUpdater
from .snap import SnapUpdater

__all__ = ["Package", "UpdateResult", "UpdaterProtocol", "AptUpdater", "FlatpakUpdater", "SnapUpdater"]

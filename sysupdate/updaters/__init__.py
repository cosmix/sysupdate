"""Package manager update backends."""

from .base import BaseUpdater, Package, UpdateResult, UpdaterProtocol
from .apt import AptUpdater
from .flatpak import FlatpakUpdater
from .snap import SnapUpdater
from .dnf import DnfUpdater
from .pacman import PacmanUpdater

__all__ = [
    "BaseUpdater",
    "Package",
    "UpdateResult",
    "UpdaterProtocol",
    "AptUpdater",
    "FlatpakUpdater",
    "SnapUpdater",
    "DnfUpdater",
    "PacmanUpdater",
]

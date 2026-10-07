"""Package manager update backends."""

from .apt import AptUpdater
from .base import BaseUpdater, Package, UpdateResult, UpdaterProtocol
from .cli_tools import CliToolUpdater
from .dnf import DnfUpdater
from .flatpak import FlatpakUpdater
from .pacman import PacmanUpdater
from .snap import SnapUpdater

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
    "CliToolUpdater",
]

"""System Update Manager - A beautiful TUI for system updates."""

try:
    from ._version import __version__
except ImportError:
    # Package not built/installed - fallback for development
    __version__ = "0.0.0.dev0+unknown"

"""Logging utilities for System Update Manager."""

from __future__ import annotations

import io
import logging
import os
import warnings
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TextIO


def _get_log_dir() -> Path:
    """Get the appropriate log directory based on privileges.

    Uses /var/log/sysupdate/ when running as root.
    Falls back to XDG_STATE_HOME/sysupdate/logs/ for non-root.
    """
    if os.geteuid() == 0:
        return Path("/var/log/sysupdate")

    xdg_state = os.environ.get("XDG_STATE_HOME", "")
    if xdg_state:
        return Path(xdg_state) / "sysupdate" / "logs"

    return Path.home() / ".local" / "state" / "sysupdate" / "logs"


def get_log_path(suffix: str = "") -> Path:
    """Get path to a log file with timestamp.

    Args:
        suffix: Optional suffix like 'apt' or 'flatpak'

    Returns:
        Path to log file

    Raises:
        RuntimeError: If the log directory path resolves through a symlink
            to an unexpected location (potential symlink attack).
    """
    log_dir = _get_log_dir()
    log_dir.mkdir(parents=True, mode=0o750, exist_ok=True)

    resolved = Path(os.path.realpath(log_dir))
    if resolved != log_dir.resolve():
        msg = (
            f"Log directory symlink mismatch: "
            f"expected {log_dir.resolve()}, got {resolved}"
        )
        raise RuntimeError(msg)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sysupdate_{timestamp}"
    if suffix:
        filename = f"{filename}_{suffix}"
    return log_dir / f"{filename}.log"


def setup_logging(verbose: bool = False) -> logging.Logger:
    """
    Set up logging for the application.

    Args:
        verbose: If True, also log to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("sysupdate")
    logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    logger.handlers.clear()

    # File handler - always enabled
    log_path = get_log_path("main")
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - only if verbose
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


class UpdateLogger:
    """Logger that captures update output for display and file logging.

    Supports the context manager protocol for safe resource cleanup::

        with UpdateLogger("apt") as logger:
            logger.log("updating packages...")
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.log_path = get_log_path(name.lower())
        fd = os.open(
            str(self.log_path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
            0o640,
        )
        self._file: TextIO = io.open(fd, "w", closefd=True)
        self.lines: deque[str] = deque(maxlen=1000)

    def __enter__(self) -> UpdateLogger:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()

    def __del__(self) -> None:
        if hasattr(self, "_file") and not self._file.closed:
            warnings.warn(
                f"UpdateLogger '{self.name}' was not properly closed. "
                "Use 'with UpdateLogger(name) as logger:' or call logger.close().",
                ResourceWarning,
                stacklevel=2,
            )
            self.close()

    def log(self, line: str) -> None:
        """Log a line of output."""
        self._file.write(line + "\n")
        self.lines.append(line)

    def close(self) -> None:
        """Close the log file. Safe to call multiple times."""
        if hasattr(self, "_file") and not self._file.closed:
            self._file.flush()
            self._file.close()

"""Logging utilities for System Update Manager."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import TextIO


LOG_DIR = Path("/tmp/update_logs")


def get_log_path(suffix: str = "") -> Path:
    """
    Get path to a log file with timestamp.

    Args:
        suffix: Optional suffix like 'apt' or 'flatpak'

    Returns:
        Path to log file
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sysupdate_{timestamp}"
    if suffix:
        filename = f"{filename}_{suffix}"
    return LOG_DIR / f"{filename}.log"


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
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - only if verbose
    if verbose:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(levelname)s: %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


class UpdateLogger:
    """Logger that captures update output for display and file logging."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.log_path = get_log_path(name.lower())
        self._file: TextIO = open(self.log_path, "w")
        self.lines: deque[str] = deque(maxlen=1000)  # Keep last 1000 lines in memory

    def log(self, line: str) -> None:
        """Log a line of output."""
        # Write to file
        self._file.write(line + "\n")

        # Keep in memory for display (deque automatically handles maxlen)
        self.lines.append(line)

    def close(self) -> None:
        """Close the log file."""
        self._file.flush()
        self._file.close()

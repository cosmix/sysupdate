"""Tests for sysupdate.utils.logging: _get_log_dir, get_log_path, UpdateLogger, setup_logging."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from sysupdate.utils.logging import (
    UpdateLogger,
    _get_log_dir,
    get_log_path,
    setup_logging,
)


# ---------------------------------------------------------------------------
# _get_log_dir
# ---------------------------------------------------------------------------

class TestGetLogDir:
    """Tests for _get_log_dir privilege and XDG logic."""

    def test_root_returns_var_log(self):
        """Running as root (euid 0) should use /var/log/sysupdate."""
        with patch("os.geteuid", return_value=0):
            result = _get_log_dir()
        assert result == Path("/var/log/sysupdate")

    def test_non_root_default_path(self):
        """Non-root without XDG_STATE_HOME should use ~/.local/state/sysupdate/logs."""
        with patch("os.geteuid", return_value=1000), \
             patch.dict(os.environ, {}, clear=True):
            result = _get_log_dir()
        assert result == Path.home() / ".local" / "state" / "sysupdate" / "logs"

    def test_non_root_xdg_override(self):
        """XDG_STATE_HOME should override the default state directory."""
        with patch("os.geteuid", return_value=1000), \
             patch.dict(os.environ, {"XDG_STATE_HOME": "/custom/state"}, clear=True):
            result = _get_log_dir()
        assert result == Path("/custom/state/sysupdate/logs")

    def test_non_root_empty_xdg_uses_default(self):
        """An empty XDG_STATE_HOME string should fall through to the default."""
        with patch("os.geteuid", return_value=1000), \
             patch.dict(os.environ, {"XDG_STATE_HOME": ""}, clear=True):
            result = _get_log_dir()
        assert result == Path.home() / ".local" / "state" / "sysupdate" / "logs"


# ---------------------------------------------------------------------------
# get_log_path
# ---------------------------------------------------------------------------

class TestGetLogPath:
    """Tests for get_log_path timestamped filename generation."""

    def test_creates_directory(self, tmp_path: Path):
        """get_log_path should create the log directory if it does not exist."""
        log_dir = tmp_path / "logs" / "nested"
        with patch("sysupdate.utils.logging._get_log_dir", return_value=log_dir):
            path = get_log_path("apt")
        assert log_dir.is_dir()
        assert path.parent == log_dir

    def test_filename_format_with_suffix(self, tmp_path: Path):
        """Filename should follow sysupdate_YYYYMMDD_HHMMSS_<suffix>.log pattern."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            path = get_log_path("flatpak")
        pattern = r"^sysupdate_\d{8}_\d{6}_flatpak\.log$"
        assert re.match(pattern, path.name), f"Filename {path.name!r} does not match expected pattern"

    def test_filename_format_without_suffix(self, tmp_path: Path):
        """An empty suffix should produce sysupdate_YYYYMMDD_HHMMSS.log."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            path = get_log_path()
        pattern = r"^sysupdate_\d{8}_\d{6}\.log$"
        assert re.match(pattern, path.name), f"Filename {path.name!r} does not match expected pattern"

    def test_directory_mode(self, tmp_path: Path):
        """Created directory should have mode 0o750."""
        log_dir = tmp_path / "new_dir"
        with patch("sysupdate.utils.logging._get_log_dir", return_value=log_dir):
            get_log_path("test")
        # Check the permission bits (mask off umask-inherited bits)
        mode = log_dir.stat().st_mode & 0o777
        assert mode == 0o750

    def test_existing_directory_ok(self, tmp_path: Path):
        """Calling get_log_path when directory already exists should not raise."""
        log_dir = tmp_path / "existing"
        log_dir.mkdir(parents=True)
        with patch("sysupdate.utils.logging._get_log_dir", return_value=log_dir):
            path = get_log_path("snap")
        assert path.parent == log_dir


# ---------------------------------------------------------------------------
# UpdateLogger
# ---------------------------------------------------------------------------

class TestUpdateLogger:
    """Tests for UpdateLogger context manager, log_line, buffer, and close."""

    def test_context_manager_enter_returns_self(self, tmp_path: Path):
        """__enter__ should return the UpdateLogger instance."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("test") as logger:
                assert isinstance(logger, UpdateLogger)

    def test_context_manager_closes_file(self, tmp_path: Path):
        """__exit__ should close the underlying file."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("test") as logger:
                pass
        assert logger._file.closed

    def test_log_writes_to_file(self, tmp_path: Path):
        """log() should append the line (plus newline) to the log file."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("write") as logger:
                logger.log("hello world")
                logger.log("second line")

        content = logger.log_path.read_text()
        assert "hello world\n" in content
        assert "second line\n" in content

    def test_log_appends_to_deque(self, tmp_path: Path):
        """log() should also append lines to the in-memory deque."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("deque") as logger:
                logger.log("first")
                logger.log("second")

        assert list(logger.lines) == ["first", "second"]

    def test_deque_maxlen_1000(self, tmp_path: Path):
        """The circular buffer should cap at 1000 entries."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("cap") as logger:
                for i in range(1050):
                    logger.log(f"line-{i}")

        assert len(logger.lines) == 1000
        # Oldest 50 lines should have been evicted
        assert logger.lines[0] == "line-50"
        assert logger.lines[-1] == "line-1049"

    def test_close_idempotent(self, tmp_path: Path):
        """Calling close() multiple times should not raise."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = UpdateLogger("idempotent")
            logger.close()
            logger.close()  # second call should be safe

        assert logger._file.closed

    def test_close_flushes_before_closing(self, tmp_path: Path):
        """close() should flush buffered data before closing the file."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = UpdateLogger("flush")
            logger.log("important data")
            logger.close()

        content = logger.log_path.read_text()
        assert "important data" in content

    def test_del_warns_if_not_closed(self, tmp_path: Path):
        """__del__ should emit a ResourceWarning if the file was not closed."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = UpdateLogger("warn")

        with pytest.warns(ResourceWarning, match="not properly closed"):
            logger.__del__()

    def test_log_path_attribute(self, tmp_path: Path):
        """The log_path attribute should point inside the configured log directory."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("path") as logger:
                assert logger.log_path.parent == tmp_path
                assert "path" in logger.log_path.name

    def test_name_attribute(self, tmp_path: Path):
        """The name attribute should match the constructor argument."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("myname") as logger:
                assert logger.name == "myname"

    def test_file_permissions(self, tmp_path: Path):
        """Log files should be created with mode 0o640."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            with UpdateLogger("perms") as logger:
                pass

        mode = logger.log_path.stat().st_mode & 0o777
        assert mode == 0o640


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    """Tests for setup_logging handler configuration."""

    def test_non_verbose_has_one_handler(self, tmp_path: Path):
        """Non-verbose mode should configure only a file handler."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging(verbose=False)

        try:
            assert len(logger.handlers) == 1
            assert isinstance(logger.handlers[0], logging.FileHandler)
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

    def test_verbose_has_two_handlers(self, tmp_path: Path):
        """Verbose mode should add both a file handler and a stream handler."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging(verbose=True)

        try:
            assert len(logger.handlers) == 2
            handler_types = {type(h) for h in logger.handlers}
            assert logging.FileHandler in handler_types
            assert logging.StreamHandler in handler_types
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

    def test_logger_name(self, tmp_path: Path):
        """The returned logger should be named 'sysupdate'."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging()

        try:
            assert logger.name == "sysupdate"
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

    def test_logger_level_debug(self, tmp_path: Path):
        """The logger level should be DEBUG regardless of verbose setting."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging(verbose=False)

        try:
            assert logger.level == logging.DEBUG
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

    def test_file_handler_level_debug(self, tmp_path: Path):
        """The file handler should capture DEBUG and above."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging(verbose=False)

        try:
            file_handler = logger.handlers[0]
            assert file_handler.level == logging.DEBUG
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

    def test_console_handler_level_info(self, tmp_path: Path):
        """The console handler (verbose mode) should only show INFO and above."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging(verbose=True)

        try:
            stream_handler = next(
                h for h in logger.handlers if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
            )
            assert stream_handler.level == logging.INFO
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

    def test_clears_existing_handlers(self, tmp_path: Path):
        """Calling setup_logging twice should not accumulate handlers."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger1 = setup_logging(verbose=True)
            # Close first set of handlers so files are released
            for h in logger1.handlers[:]:
                h.close()

            logger2 = setup_logging(verbose=False)

        try:
            # Should have exactly 1 handler (file only), not 3
            assert len(logger2.handlers) == 1
        finally:
            for h in logger2.handlers[:]:
                h.close()
                logger2.removeHandler(h)

    def test_file_handler_creates_log_file(self, tmp_path: Path):
        """The file handler should create an actual log file on disk."""
        with patch("sysupdate.utils.logging._get_log_dir", return_value=tmp_path):
            logger = setup_logging(verbose=False)

        try:
            log_files = list(tmp_path.glob("sysupdate_*_main.log"))
            assert len(log_files) >= 1
        finally:
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)

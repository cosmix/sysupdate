"""Tests for base updater module: create_scaled_callback, read_process_lines, BaseUpdater.run_update error paths."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from sysupdate.updaters.base import (
    BaseUpdater,
    Package,
    UpdatePhase,
    UpdateProgress,
    create_scaled_callback,
    read_process_lines,
)


# ---------------------------------------------------------------------------
# create_scaled_callback
# ---------------------------------------------------------------------------

class TestCreateScaledCallback:
    """Tests for the create_scaled_callback helper."""

    def test_none_callback_returns_noop(self):
        """A None callback should produce a callable that does nothing."""
        scaled = create_scaled_callback(None, 0.0, 1.0)
        # Should not raise when invoked
        scaled(UpdateProgress(phase=UpdatePhase.DOWNLOADING, progress=0.5))

    def test_none_callback_noop_does_not_call_anything(self):
        """The no-op wrapper should never attempt to call None."""
        scaled = create_scaled_callback(None, 0.0, 1.0)
        # If it tried ``None(…)`` we would get a TypeError
        scaled(UpdateProgress())

    def test_scaling_downloading_phase(self):
        """Progress in a scaled phase should map [0,1] -> [scale_start, scale_end]."""
        received: list[UpdateProgress] = []
        def cb(p): received.append(p)

        scaled = create_scaled_callback(
            cb,
            scale_start=0.1,
            scale_end=1.0,
            phases_to_scale={UpdatePhase.DOWNLOADING},
        )

        scaled(UpdateProgress(phase=UpdatePhase.DOWNLOADING, progress=0.0))
        scaled(UpdateProgress(phase=UpdatePhase.DOWNLOADING, progress=0.5))
        scaled(UpdateProgress(phase=UpdatePhase.DOWNLOADING, progress=1.0))

        assert received[0].progress == pytest.approx(0.1)
        assert received[1].progress == pytest.approx(0.55)
        assert received[2].progress == pytest.approx(1.0)

    def test_non_scaled_phase_passes_through(self):
        """Phases not in phases_to_scale should pass the original progress unchanged."""
        received: list[UpdateProgress] = []
        def cb(p): received.append(p)

        original = UpdateProgress(phase=UpdatePhase.CHECKING, progress=0.42)
        scaled = create_scaled_callback(
            cb,
            scale_start=0.1,
            scale_end=1.0,
            phases_to_scale={UpdatePhase.DOWNLOADING},
        )
        scaled(original)

        assert received[0] is original
        assert received[0].progress == pytest.approx(0.42)

    def test_phases_to_scale_none_scales_all(self):
        """When phases_to_scale is None every phase is scaled."""
        received: list[UpdateProgress] = []
        def cb(p): received.append(p)

        scaled = create_scaled_callback(cb, scale_start=0.2, scale_end=0.8)

        scaled(UpdateProgress(phase=UpdatePhase.CHECKING, progress=0.0))
        scaled(UpdateProgress(phase=UpdatePhase.INSTALLING, progress=1.0))

        assert received[0].progress == pytest.approx(0.2)
        assert received[1].progress == pytest.approx(0.8)

    def test_boundary_zero(self):
        """progress=0.0 should map to scale_start."""
        received: list[UpdateProgress] = []
        def cb(p): received.append(p)

        scaled = create_scaled_callback(
            cb,
            scale_start=0.25,
            scale_end=0.75,
            phases_to_scale={UpdatePhase.DOWNLOADING},
        )
        scaled(UpdateProgress(phase=UpdatePhase.DOWNLOADING, progress=0.0))

        assert received[0].progress == pytest.approx(0.25)

    def test_boundary_one(self):
        """progress=1.0 should map to scale_end."""
        received: list[UpdateProgress] = []
        def cb(p): received.append(p)

        scaled = create_scaled_callback(
            cb,
            scale_start=0.25,
            scale_end=0.75,
            phases_to_scale={UpdatePhase.DOWNLOADING},
        )
        scaled(UpdateProgress(phase=UpdatePhase.DOWNLOADING, progress=1.0))

        assert received[0].progress == pytest.approx(0.75)

    def test_all_fields_preserved_in_scaled_copy(self):
        """The scaled UpdateProgress should carry over every field except progress."""
        received: list[UpdateProgress] = []
        def cb(p): received.append(p)

        original = UpdateProgress(
            phase=UpdatePhase.DOWNLOADING,
            progress=0.5,
            total_packages=10,
            completed_packages=3,
            current_package="libssl3",
            speed="4.2 MB/s",
            eta="00:12",
            message="Downloading...",
        )
        scaled = create_scaled_callback(
            cb,
            scale_start=0.1,
            scale_end=0.9,
            phases_to_scale={UpdatePhase.DOWNLOADING},
        )
        scaled(original)

        result = received[0]
        assert result.phase == UpdatePhase.DOWNLOADING
        assert result.total_packages == 10
        assert result.completed_packages == 3
        assert result.current_package == "libssl3"
        assert result.speed == "4.2 MB/s"
        assert result.eta == "00:12"
        assert result.message == "Downloading..."
        # progress should be scaled: 0.1 + 0.5 * 0.8 = 0.5
        assert result.progress == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# read_process_lines
# ---------------------------------------------------------------------------

def _make_stream_reader(data: bytes) -> asyncio.StreamReader:
    """Create a StreamReader pre-loaded with *data* so reads return it then EOF."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class TestReadProcessLines:
    """Tests for the read_process_lines async generator."""

    async def test_newline_delimited(self):
        """Standard newline-delimited output should yield each line."""
        reader = _make_stream_reader(b"line1\nline2\nline3\n")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == ["line1", "line2", "line3"]

    async def test_carriage_return_delimited(self):
        """Pure \\r delimiters (Flatpak-style) should yield each segment."""
        reader = _make_stream_reader(b"progress 10%\rprogress 50%\rprogress 100%\r")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == ["progress 10%", "progress 50%", "progress 100%"]

    async def test_mixed_cr_lf(self):
        """Mixed \\r\\n sequences should split correctly without empty yields."""
        reader = _make_stream_reader(b"alpha\r\nbeta\rgamma\n")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == ["alpha", "beta", "gamma"]

    async def test_empty_lines_skipped(self):
        """Empty lines (consecutive delimiters) should not be yielded."""
        reader = _make_stream_reader(b"first\n\n\nsecond\n")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == ["first", "second"]

    async def test_whitespace_only_lines_skipped(self):
        """Lines containing only whitespace should not be yielded."""
        reader = _make_stream_reader(b"data\n   \n\t\nmore\n")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == ["data", "more"]

    async def test_trailing_content_without_delimiter(self):
        """Content after the last delimiter but before EOF stays in the buffer.

        The implementation only yields when a delimiter is found, so
        trailing content without a final delimiter is not yielded.
        """
        reader = _make_stream_reader(b"line1\ntrailing")
        lines = [line async for line in read_process_lines(reader)]
        # "trailing" has no delimiter after it, so it stays in the buffer
        assert lines == ["line1"]

    async def test_empty_stream(self):
        """An empty stream should yield nothing."""
        reader = _make_stream_reader(b"")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == []

    async def test_strips_leading_trailing_whitespace(self):
        """Whitespace around line content should be stripped."""
        reader = _make_stream_reader(b"  hello  \n  world  \n")
        lines = [line async for line in read_process_lines(reader)]
        assert lines == ["hello", "world"]

    async def test_handles_decode_errors(self):
        """Invalid UTF-8 bytes should be replaced rather than raising."""
        reader = _make_stream_reader(b"valid\xff\xfeline\n")
        lines = [line async for line in read_process_lines(reader)]
        assert len(lines) == 1
        assert "valid" in lines[0]

    async def test_chunked_reads(self):
        """Small chunk_size should still reassemble lines correctly."""
        reader = _make_stream_reader(b"hello world\n")
        lines = [line async for line in read_process_lines(reader, chunk_size=3)]
        assert lines == ["hello world"]


# ---------------------------------------------------------------------------
# BaseUpdater.run_update error paths
# ---------------------------------------------------------------------------

class _StubUpdater(BaseUpdater):
    """Minimal concrete subclass for testing BaseUpdater.run_update."""

    def __init__(self, *, do_upgrade_side_effect=None, do_upgrade_return=None):
        super().__init__()
        self._do_upgrade_effect = do_upgrade_side_effect
        self._do_upgrade_return = do_upgrade_return or ([], True, "")

    @property
    def name(self) -> str:
        return "Stub Packages"

    async def check_available(self) -> bool:
        return True

    async def check_updates(self) -> list[Package]:
        return [Package(name="stub-pkg")]

    async def _do_upgrade(self, report):
        if self._do_upgrade_effect is not None:
            raise self._do_upgrade_effect
        return self._do_upgrade_return


class TestBaseUpdaterRunUpdate:
    """Tests for BaseUpdater.run_update error handling and control flow."""

    async def test_file_not_found_error(self):
        """FileNotFoundError should set error_message and report ERROR phase."""
        updater = _StubUpdater(do_upgrade_side_effect=FileNotFoundError("apt"))
        progress_updates: list[UpdateProgress] = []

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(
                callback=lambda p: progress_updates.append(p),
            )

        assert result.success is False
        assert "not found" in result.error_message
        assert any(p.phase == UpdatePhase.ERROR for p in progress_updates)

    async def test_generic_exception(self):
        """A generic Exception should be caught and surfaced as error_message."""
        updater = _StubUpdater(
            do_upgrade_side_effect=RuntimeError("something broke"),
        )
        progress_updates: list[UpdateProgress] = []

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(
                callback=lambda p: progress_updates.append(p),
            )

        assert result.success is False
        assert "something broke" in result.error_message
        assert any(p.phase == UpdatePhase.ERROR for p in progress_updates)

    async def test_process_killed_in_finally(self):
        """If _process is set, it should be killed in the finally block."""
        updater = _StubUpdater(
            do_upgrade_side_effect=RuntimeError("boom"),
        )
        mock_process = MagicMock()
        mock_process.kill = MagicMock()

        with patch("sysupdate.utils.logging.UpdateLogger"):
            updater._process = mock_process
            await updater.run_update()

        mock_process.kill.assert_called_once()

    async def test_process_lookup_error_suppressed(self):
        """ProcessLookupError from process.kill() should be silently ignored."""
        updater = _StubUpdater(
            do_upgrade_side_effect=RuntimeError("boom"),
        )
        mock_process = MagicMock()
        mock_process.kill.side_effect = ProcessLookupError

        with patch("sysupdate.utils.logging.UpdateLogger"):
            updater._process = mock_process
            # Should not raise
            result = await updater.run_update()

        assert result.success is False
        mock_process.kill.assert_called_once()

    async def test_dry_run_skips_upgrade(self):
        """dry_run=True should call check_updates and skip _do_upgrade entirely."""
        updater = _StubUpdater()
        progress_updates: list[UpdateProgress] = []

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(
                callback=lambda p: progress_updates.append(p),
                dry_run=True,
            )

        assert result.success is True
        assert len(result.packages) == 1
        assert result.packages[0].name == "stub-pkg"
        assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)

    async def test_non_dry_run_calls_upgrade(self):
        """dry_run=False should call _do_upgrade and forward its results."""
        packages = [Package(name="upgraded-pkg", old_version="1.0", new_version="2.0")]
        updater = _StubUpdater(do_upgrade_return=(packages, True, ""))
        progress_updates: list[UpdateProgress] = []

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(
                callback=lambda p: progress_updates.append(p),
                dry_run=False,
            )

        assert result.success is True
        assert len(result.packages) == 1
        assert result.packages[0].name == "upgraded-pkg"
        assert any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)

    async def test_upgrade_failure_reports_error_phase(self):
        """When _do_upgrade returns success=False, ERROR phase should be reported."""
        updater = _StubUpdater(do_upgrade_return=([], False, "upgrade failed"))
        progress_updates: list[UpdateProgress] = []

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(
                callback=lambda p: progress_updates.append(p),
                dry_run=False,
            )

        assert result.success is False
        assert result.error_message == "upgrade failed"
        assert any(
            p.phase == UpdatePhase.ERROR and p.message == "upgrade failed"
            for p in progress_updates
        )

    async def test_end_time_always_set(self):
        """end_time should be populated regardless of success or failure."""
        updater = _StubUpdater()

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(dry_run=True)

        assert result.end_time is not None

    async def test_logger_closed_on_success(self):
        """The UpdateLogger should be closed even on a successful run."""
        updater = _StubUpdater()
        mock_logger = MagicMock()

        with patch("sysupdate.utils.logging.UpdateLogger", return_value=mock_logger):
            await updater.run_update(dry_run=True)

        mock_logger.close.assert_called_once()

    async def test_logger_closed_on_exception(self):
        """The UpdateLogger should be closed even when _do_upgrade raises."""
        updater = _StubUpdater(do_upgrade_side_effect=RuntimeError("fail"))
        mock_logger = MagicMock()

        with patch("sysupdate.utils.logging.UpdateLogger", return_value=mock_logger):
            await updater.run_update()

        mock_logger.close.assert_called_once()

    async def test_no_callback_does_not_raise(self):
        """Passing callback=None should not cause errors."""
        updater = _StubUpdater()

        with patch("sysupdate.utils.logging.UpdateLogger"):
            result = await updater.run_update(callback=None, dry_run=True)

        assert result.success is True

    async def test_checking_phase_reported_first(self):
        """The first progress report should be the CHECKING phase."""
        updater = _StubUpdater()
        progress_updates: list[UpdateProgress] = []

        with patch("sysupdate.utils.logging.UpdateLogger"):
            await updater.run_update(
                callback=lambda p: progress_updates.append(p),
                dry_run=True,
            )

        assert progress_updates[0].phase == UpdatePhase.CHECKING
        assert progress_updates[0].progress == 0.0

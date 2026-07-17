"""Tests for the update summary rendering (sysupdate/summary.py)."""

import re
from io import StringIO

from rich.console import Console

from sysupdate.summary import (
    MANAGER_ACCENTS,
    format_elapsed,
    print_summary,
    version_diff_text,
)
from sysupdate.updaters.base import Package


ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def console_text(console: Console) -> str:
    """Console output with ANSI escape sequences stripped."""
    return ANSI_PATTERN.sub("", console.file.getvalue())


def make_console() -> Console:
    return Console(file=StringIO(), width=100, color_system="truecolor")


def empty_results(**overrides) -> dict:
    results = {"APT": [], "Flatpak": [], "Snap": [], "DNF": [], "Pacman": []}
    results.update(overrides)
    return results


class TestVersionDiff:
    """Highlighting of the changed part of a version string."""

    def test_common_prefix_dimmed_changed_bold(self):
        text = version_diff_text("3.0.11", "3.0.13")
        assert text.plain == "3.0.13"
        styles = [(text.plain[s.start : s.end], str(s.style)) for s in text.spans]
        assert ("3.0.", "dim") in styles
        assert ("13", "bold white") in styles

    def test_component_boundary_not_char_boundary(self):
        # 3.11.6 -> 3.11.8: '3.11.' is common, '8' changed
        text = version_diff_text("3.11.6", "3.11.8")
        styles = [(text.plain[s.start : s.end], str(s.style)) for s in text.spans]
        assert ("3.11.", "dim") in styles
        assert ("8", "bold white") in styles

    def test_no_old_version_renders_plain(self):
        assert version_diff_text(None, "2.0").plain == "2.0"
        assert version_diff_text("", "2.0").plain == "2.0"

    def test_missing_new_version_renders_dash(self):
        assert version_diff_text("1.0", None).plain == "-"

    def test_identical_versions_render_plain(self):
        text = version_diff_text("1.0", "1.0")
        assert text.plain == "1.0"
        assert not text.spans


class TestFormatElapsed:
    """Elapsed time formatting."""

    def test_seconds(self):
        assert format_elapsed(42.4) == "42s"

    def test_minutes(self):
        assert format_elapsed(125) == "2m 05s"

    def test_negative_clamped(self):
        assert format_elapsed(-3) == "0s"


class TestManagerAccents:
    """Every configured updater label has an accent color."""

    def test_all_managers_have_accents(self):
        assert set(MANAGER_ACCENTS) == {"APT", "Flatpak", "Snap", "DNF", "Pacman"}

    def test_accents_are_hex_colors(self):
        for accent in MANAGER_ACCENTS.values():
            assert accent.startswith("#") and len(accent) == 7


class TestPrintSummary:
    """Summary rendering paths."""

    def test_manager_chip_and_accent_color(self):
        console = make_console()
        packages = [Package(name="pkg1", old_version="1.0", new_version="2.0")]
        print_summary(console, empty_results(APT=packages), use_ascii=False)
        assert "▪" in console_text(console)
        # APT accent (#22d3ee) as a truecolor escape in the raw output
        assert "38;2;34;211;238" in console.file.getvalue()

    def test_up_to_date_message(self):
        console = make_console()
        print_summary(console, empty_results(), use_ascii=False)
        assert "up to date" in console_text(console)

    def test_count_bars_shown_for_multiple_managers(self):
        console = make_console()
        results = empty_results(
            APT=[Package(name=f"p{i}") for i in range(4)],
            Snap=[Package(name="s1")],
        )
        print_summary(console, results, use_ascii=True)
        output = console_text(console)
        # ASCII bars: APT has the peak (full width), Snap is shorter
        assert "=" * 20 in output

    def test_count_bars_hidden_for_single_manager(self):
        console = make_console()
        results = empty_results(APT=[Package(name="p1"), Package(name="p2")])
        print_summary(console, results, use_ascii=True)
        # No count-bar rows: the only '=' output would be a bar
        assert "==" not in console_text(console)

    def test_failures_shown_with_log_pointer(self):
        console = make_console()
        print_summary(
            console,
            empty_results(),
            use_ascii=False,
            failures=[("DNF", "connection timeout")],
            log_dir="/var/log/sysupdate",
        )
        output = console_text(console)
        assert "DNF failed" in output
        assert "connection timeout" in output
        assert "/var/log/sysupdate" in output
        # Failure-only run must not claim the system is up to date
        assert "up to date" not in output

    def test_elapsed_tagline(self):
        console = make_console()
        packages = [Package(name="pkg1", old_version="1.0", new_version="2.0")]
        print_summary(console, empty_results(APT=packages), use_ascii=False, elapsed=42)
        assert "Done in 42s" in console_text(console)

    def test_elapsed_tagline_when_up_to_date(self):
        console = make_console()
        print_summary(console, empty_results(), use_ascii=False, elapsed=8)
        assert "Checked in 8s" in console_text(console)

    def test_count_line_static_when_not_terminal(self):
        console = make_console()
        packages = [Package(name="pkg1", old_version="1.0", new_version="2.0")]
        print_summary(console, empty_results(APT=packages), use_ascii=False)
        output = console_text(console)
        assert "Updated" in output
        assert "1 APT" in output
        # No Live cursor-hide control sequence (no animation ran)
        assert "?25l" not in console.file.getvalue()

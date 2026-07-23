"""Tests for the animated startup banner (sysupdate/banner.py)."""

import re
from io import StringIO

from rich.console import Console

from sysupdate import banner
from sysupdate.banner import (
    BLOCK_LOGO,
    FIGLET_LOGO,
    GRADIENT_STOPS,
    _select_logo,
    banner_rows,
    build_frame,
    gradient_rgb,
    gradient_rule,
    hex_to_rgb,
    sheen_intensity,
    sheen_sweep_line,
    show_banner,
)

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def make_console(width: int = 100, terminal: bool = False) -> Console:
    """Create a Console writing to a StringIO buffer."""
    return Console(
        file=StringIO(),
        width=width,
        force_terminal=terminal or None,
        color_system="truecolor",
    )


def console_text(console: Console) -> str:
    """Console output with ANSI escape sequences stripped."""
    return ANSI_PATTERN.sub("", console.file.getvalue())


class TestLogoArt:
    """The art blocks must be rectangular for the diagonal math to hold."""

    def test_block_logo_rows_uniform_width(self):
        assert len({len(line) for line in BLOCK_LOGO}) == 1

    def test_figlet_logo_rows_uniform_width(self):
        assert len({len(line) for line in FIGLET_LOGO}) == 1

    def test_figlet_logo_is_pure_ascii(self):
        for line in FIGLET_LOGO:
            assert line.isascii()

    def test_block_logo_fits_80_columns(self):
        assert len(BLOCK_LOGO[0]) + 2 * banner.MARGIN <= 80


class TestGradientMath:
    """Gradient sampling and sheen falloff."""

    def test_gradient_endpoints(self):
        assert gradient_rgb(0.0) == GRADIENT_STOPS[0]
        assert gradient_rgb(1.0) == GRADIENT_STOPS[-1]

    def test_gradient_clamps_out_of_range(self):
        assert gradient_rgb(-5.0) == GRADIENT_STOPS[0]
        assert gradient_rgb(5.0) == GRADIENT_STOPS[-1]

    def test_gradient_midpoint_is_interior_stop(self):
        # With 5 stops, t=0.5 lands exactly on the middle stop
        assert gradient_rgb(0.5) == GRADIENT_STOPS[2]

    def test_sheen_peaks_at_band_center(self):
        assert sheen_intensity(0.0) == 1.0

    def test_sheen_decays_symmetrically(self):
        assert sheen_intensity(4.0) == sheen_intensity(-4.0)
        assert sheen_intensity(4.0) < sheen_intensity(1.0)
        assert sheen_intensity(30.0) < 0.001


class TestBuildFrame:
    """Frame rendering."""

    def test_final_frame_contains_logo_and_version(self):
        rows = banner_rows(BLOCK_LOGO, "2.1.0", use_ascii=False)
        plain = build_frame(rows).plain
        assert BLOCK_LOGO[0] in plain
        assert "v2.1.0" in plain

    def test_sweep_before_art_renders_same_glyphs(self):
        rows = banner_rows(BLOCK_LOGO, "2.1.0", use_ascii=False)
        # Band far before the art: glyphs unrevealed but characters intact
        assert build_frame(rows, sweep=-100.0).plain == build_frame(rows).plain

    def test_unrevealed_frame_is_darker_than_final(self):
        rows = banner_rows(BLOCK_LOGO, "2.1.0", use_ascii=False)
        def first_glyph_color(frame):
            for span in frame.spans:
                if span.style and "#" in str(span.style):
                    return str(span.style)
            raise AssertionError("no colored span found")
        dark = first_glyph_color(build_frame(rows, sweep=-100.0))
        final = first_glyph_color(build_frame(rows))
        assert dark != final

    def test_gradient_rule_width_and_style(self):
        rule = gradient_rule(40, use_ascii=False, indent=3)
        assert rule.plain == " " * 3 + "─" * 40
        rule_ascii = gradient_rule(40, use_ascii=True, indent=3)
        assert rule_ascii.plain == " " * 3 + "-" * 40


class TestLogoSelection:
    """Adaptive art selection by terminal capability and width."""

    def test_wide_unicode_terminal_gets_block_logo(self):
        assert _select_logo(100, use_ascii=False) is BLOCK_LOGO

    def test_ascii_terminal_gets_figlet(self):
        assert _select_logo(100, use_ascii=True) is FIGLET_LOGO

    def test_narrow_terminal_gets_figlet(self):
        assert _select_logo(60, use_ascii=False) is FIGLET_LOGO


class TestShowBanner:
    """The public entry point, static and animated paths."""

    def test_static_path_prints_version(self):
        console = make_console()
        show_banner(console, "2.1.0", dry_run=False, use_ascii=False)
        output = console_text(console)
        assert "v2.1.0" in output
        assert "DRY RUN" not in output

    def test_static_path_dry_run_indicator(self):
        console = make_console()
        show_banner(console, "2.1.0", dry_run=True, use_ascii=False)
        assert "DRY RUN" in console_text(console)

    def test_ascii_mode_avoids_unicode_blocks(self):
        console = make_console()
        show_banner(console, "2.1.0", dry_run=False, use_ascii=True)
        output = console_text(console)
        assert "█" not in output
        assert "─" not in output

    def test_animated_path_renders_final_frame(self, monkeypatch):
        # Zero duration: the sweep loop exits immediately, leaving only
        # the final Live frame — exercises the Live code path quickly.
        monkeypatch.setattr(banner, "ANIMATION_SECONDS", 0.0)
        console = make_console(terminal=True)
        show_banner(console, "2.1.0", dry_run=False, use_ascii=False)
        output = console_text(console)
        assert "v2.1.0" in output
        assert BLOCK_LOGO[0] in output

    def test_animate_false_skips_live_on_terminal(self):
        console = make_console(terminal=True)
        show_banner(console, "2.1.0", dry_run=False, use_ascii=False, animate=False)
        raw = console.file.getvalue()
        # No Live cursor-hide control sequence: static path was used
        assert "?25l" not in raw
        assert "v2.1.0" in console_text(console)


class TestColorHelpers:
    """Shared color primitives."""

    def test_hex_to_rgb(self):
        assert hex_to_rgb("#22d3ee") == (34, 211, 238)
        assert hex_to_rgb("ffffff") == (255, 255, 255)


class TestSheenSweepLine:
    """Single-line sheen sweep."""

    def test_static_path_prints_segments(self):
        console = make_console()
        segments = [("✓ ", (74, 222, 128), "bold"), ("done", (226, 232, 240), "")]
        sheen_sweep_line(console, segments, indent=3)
        raw = console.file.getvalue()
        assert "✓ done" in ANSI_PATTERN.sub("", raw)
        assert "?25l" not in raw

    def test_animate_false_never_uses_live(self):
        console = make_console(terminal=True)
        sheen_sweep_line(console, [("hi", (255, 255, 255), "")], animate=False)
        assert "?25l" not in console.file.getvalue()

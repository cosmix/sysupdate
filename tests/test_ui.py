"""Tests for Rich UI components (sysupdate/ui.py)."""

from rich.progress import Progress, Task as RichTask

from sysupdate.ui import GradientBarColumn, StatusColumn


def make_task(total=None, completed=0, **fields) -> RichTask:
    """Create a real Rich Task via a Progress instance."""
    progress = Progress()
    task_id = progress.add_task("x", total=total, **fields)
    if completed:
        progress.update(task_id, completed=completed)
    return progress.tasks[0]


class TestGradientBarColumn:
    """Gradient progress bar rendering."""

    def test_determinate_half_fill(self):
        column = GradientBarColumn(bar_width=16)
        bar = column.render(make_task(total=100, completed=50))
        assert bar.plain == "━" * 16
        # 8 gradient-colored cells, 8 dim track cells
        hex_spans = [s for s in bar.spans if "#" in str(s.style)]
        assert len(hex_spans) == 8

    def test_indeterminate_is_fully_styled(self):
        column = GradientBarColumn(bar_width=16)
        bar = column.render(make_task(total=None))
        assert bar.plain == "━" * 16
        hex_spans = [s for s in bar.spans if "#" in str(s.style)]
        assert len(hex_spans) == 16

    def test_complete_bar_shows_full_gradient(self):
        column = GradientBarColumn(bar_width=16)
        bar = column.render(make_task(total=100, completed=100, success=True))
        hex_spans = [s for s in bar.spans if "#" in str(s.style)]
        assert len(hex_spans) == 16

    def test_error_bar_is_red_shifted(self):
        column = GradientBarColumn(bar_width=16)
        bar = column.render(make_task(total=100, completed=100, success=False))
        # First cell would be cyan (green > red); the failure tint flips it
        style = str(bar.spans[0].style)
        r, g = int(style[1:3], 16), int(style[3:5], 16)
        assert r > g

    def test_ascii_fallback_chars(self):
        column = GradientBarColumn(bar_width=16, use_ascii=True)
        bar = column.render(make_task(total=100, completed=50))
        assert bar.plain == "=" * 8 + "-" * 8


class TestStatusColumn:
    """Phase-aware status badge."""

    def test_finished_success_symbol(self):
        column = StatusColumn()
        task = make_task(total=100, completed=100, success=True)
        text = column.render(task)
        assert text.plain == "✓"
        assert "#4ade80" in str(text.style)

    def test_finished_error_symbol(self):
        column = StatusColumn()
        task = make_task(total=100, completed=100, success=False)
        text = column.render(task)
        assert text.plain == "✗"
        assert "#f87171" in str(text.style)

    def test_checking_phase_shows_spinner(self):
        column = StatusColumn()
        text = column.render(make_task(total=None, phase="checking"))
        # A spinner frame, not a static phase glyph
        assert text.plain.strip() not in ("✓", "✗", "↓", "⚙", "●", "")

    def test_downloading_phase_symbol(self):
        column = StatusColumn()
        text = column.render(make_task(total=100, phase="downloading"))
        assert text.plain == "↓"
        assert "#22d3ee" in str(text.style)

    def test_ascii_symbols(self):
        column = StatusColumn(use_ascii=True)
        task = make_task(total=100, completed=100, success=True)
        assert column.render(task).plain == "+"
        text = column.render(make_task(total=100, phase="installing"))
        assert text.plain == "*"

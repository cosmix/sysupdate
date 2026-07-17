"""Rich progress-display components for System Update Manager."""

import math
import re

from rich.progress import (
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    Task as RichTask,
)
from rich.text import Text

from .banner import (
    DEFAULT_ACCENT,
    ERROR_STYLE,
    SHEEN_RGB,
    SUCCESS_STYLE,
    blend_rgb,
    gradient_rgb,
    scale_rgb,
)

# ============================================================================
# Module-level constants
# ============================================================================

# Fixed width for description column (prefix + label + detail text)
DESC_WIDTH = 30

# Progress thresholds - fraction of progress bar reserved for checking phase
CHECKING_PROGRESS_END = 0.1

# Progress bar width in characters
BAR_WIDTH = 16

# Precompiled pattern for stripping Rich markup tags
_MARKUP_PATTERN = re.compile(r"\[[^\]]*\]")


class StatusColumn(SpinnerColumn):
    """Status badge: animated spinner while checking, phase glyphs after."""

    # Unicode phase symbols for terminals with full Unicode support
    PHASE_STYLES: dict[str, tuple[str, str]] = {
        "downloading": ("#22d3ee", "\u2193"),
        "installing": ("#fbbf24", "\u2699"),
        "complete": (SUCCESS_STYLE, "\u2713"),
        "error": (ERROR_STYLE, "\u2717"),
    }

    # ASCII fallback symbols for terminals without Unicode support
    ASCII_PHASE_STYLES: dict[str, tuple[str, str]] = {
        "downloading": ("#22d3ee", "v"),
        "installing": ("#fbbf24", "*"),
        "complete": (SUCCESS_STYLE, "+"),
        "error": (ERROR_STYLE, "x"),
    }

    def __init__(self, use_ascii: bool = False, **kwargs):
        # The "line" spinner is pure ASCII; "dots" needs braille glyphs
        kwargs.setdefault("spinner_name", "line" if use_ascii else "dots")
        kwargs.setdefault("style", DEFAULT_ACCENT)
        super().__init__(**kwargs)
        self.use_ascii = use_ascii

    def render(self, task: RichTask) -> Text:
        styles = self.ASCII_PHASE_STYLES if self.use_ascii else self.PHASE_STYLES

        if task.finished:
            if task.fields.get("success", True):
                symbol = "+" if self.use_ascii else "\u2713"
                return Text(symbol, style=f"bold {SUCCESS_STYLE}")
            symbol = "x" if self.use_ascii else "\u2717"
            return Text(symbol, style=f"bold {ERROR_STYLE}")

        phase = task.fields.get("phase", "checking")
        if phase == "checking":
            # Live spinner while probing for updates
            return super().render(task)
        default_symbol = "." if self.use_ascii else "\u25cf"
        style, symbol = styles.get(phase, ("white", default_symbol))
        return Text(symbol, style=style)


class GradientBarColumn(ProgressColumn):
    """Progress bar that reveals the banner gradient as it fills.

    The bar is pre-painted with the nebula gradient: filling it uncovers
    the colors in place, echoing the banner's sheen reveal. Indeterminate
    tasks show the sheen motif directly \u2014 a soft highlight band sweeping
    across a dimmed gradient track.
    """

    # Sheen band width (cells) and sweep speed (cells/second) while pulsing
    PULSE_SIGMA = 2.0
    PULSE_SPEED = 14.0

    def __init__(self, bar_width: int = BAR_WIDTH, use_ascii: bool = False) -> None:
        super().__init__()
        self.bar_width = bar_width
        self.use_ascii = use_ascii

    def render(self, task: RichTask) -> Text:
        width = self.bar_width
        fill_char = "=" if self.use_ascii else "\u2501"
        track_char = "-" if self.use_ascii else "\u2501"
        span = max(width - 1, 1)
        bar = Text(no_wrap=True)

        if task.total is None:
            # Indeterminate: sheen band sweeping over a dimmed gradient
            cycle = width + 6.0 * self.PULSE_SIGMA
            pos = (task.get_time() * self.PULSE_SPEED) % cycle - 3.0 * self.PULSE_SIGMA
            for i in range(width):
                base = scale_rgb(gradient_rgb(i / span), 0.45)
                glow = math.exp(-(((i - pos) / self.PULSE_SIGMA) ** 2))
                r, g, b = blend_rgb(base, SHEEN_RGB, glow * 0.9)
                bar.append(fill_char, style=f"#{r:02x}{g:02x}{b:02x}")
            return bar

        filled = int(width * min(task.completed / task.total, 1.0)) if task.total else 0
        failed = task.finished and not task.fields.get("success", True)
        for i in range(width):
            if i >= filled:
                bar.append(track_char, style="dim")
                continue
            rgb = gradient_rgb(i / span)
            if failed:
                rgb = scale_rgb(blend_rgb(rgb, (248, 113, 113), 0.8), 0.85)
            elif i == filled - 1 and not task.finished:
                # Glowing head cell on the advancing edge
                rgb = blend_rgb(rgb, SHEEN_RGB, 0.6)
            bar.append(fill_char, style=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
        return bar


class PhaseAwareProgressColumn(TaskProgressColumn):
    """Task progress column that shows dim placeholder during indeterminate phase."""

    def render(self, task: RichTask) -> Text:
        # When total is None (indeterminate), show placeholder to maintain width
        if task.total is None:
            # Match width of "100%" (4 chars)
            return Text("  - ", style="dim")
        return super().render(task)


class SpeedColumn(ProgressColumn):
    """Shows download speed when available."""

    def render(self, task: RichTask) -> Text:
        speed = task.fields.get("speed", "")
        if speed:
            return Text(f"{speed:>10}", style="cyan")
        return Text(" " * 10, style="dim")


class ETAColumn(ProgressColumn):
    """Shows ETA when available with fixed width."""

    # Fixed width for ETA column (e.g., "ETA 10m30s" = 10 chars)
    ETA_WIDTH = 10

    def render(self, task: RichTask) -> Text:
        eta = task.fields.get("eta", "")
        if eta:
            text = f"ETA {eta}"
            # Pad or truncate to fixed width
            if len(text) < self.ETA_WIDTH:
                text = text + " " * (self.ETA_WIDTH - len(text))
            elif len(text) > self.ETA_WIDTH:
                text = text[: self.ETA_WIDTH]
            return Text(text, style="dim")
        return Text(" " * self.ETA_WIDTH, style="dim")



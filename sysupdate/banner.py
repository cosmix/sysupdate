"""Animated startup banner with a diagonal sheen reveal.

The wordmark is painted with a smooth truecolor gradient that runs
diagonally across the letterforms. On interactive terminals a bright
"sheen" band sweeps over the art at a visual 45 degrees, revealing the
glyphs as it passes; non-interactive consoles get the final frame
printed statically. Rich downgrades the truecolor styles automatically
on terminals with smaller palettes.
"""

import math
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text

RGB = tuple[int, int, int]

# Gradient stops applied along the diagonal (top-left -> bottom-right)
GRADIENT_STOPS: tuple[RGB, ...] = (
    (34, 211, 238),  # electric cyan
    (59, 130, 246),  # azure
    (139, 92, 246),  # violet
    (217, 70, 239),  # fuchsia
    (244, 114, 182),  # hot pink
)

# Sheen highlight (icy white) and footer text tint (pale slate)
SHEEN_RGB: RGB = (240, 251, 255)
TEXT_RGB: RGB = (226, 232, 240)

# Shared identity colors used across the UI
DEFAULT_ACCENT = "#8b5cf6"
INFO_STYLE = "#22d3ee"
SUCCESS_STYLE = "#4ade80"
WARNING_STYLE = "#fbbf24"
ERROR_STYLE = "#f87171"

# Terminal cells are roughly twice as tall as wide, so a slope of two
# columns per row reads as a 45-degree diagonal on screen.
ROW_SLANT = 2.0

# Sheen band width (gaussian sigma) and reveal ramp, in diagonal units
SHEEN_SIGMA = 5.0
REVEAL_SPAN = 7.0

# Luminance of unrevealed glyphs and of the shadow strokes
UNREVEALED_LUMA = 0.22
SHADOW_LUMA = 0.45

# How strongly the sheen whitens each character class
SHEEN_SOLID = 0.95
SHEEN_SHADOW = 0.55

# How far footer text is blended toward TEXT_RGB
TEXT_TINT = 0.7

ANIMATION_SECONDS = 1.15
FPS = 30
MARGIN = 2

# Box-drawing strokes that form the block logo's shadow/outline
SHADOW_CHARS = frozenset("╔╗╚╝║═")

# "sysupdate" in ANSI Shadow, for wide Unicode-capable terminals
BLOCK_LOGO = [
    "███████╗██╗   ██╗███████╗██╗   ██╗██████╗ ██████╗  █████╗ ████████╗███████╗",
    "██╔════╝╚██╗ ██╔╝██╔════╝██║   ██║██╔══██╗██╔══██╗██╔══██╗╚══██╔══╝██╔════╝",
    "███████╗ ╚████╔╝ ███████╗██║   ██║██████╔╝██║  ██║███████║   ██║   █████╗  ",
    "╚════██║  ╚██╔╝  ╚════██║██║   ██║██╔═══╝ ██║  ██║██╔══██║   ██║   ██╔══╝  ",
    "███████║   ██║   ███████║╚██████╔╝██║     ██████╔╝██║  ██║   ██║   ███████╗",
    "╚══════╝   ╚═╝   ╚══════╝ ╚═════╝ ╚═╝     ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝",
]

# Compact pure-ASCII fallback for narrow or non-Unicode terminals
FIGLET_LOGO = [
    "                               _       _       ",
    " ___ _   _ ___ _   _ _ __   __| | __ _| |_ ___ ",
    "/ __| | | / __| | | | '_ \\ / _` |/ _` | __/ _ \\",
    "\\__ \\ |_| \\__ \\ |_| | |_) | (_| | (_| | ||  __/",
    "|___/\\__, |___/\\__,_| .__/ \\__,_|\\__,_|\\__\\___|",
    "     |___/          |_|                        ",
]


def hex_to_rgb(value: str) -> RGB:
    """Parse a '#rrggbb' color string into an RGB tuple."""
    v = value.lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def blend_rgb(c1: RGB, c2: RGB, t: float) -> RGB:
    """Linearly interpolate between two RGB colors (t clamped to [0, 1])."""
    t = min(max(t, 0.0), 1.0)
    return (
        round(c1[0] + (c2[0] - c1[0]) * t),
        round(c1[1] + (c2[1] - c1[1]) * t),
        round(c1[2] + (c2[2] - c1[2]) * t),
    )


def scale_rgb(color: RGB, luma: float) -> RGB:
    """Scale a color toward black by a luminance factor."""
    return (round(color[0] * luma), round(color[1] * luma), round(color[2] * luma))


def gradient_rgb(t: float) -> RGB:
    """Sample the banner gradient at position t in [0, 1]."""
    t = min(max(t, 0.0), 1.0)
    segments = len(GRADIENT_STOPS) - 1
    x = t * segments
    i = min(int(x), segments - 1)
    return blend_rgb(GRADIENT_STOPS[i], GRADIENT_STOPS[i + 1], x - i)


def _smoothstep(t: float) -> float:
    """Hermite ease between 0 and 1 (t clamped to [0, 1])."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def sheen_intensity(delta: float) -> float:
    """Gaussian falloff of the sheen band at signed distance delta."""
    x = delta / SHEEN_SIGMA
    return math.exp(-x * x)


def _char_class(char: str, kind: str) -> str | None:
    """Classify a banner character: solid glyph, shadow stroke, or text."""
    if char == " ":
        return None
    if kind == "footer":
        return "shadow" if char in "─-" else "text"
    return "shadow" if char in SHADOW_CHARS else "solid"


def _cell_rgb(cls: str, diag: float, max_diag: float, sweep: float | None) -> RGB:
    """Color for one character cell at diagonal position diag.

    With sweep=None the cell shows its final gradient color; otherwise
    the color depends on where the sheen band (at diagonal position
    sweep) is relative to the cell: dark before it arrives, white-hot
    at the band, full gradient after it has passed.
    """
    base = gradient_rgb(diag / max_diag if max_diag else 0.0)
    if cls == "shadow":
        base = scale_rgb(base, SHADOW_LUMA)
    elif cls == "text":
        base = blend_rgb(base, TEXT_RGB, TEXT_TINT)
    if sweep is None:
        return base
    delta = sweep - diag
    revealed = blend_rgb(
        scale_rgb(base, UNREVEALED_LUMA), base, _smoothstep(delta / REVEAL_SPAN)
    )
    strength = SHEEN_SOLID if cls == "solid" else SHEEN_SHADOW
    return blend_rgb(revealed, SHEEN_RGB, sheen_intensity(delta) * strength)


def _footer_text(version: str, width: int, use_ascii: bool) -> str:
    """Build the hairline rule with the version centered inside it."""
    rule = "-" if use_ascii else "─"
    label = f" v{version} "
    if len(label) >= width:
        return label.strip()
    side = (width - len(label)) // 2
    return rule * side + label + rule * (width - side - len(label))


def banner_rows(
    logo: list[str], version: str, use_ascii: bool
) -> list[tuple[str, str]]:
    """Assemble (text, kind) rows: logo art, a gap, then the footer rule."""
    width = max(len(line) for line in logo)
    rows: list[tuple[str, str]] = [(line, "logo") for line in logo]
    rows.append(("", "logo"))
    rows.append((_footer_text(version, width, use_ascii), "footer"))
    return rows


def build_frame(rows: list[tuple[str, str]], sweep: float | None = None) -> Text:
    """Render one frame of the banner as styled Rich Text."""
    width = max(len(text) for text, _ in rows)
    max_diag = (width - 1) + (len(rows) - 1) * ROW_SLANT
    frame = Text(no_wrap=True)
    for row, (line, kind) in enumerate(rows):
        if row:
            frame.append("\n")
        if not line:
            continue
        frame.append(" " * MARGIN)
        for col, char in enumerate(line):
            cls = _char_class(char, kind)
            if cls is None:
                frame.append(char)
                continue
            r, g, b = _cell_rgb(cls, col + row * ROW_SLANT, max_diag, sweep)
            bold = "bold " if cls == "solid" else ""
            frame.append(char, style=f"{bold}#{r:02x}{g:02x}{b:02x}")
    return frame


def gradient_rule(width: int, use_ascii: bool, indent: int = 3) -> Text:
    """A dimmed gradient hairline, used as a section rule in the summary."""
    char = "-" if use_ascii else "─"
    rule = Text(" " * indent, no_wrap=True)
    span = max(width - 1, 1)
    for i in range(width):
        r, g, b = scale_rgb(gradient_rgb(i / span), 0.55)
        rule.append(char, style=f"#{r:02x}{g:02x}{b:02x}")
    return rule


def _select_logo(console_width: int, use_ascii: bool) -> list[str]:
    """Pick the block wordmark when it fits, the ASCII figlet otherwise."""
    if use_ascii or console_width < len(BLOCK_LOGO[0]) + MARGIN + 1:
        return FIGLET_LOGO
    return BLOCK_LOGO


def _animate(console: Console, rows: list[tuple[str, str]]) -> None:
    """Sweep the sheen band across the banner, then hold the final frame."""
    width = max(len(text) for text, _ in rows)
    max_diag = (width - 1) + (len(rows) - 1) * ROW_SLANT
    start = -3.0 * SHEEN_SIGMA
    end = max_diag + 3.0 * SHEEN_SIGMA + REVEAL_SPAN
    with Live(console=console, refresh_per_second=FPS, transient=False) as live:
        t0 = time.monotonic()
        while (elapsed := time.monotonic() - t0) < ANIMATION_SECONDS:
            frac = 1.0 - (1.0 - elapsed / ANIMATION_SECONDS) ** 3
            live.update(build_frame(rows, sweep=start + frac * (end - start)))
            time.sleep(1.0 / FPS)
        live.update(build_frame(rows))


# Segment of a sweepable line: (text, base color, extra style like "bold")
Segment = tuple[str, RGB, str]

# Sheen band sigma (cells) for single-line sweeps
LINE_SHEEN_SIGMA = 3.0


def _sweep_line_frame(
    segments: list[Segment], indent: int, sweep: float | None
) -> Text:
    """Render one frame of a sheen sweep across a single styled line."""
    line = Text(" " * indent, no_wrap=True)
    pos = 0
    for text, base, extra in segments:
        for char in text:
            rgb = base
            if sweep is not None:
                glow = math.exp(-(((pos - sweep) / LINE_SHEEN_SIGMA) ** 2))
                rgb = blend_rgb(base, SHEEN_RGB, glow * 0.9)
            style = f"{extra} #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}".strip()
            line.append(char, style=style)
            pos += 1
    return line


def sheen_sweep_line(
    console: Console,
    segments: list[Segment],
    indent: int = 3,
    animate: bool = True,
    duration: float = 0.55,
) -> None:
    """Print a styled line, sweeping a sheen across it on live terminals."""
    if not (animate and console.is_terminal):
        console.print(_sweep_line_frame(segments, indent, None))
        return
    total = sum(len(text) for text, _, _ in segments)
    start = -2.0 * LINE_SHEEN_SIGMA
    end = total + 2.0 * LINE_SHEEN_SIGMA
    with Live(console=console, refresh_per_second=FPS, transient=False) as live:
        t0 = time.monotonic()
        while (elapsed := time.monotonic() - t0) < duration:
            frac = 1.0 - (1.0 - elapsed / duration) ** 3
            live.update(
                _sweep_line_frame(segments, indent, start + frac * (end - start))
            )
            time.sleep(1.0 / FPS)
        live.update(_sweep_line_frame(segments, indent, None))


def show_banner(
    console: Console,
    version: str,
    dry_run: bool,
    use_ascii: bool,
    animate: bool = True,
) -> None:
    """Print the startup banner, animating the sheen on live terminals.

    Args:
        console: Rich Console instance for output.
        version: Application version string.
        dry_run: Whether dry-run mode is active.
        use_ascii: Whether to use ASCII fallback characters.
        animate: Whether animation is allowed (still requires a terminal).
    """
    logo = _select_logo(console.width, use_ascii)
    rows = banner_rows(logo, version, use_ascii)
    console.print()
    if animate and console.is_terminal:
        _animate(console, rows)
    else:
        console.print(build_frame(rows))
    if dry_run:
        dash = "--" if use_ascii else "—"
        console.print()
        console.print(
            f"   [bold {WARNING_STYLE}]DRY RUN[/] [dim]{dash} no changes will be made[/]"
        )
    console.print()

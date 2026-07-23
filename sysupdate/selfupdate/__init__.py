"""Self-update functionality for sysupdate."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

from .binary import (
    can_write_to_path,
    get_architecture,
    get_binary_path,
    get_expected_asset_name,
    replace_binary,
)
from .github import (
    GITHUB_API_BASE,
    REPO_NAME,
    REPO_OWNER,
    GitHubClient,
    Release,
    ReleaseAsset,
)
from .updater import SelfUpdater, UpdateCheckResult, UpdateResult

__all__ = [
    "GitHubClient",
    "Release",
    "ReleaseAsset",
    "GITHUB_API_BASE",
    "REPO_OWNER",
    "REPO_NAME",
    "get_architecture",
    "get_binary_path",
    "get_expected_asset_name",
    "can_write_to_path",
    "replace_binary",
    "SelfUpdater",
    "UpdateCheckResult",
    "UpdateResult",
    "run_self_update",
]


def _version_arrow(old: str, new: str, arrow: str, accent: str) -> Text:
    """Render 'vOLD → vNEW' with only the changed part of NEW highlighted."""
    from ..summary import version_diff_text

    line = Text()
    line.append(f"v{old}", style="dim")
    line.append(f" {arrow} ", style=accent)
    line.append("v", style="bold white")
    line.append_text(version_diff_text(old, new))
    return line


async def run_self_update(check_only: bool = False) -> int:
    """Run self-update process with Rich CLI output.

    Args:
        check_only: If True, only check for updates without installing

    Returns:
        Exit code: 0 for success, 1 for error
    """
    from sysupdate import __version__

    from ..banner import (
        DEFAULT_ACCENT,
        ERROR_STYLE,
        SUCCESS_STYLE,
        WARNING_STYLE,
        gradient_rule,
    )

    console = Console()
    use_ascii = "utf" not in (console.encoding or "").lower()
    sep = "|" if use_ascii else "·"
    arrow = "->" if use_ascii else "→"
    check = "+" if use_ascii else "✓"
    cross = "x" if use_ascii else "✗"
    up = "^" if use_ascii else "⬆"

    updater = SelfUpdater()

    console.print()
    console.print(gradient_rule(48, use_ascii, indent=2))
    console.print()
    console.print(f"  [bold]self-update[/] [dim]{sep} Checking for new releases[/]")
    console.print()

    try:
        check_result = await updater.check_for_update(__version__)
    except Exception as e:
        console.print(
            f"  [bold {ERROR_STYLE}]{cross} Update check failed[/] [dim]{sep}[/] {escape(str(e))}"
        )
        return 1

    if check_result.error_message:
        console.print(
            f"  [bold {ERROR_STYLE}]{cross}[/] {escape(check_result.error_message)}"
        )
        return 1

    if not check_result.update_available:
        console.print(
            f"  [bold {SUCCESS_STYLE}]{check}[/] Up to date"
            f" [dim]{sep} v{check_result.current_version} is the latest version[/]"
        )
        console.print()
        return 0

    latest = check_result.latest_version or ""
    console.print(f"  [bold {WARNING_STYLE}]{up} Update available[/]")
    version_line = Text("  ")
    version_line.append_text(
        _version_arrow(check_result.current_version, latest, arrow, DEFAULT_ACCENT)
    )
    console.print(version_line)
    console.print()

    # If check-only mode, stop here
    if check_only:
        console.print(
            "  [dim]Run[/] [bold]sysupdate self-update[/] [dim]to install the update[/]"
        )
        console.print()
        return 0

    # Guard against None release (should never happen due to update_available check)
    if check_result.release is None:
        console.print(
            f"  [bold {ERROR_STYLE}]{cross}[/] No release information available"
        )
        return 1

    # Perform update with progress bar
    from ..ui import GradientBarColumn

    with Progress(
        TextColumn("  "),
        SpinnerColumn(
            spinner_name="line" if use_ascii else "dots", style=DEFAULT_ACCENT
        ),
        TextColumn("{task.description}"),
        GradientBarColumn(bar_width=24, use_ascii=use_ascii),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("[dim]starting[/]".ljust(34), total=100)

        def progress_callback(message: str, percent: float) -> None:
            """Update progress bar with status and percentage."""
            desc = f"[dim]{message[:28]:<28}[/]"
            progress.update(task, completed=percent, description=desc)

        try:
            update_result = await updater.perform_update(
                current_version=check_result.current_version,
                release=check_result.release,
                progress_callback=progress_callback,
            )
        except Exception as e:
            console.print(
                f"\n  [bold {ERROR_STYLE}]{cross} Update failed[/] [dim]{sep}[/] {escape(str(e))}"
            )
            return 1

    # Display update results
    console.print()
    if update_result.success:
        done = Text("  ")
        done.append(f"{check} Updated ", style=f"bold {SUCCESS_STYLE}")
        done.append_text(
            _version_arrow(
                update_result.old_version,
                update_result.new_version,
                arrow,
                DEFAULT_ACCENT,
            )
        )
        console.print(done)
        console.print()
        console.print(gradient_rule(48, use_ascii, indent=2))
        console.print()
        return 0
    else:
        console.print(
            f"  [bold {ERROR_STYLE}]{cross} Update failed[/]"
            f" [dim]{sep}[/] {escape(update_result.error_message)}"
        )
        console.print()
        return 1

"""Self-update functionality for sysupdate."""

from __future__ import annotations

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from .binary import (
    can_write_to_path,
    get_architecture,
    get_binary_path,
    get_expected_asset_name,
    replace_binary,
)
from .github import GITHUB_API_BASE, REPO_NAME, REPO_OWNER, GitHubClient, Release, ReleaseAsset
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


async def run_self_update(check_only: bool = False) -> int:
    """Run self-update process with Rich CLI output.

    Args:
        check_only: If True, only check for updates without installing

    Returns:
        Exit code: 0 for success, 1 for error
    """
    from sysupdate import __version__

    console = Console()
    updater = SelfUpdater()

    # Check for updates
    console.print("\n[cyan]Checking for updates...[/cyan]")

    try:
        check_result = await updater.check_for_update(__version__)
    except Exception as e:
        console.print(f"[red]Error checking for updates:[/red] {e}")
        return 1

    if check_result.error_message:
        console.print(f"[red]Error:[/red] {check_result.error_message}")
        return 1

    # Display results
    console.print(f"[cyan]Current version:[/cyan] {check_result.current_version}")

    if check_result.latest_version:
        console.print(f"[cyan]Latest version:[/cyan] {check_result.latest_version}")

    if not check_result.update_available:
        console.print("[green]You are running the latest version![/green]")
        return 0

    console.print("[yellow]Update available![/yellow]")

    # If check-only mode, stop here
    if check_only:
        console.print("\n[cyan]Run without --check-only to install the update.[/cyan]")
        return 0

    # Perform update with progress bar
    console.print("\n[cyan]Installing update...[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Updating...", total=100)

        def progress_callback(message: str, percent: float) -> None:
            """Update progress bar with status and percentage."""
            progress.update(task, completed=percent, description=message)

        try:
            update_result = await updater.perform_update(
                current_version=check_result.current_version,
                release=check_result.release,
                progress_callback=progress_callback,
            )
        except Exception as e:
            console.print(f"\n[red]Error during update:[/red] {e}")
            return 1

    # Display update results
    if update_result.success:
        console.print(
            f"\n[green]Successfully updated from {update_result.old_version} "
            f"to {update_result.new_version}![/green]"
        )
        console.print("[cyan]Please restart sysupdate to use the new version.[/cyan]")
        return 0
    else:
        console.print(f"\n[red]Update failed:[/red] {update_result.error_message}")
        return 1

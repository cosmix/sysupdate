"""aria2 installation helper for parallel downloads."""

import asyncio
import shutil

from rich.console import Console
from rich.prompt import Confirm

from . import invalidate_cache


def _detect_install_command() -> list[str] | None:
    """Detect the system package manager and return the aria2 install command.

    Returns:
        Install command as a list of strings, or None if no supported
        package manager is found.
    """
    if shutil.which("apt"):
        return ["sudo", "apt", "install", "-y", "aria2"]
    if shutil.which("dnf"):
        return ["sudo", "dnf", "install", "-y", "aria2"]
    if shutil.which("pacman"):
        return ["sudo", "pacman", "-S", "--noconfirm", "aria2"]
    return None


def _install_hint() -> str:
    """Return a human-readable install hint based on the detected package manager."""
    if shutil.which("apt"):
        return "sudo apt install aria2"
    if shutil.which("dnf"):
        return "sudo dnf install aria2"
    if shutil.which("pacman"):
        return "sudo pacman -S aria2"
    return "your package manager"


async def prompt_install_aria2(console: Console) -> bool:
    """Display aria2 warning and offer to install it.

    Args:
        console: Rich Console instance for output

    Returns:
        True if aria2 is now available, False otherwise.
    """
    # Barber-pole border - yellow and dim (works on light and dark terminals)
    border = "".join(
        "[bold yellow]█[/]" if i % 2 == 0 else "[dim]░[/]" for i in range(48)
    )

    hint = _install_hint()

    console.print()
    console.print(f"  {border}")
    console.print()
    console.print("  [bold yellow]![/]  [bold]aria2c is not installed[/]")
    console.print("  [dim]Downloads will be sequential (slower)[/]")
    console.print()
    console.print("  aria2 enables parallel package downloads,")
    console.print("  significantly speeding up large updates.")
    console.print()
    console.print(f"  [dim]Install manually: {hint}[/]")
    console.print()
    console.print(f"  {border}")
    console.print()

    # Prompt user
    loop = asyncio.get_running_loop()
    install = await loop.run_in_executor(
        None,
        lambda: Confirm.ask(
            "  [yellow]I can install aria2 right now. It'll only take a few seconds.[/]",
            console=console,
            default=True,
        ),
    )

    if not install:
        console.print()
        console.print("  [dim]Continuing without aria2. Downloads will be slower.[/]")
        console.print()
        return False

    return await _install_aria2(console)


async def _install_aria2(console: Console) -> bool:
    """Install aria2 using the detected system package manager.

    Args:
        console: Rich Console instance for output

    Returns:
        True if installation succeeded, False otherwise.
    """
    cmd = _detect_install_command()
    if cmd is None:
        console.print()
        console.print("  [yellow]Could not detect a supported package manager.[/]")
        console.print("  [dim]Please install aria2 manually using your package manager.[/]")
        console.print()
        return False

    console.print()
    console.print("  [cyan]Installing aria2...[/]")
    console.print()

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        if process.stdout:
            async for line in process.stdout:
                decoded = line.decode().strip()
                if decoded:
                    console.print(f"  [dim]{decoded}[/]")

        returncode = await process.wait()

        if returncode == 0:
            invalidate_cache("aria2c")
            console.print()
            console.print("  [green]✓ aria2 installed successfully![/]")
            console.print("  [dim]Parallel downloads are now enabled.[/]")
            console.print()
            return True
        else:
            console.print()
            console.print("  [red]✗ Failed to install aria2.[/]")
            console.print(
                "  [dim]Continuing without aria2. Downloads will be slower![/]"
            )
            console.print()
            return False

    except Exception as e:
        console.print()
        console.print(f"  [red]✗ Installation error: {e}[/]")
        console.print("  [dim]Continuing without aria2. Downloads will be slower![/]")
        console.print()
        return False

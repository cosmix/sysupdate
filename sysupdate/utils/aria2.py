"""aria2 installation helper for parallel downloads."""

import asyncio
from rich.console import Console
from rich.prompt import Confirm


async def prompt_install_aria2(console: Console) -> bool:
    """Display aria2 warning and offer to install it.

    Args:
        console: Rich Console instance for output

    Returns:
        True if aria2 is now available, False otherwise.
    """
    # Barber-pole border - yellow and dim (works on light and dark terminals)
    border = "".join(
        "[bold yellow]█[/]" if i % 2 == 0 else "[dim]░[/]"
        for i in range(48)
    )

    # Yellow warning triangle
    triangle = [
        "              [bold yellow]▄[/]",
        "             [bold yellow]▟█▙[/]",
        "            [bold yellow]▟███▙[/]",
    ]

    console.print()
    console.print(f"  {border}")
    console.print()
    for line in triangle:
        console.print(line)
    console.print()
    console.print("  [bold]aria2c is not installed[/]")
    console.print("  [dim]Downloads will be sequential (slower)[/]")
    console.print()
    console.print("  aria2 enables parallel package downloads,")
    console.print("  significantly speeding up large updates.")
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
        console.print("  [dim]Continuing with standard apt. This will take longer![/]")
        console.print()
        return False

    return await _install_aria2(console)


async def _install_aria2(console: Console) -> bool:
    """Install aria2 using apt.

    Args:
        console: Rich Console instance for output

    Returns:
        True if installation succeeded, False otherwise.
    """
    console.print()
    console.print("  [cyan]Installing aria2...[/]")
    console.print()

    try:
        process = await asyncio.create_subprocess_exec(
            "sudo", "apt", "install", "-y", "aria2",
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
            console.print()
            console.print("  [green]✓ aria2 installed successfully![/]")
            console.print("  [dim]Parallel downloads are now enabled.[/]")
            console.print()
            return True
        else:
            console.print()
            console.print("  [red]✗ Failed to install aria2.[/]")
            console.print("  [dim]Continuing with standard apt. This will take longer![/]")
            console.print()
            return False

    except Exception as e:
        console.print()
        console.print(f"  [red]✗ Installation error: {e}[/]")
        console.print("  [dim]Continuing with standard apt. This will take longer![/]")
        console.print()
        return False

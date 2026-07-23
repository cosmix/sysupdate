"""Entry point for the System Update Manager."""

import argparse
import asyncio
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from . import __version__


def check_sudo() -> bool:
    """Prompt for sudo credentials before starting."""
    from rich.markup import escape

    from .banner import DEFAULT_ACCENT, ERROR_STYLE
    from .console import console

    utf = "utf" in (console.encoding or "").lower()
    diamond = "*" if not utf else "◆"
    dash = "--" if not utf else "—"

    console.print(
        f"\n[bold {DEFAULT_ACCENT}]{diamond}[/] [bold]sysupdate needs sudo[/]"
        f" [dim]{dash} enter your password if prompted[/]\n"
    )

    try:
        result = subprocess.run(
            ["sudo", "-v"],
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        console.print(f"[bold {ERROR_STYLE}]x[/] {escape(str(e))}")
        return False


@contextmanager
def _sudo_keepalive(interval: float = 60.0) -> Iterator[None]:
    """Refresh sudo's cached credentials in the background until the block exits.

    A full multi-manager upgrade can outlast sudo's ``timestamp_timeout``
    (as little as five minutes). Refreshing every ``interval`` seconds keeps
    the timestamp valid, so downstream ``sudo`` calls never block on a
    password prompt that the live progress display would otherwise hide.
    """
    stop = threading.Event()

    def refresh() -> None:
        while not stop.wait(interval):
            try:
                subprocess.run(
                    ["sudo", "-n", "-v"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                return

    thread = threading.Thread(target=refresh, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2.0)


def cmd_update(args: argparse.Namespace) -> int:
    """Run system updates (default command)."""
    # Dry runs make no changes, so they need no sudo credentials.
    if not args.dry_run and not check_sudo():
        from .banner import ERROR_STYLE
        from .console import console

        console.print(f"\n[bold {ERROR_STYLE}]sudo access failed[/] [dim]- exiting[/]")
        return 1

    from .app import SysUpdateCLI

    cli = SysUpdateCLI(
        verbose=args.verbose,
        dry_run=args.dry_run,
        no_animation=args.no_animation,
    )

    if args.dry_run:
        return cli.run()

    # Keep sudo's timestamp warm for the whole run so a long upgrade never
    # stalls on a re-prompt hidden beneath the live progress display.
    with _sudo_keepalive():
        return cli.run()


def cmd_self_update(args: argparse.Namespace) -> int:
    """Check for and install sysupdate updates."""
    from .selfupdate import run_self_update

    return asyncio.run(run_self_update(check_only=args.check_only))


def main() -> int:
    """Main entry point for sysupdate."""
    parser = argparse.ArgumentParser(
        prog="sysupdate",
        description="A beautiful CLI system update manager with multi-distro support (APT, DNF, Pacman, Flatpak, Snap).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed package information",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument(
        "--no-animation",
        action="store_true",
        default=bool(os.environ.get("SYSUPDATE_NO_ANIMATION")),
        help="Disable banner and summary animations"
        " (also via SYSUPDATE_NO_ANIMATION=1)",
    )

    # Add subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # self-update subcommand
    self_update_parser = subparsers.add_parser(
        "self-update",
        help="Check for and install sysupdate updates",
    )
    self_update_parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check for updates without installing",
    )

    args = parser.parse_args()

    # Handle subcommands or default behavior
    if args.command == "self-update":
        return cmd_self_update(args)
    else:
        # Default: run system updates
        return cmd_update(args)


if __name__ == "__main__":
    sys.exit(main())

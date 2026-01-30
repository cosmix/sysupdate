"""Entry point for the System Update Manager."""

import argparse
import asyncio
import subprocess
import sys

from . import __version__


def check_sudo() -> bool:
    """Prompt for sudo password before starting."""
    print()  # Blank line after command prompt
    print("sysupdate requires sudo access.")
    print("Please enter your password if prompted.\n")

    try:
        result = subprocess.run(
            ["sudo", "-v"],
            check=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False


def cmd_update(args: argparse.Namespace) -> int:
    """Run system updates (default command)."""
    # Get sudo credentials before starting
    if not args.dry_run:
        if not check_sudo():
            print("\nFailed to get sudo access. Exiting.")
            return 1

    from .app import SysUpdateCLI

    cli = SysUpdateCLI(verbose=args.verbose, dry_run=args.dry_run)
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
        "-v", "--verbose",
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

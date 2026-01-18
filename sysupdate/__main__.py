"""Entry point for the System Update Manager."""

import argparse
import subprocess
import sys

from . import __version__


def check_sudo() -> bool:
    """Prompt for sudo password before starting."""
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


def main() -> int:
    """Main entry point for sysupdate."""
    parser = argparse.ArgumentParser(
        prog="sysupdate",
        description="A beautiful, fast CLI system update manager for apt and flatpak.",
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

    args = parser.parse_args()

    # Get sudo credentials before starting
    if not args.dry_run:
        if not check_sudo():
            print("\nFailed to get sudo access. Exiting.")
            return 1

    from .app import SysUpdateCLI

    cli = SysUpdateCLI(verbose=args.verbose, dry_run=args.dry_run)
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())

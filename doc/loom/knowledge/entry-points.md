# Entry Points

> Key files agents should read first to understand the codebase.
> This file is append-only - agents add discoveries, never delete.

## CLI Entry Point

- `sysupdate/__main__.py:24-57` - `main()` function, the primary entry point
  - Parses CLI arguments (--verbose, --dry-run, --version)
  - Validates sudo access via `check_sudo()`
  - Instantiates `SysUpdateCLI` from `sysupdate/app.py`
  - Calls `cli.run()` to start the update process

- `pyproject.toml:33` - Package entry point definition
  - `sysupdate = "sysupdate.__main__:main"`
  - Enables running as `sysupdate` command after installation

## Application Core

- `sysupdate/app.py:41-444` - `SysUpdateCLI` class
  - Main application orchestrator
  - Manages concurrent APT and Flatpak updates
  - Uses Rich for terminal rendering (progress bars, tables)
  - Key method: `run()` at line 55 drives the update process

## Updaters

- `sysupdate/updaters/base.py` - Protocol and data structures
  - `UpdaterProtocol` defines the interface for all updaters
  - `Package`, `UpdateProgress`, `UpdateResult` data classes
  - `UpdatePhase` enum for tracking update stages

- `sysupdate/updaters/apt.py` - APT package manager updater
- `sysupdate/updaters/flatpak.py` - Flatpak application updater
- `sysupdate/updaters/aria2_downloader.py` - Parallel download support

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

## Adding New Updaters

1. Create module: sysupdate/updaters/snap.py
2. Export in **init**.py: add import and **all** entry
3. Wire in app.py: add instance, check_available, progress task, \_run_snap method
4. Add parser in utils/parsing.py if needed
5. Add tests in tests/test_updaters.py

## App.py Integration Points

- Line ~52-53: Add updater instance in **init**
- Line ~247-248: Check availability with check_available()
- Line ~274-292: Add progress task and coroutine
- Line ~314-368: Add \_run_snap() method (copy \_run_flatpak pattern)
- Line ~370-440: Update \_print_summary() for snap packages

## app.py Constructor & Initialization

SysUpdateCLI.__init__ (lines 48-55) instantiates 3 updaters: AptUpdater, FlatpakUpdater, SnapUpdater as instance variables. Creates Console for Rich output. Initializes logger via setup_logging(verbose).

## app.py Concurrent Orchestration

_run_updates() (lines 255-336): Checks all updaters available, creates Progress context. Builds coroutines conditionally. Uses asyncio.gather(*coroutines) to run all 3 updaters concurrently. task_mapping tracks result order. Casts results back to updater-specific Package lists.

## app.py Progress Widget Architecture

Progress context (lines 272-282): Combines TextColumn (indent), StatusColumn (spinner → ✓/✗), BarColumn (16-char bar), TaskProgressColumn. _create_progress_callback creates closure (lines 112-149) returning on_progress callback that updates descriptions based on UpdatePhase.

## app.py Result Display

_print_summary (lines 422-526): Creates 3 Rich Tables for APT/Flatpak/Snap packages. Each table shows name, old_version, arrow, new_version. Flatpak table shows app names + branches. Tables styled with dim headers, no borders, custom padding.

## DNF Updater Files

- sysupdate/updaters/dnf.py - DNF package manager implementation
- tests/test_dnf_updater.py - DNF updater tests
- sysupdate/utils/parsing.py - Contains parse_dnf_check_output() and DnfUpgradeProgressTracker

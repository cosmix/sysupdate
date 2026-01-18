# Architectural Patterns

> Discovered patterns in the codebase that help agents understand how things work.
> This file is append-only - agents add discoveries, never delete.

## Build System

- **Build backend**: hatchling (`pyproject.toml:36-37`)
- **Package management**: uv (lockfile: `uv.lock`)
- **Python version**: 3.11+ required (`pyproject.toml:10`)
- **Wheel targets**: Configured in `[tool.hatch.build.targets.wheel]`

## Async Concurrency Pattern

- Uses `asyncio` for concurrent APT and Flatpak updates
- `app.py:245-312` - `_run_updates()` orchestrates parallel execution
- `asyncio.gather()` runs APT and Flatpak updaters concurrently
- Progress callbacks provide real-time status updates

## Updater Protocol Pattern

- `sysupdate/updaters/base.py:99-127` - `UpdaterProtocol`
- All updaters implement three key methods:
  - `check_available()` - Verify package manager exists
  - `check_updates()` - List available updates
  - `run_update()` - Execute the update with progress callback
- Enables adding new updaters (e.g., snap) without changing app.py

## Terminal Rendering

- Uses Rich library for all terminal output
- `Progress` widget with custom `StatusColumn` for spinner/checkmark
- `Table` widgets for package summaries
- Styled text with markup like `[green]`, `[dim]`, `[bold]`

## Subprocess Management

- Async subprocess execution via `asyncio.create_subprocess_exec()`
- Stdout/stderr captured and parsed for progress info
- Proper cleanup and signal handling for keyboard interrupts

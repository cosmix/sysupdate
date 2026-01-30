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

## UpdaterProtocol Methods

Required methods for new updaters:
- name: str class attribute for display
- check_available() -> bool: use command_available('which', 'snap')
- check_updates() -> list[Package]: list pending updates
- run_update(callback, dry_run) -> UpdateResult: execute update

## Progress Callback Pattern

- Create UpdateProgress with phase and progress (0.0-1.0)
- Phases: IDLE → CHECKING → DOWNLOADING → INSTALLING → COMPLETE/ERROR
- Use create_scaled_callback() for sub-ranges (e.g., checking=0-10%, rest=10-100%)
- Report via callback(UpdateProgress(...))

## Subprocess Output Handling

- Read stdout char-by-char for real-time progress (see flatpak.py:184-212)
- Collect lines in list for final parsing
- Use UpdateLogger('name') to log all output
- Parse progress % with regex: re.search(r'(\d+)\s*%', line)

## Updater Protocol Implementation

All updaters (APT, Flatpak, Snap) implement UpdaterProtocol:
- async check_available() - Check tool availability via command_available()
- async check_updates() - List updates using subprocess without installing
- async run_update(callback, dry_run) - Execute update with progress reporting

Instance state in all updaters:
- _logger: UpdateLogger - Logs to /tmp/update_logs/
- _process: asyncio.subprocess.Process - Active subprocess reference

## Subprocess Handling Pattern

All updaters use asyncio.create_subprocess_exec() for non-blocking execution:
- Combined stderr to stdout with stderr=PIPE + STDOUT
- Read stdout line-by-line: while True: line = await stdout.readline()
- Decode with errors='replace' for binary/broken output
- Call await process.wait() for exit code (check returncode != 0)

## Progress Reporting Pattern

Updaters use ProgressCallback (Callable[[UpdateProgress], None]):
- create_scaled_callback() wraps callback to scale progress [0,1] -> [start,end]
- Phases to scale: CHECKING, DOWNLOADING, INSTALLING per updater
- Report with UpdateProgress(phase, progress, total_packages, completed, message)
- Scale APT: checking 0-10%, downloading 10-50%, installing 50-100%

## APT Parsing Pattern

Uses precompiled regex patterns in parsing.py:
- UNPACK_PATTERN: 'Unpacking pkg (new) over (old)' -> extracts old/new versions
- SETUP_PATTERN: 'Setting up pkg (version)' -> tracks installation
- GET_PATTERN: 'Get:N pkg' -> counts downloads
- AptUpgradeProgressTracker encapsulates state/logic for progress calculation
- Allocates: downloading 0-50%, installing 50-100% of total_packages

## Flatpak Parsing Pattern

Reads chunks (1024 bytes) instead of line-by-line due to carriage return output:
- Buffer handling: split on both \n and \r delimiters
- Extract snap name from: 'Downloading|Fetching snap.name'
- Detect completion: count 'done', 'installed', 'updated' keywords
- Filter skip patterns: Locale, Extension, Platform, GL., Sdk, Runtime
- Environment: FLATPAK_TTY_MODE=none disables interactive progress bar

## Snap Parsing Pattern

Also uses chunk reading (1024 bytes) with buffer management:
- Regex: 'snap.name (channel) version from Publisher refreshed' for completion
- Progress: '(snap.name) (percentage)%' pattern for download tracking
- Calls _get_current_versions() to fetch installed versions before update
- Compares snap list output before/after to populate old_version/new_version
- Skip patterns: snapd, core*, bare, gnome-*, gtk-common-themes

## Error Handling Pattern

All updaters follow consistent error handling:
- Exceptions caught in top-level run_update() block
- Search reversed output for first error line (E: or 'error' keyword)
- Return UpdateResult(success=False, error_message=...) on failure
- Report ERROR phase with message via callback
- finally block ensures _logger.close() always executes
- Distinguish: returncode != 0 vs exception thrown

## Dry Run Pattern

All updaters handle dry_run=True consistently:
- Call check_updates() to get list of available updates
- Report COMPLETE phase with progress=1.0
- Set total_packages and completed_packages to len(packages)
- Return UpdateResult(success=True, packages=packages)
- Skip actual subprocess execution
- Demonstrates feature without modifying system

## DNF Output Parsing

### check-update Format
Output format: `package.arch    version    repository`
- Exit code 100 = updates available
- Exit code 0 = no updates
- Skip metadata lines containing 'Last metadata expiration' or 'Metadata cache created'

### Upgrade Progress Detection
- 'Downloading Packages:' header → DOWNLOADING phase
- 'Installing:' or 'Upgrading:' → INSTALLING phase
- '(\d+)/(\d+):' pattern for individual package progress
- 'Complete!' for completion detection

## Rich Progress Bar Integration

Custom progress columns in app.py:
- StatusColumn (44-63): Phase-aware spinner with color mapping
- SpeedColumn (66-73): Right-aligned download speed (10 chars)
- ETAColumn (76-83): ETA display when available
- Custom task fields: phase, speed, eta, success

### Progress Column Configuration (app.py:249-261)

- TextColumn for spacing/description
- StatusColumn with dots spinner style
- BarColumn(bar_width=16, style=dim, complete_style=white)
- TaskProgressColumn for percentage display
- TimeElapsedColumn for elapsed time
- Custom SpeedColumn and ETAColumn appended

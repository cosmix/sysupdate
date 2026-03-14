# Architecture

> High-level component relationships, data flow, and module dependencies.
> This file is append-only - agents add discoveries, never delete.

(Add architecture diagrams and component relationships as you discover them)

## Directory Structure

```
CLAUDE.md
LICENSE
README.md
build-binary.sh
dist/
doc/
  loom/
    knowledge/
  plans/
pyproject.toml
pyrightconfig.json
restore_packages.sh
sysupdate/
  selfupdate/
  updaters/
  utils/
sysupdate-legacy.sh
test_downgrade.sh
tests/
uv.lock
```

## UpdaterProtocol Interface

Core abstraction in `sysupdate/updaters/base.py:99-127`.

### Protocol Methods

- `name: str` - Display name ('APT', 'Flatpak', 'Snap')
- `check_available() -> bool` - Is updater available on system?
- `check_updates() -> list[Package]` - List pending updates
- `run_update(callback, dry_run) -> UpdateResult` - Execute update

## Key Data Structures (base.py)

**Package** (lines 19-31):

- name, old_version, new_version, size, status
- status flow: pending → downloading → installing → complete/error

**UpdateProgress** (lines 34-44):

- phase (UpdatePhase enum), progress (0.0-1.0)
- total_packages, completed_packages, current_package, speed, eta, message

**UpdateResult** (lines 47-54):

- success (bool), packages (list[Package])
- error_message, start_time, end_time

**UpdatePhase** enum (lines 9-16):
IDLE → CHECKING → DOWNLOADING → INSTALLING → COMPLETE/ERROR

## Progress Scaling (create_scaled_callback, lines 61-96)

Maps progress [0,1] to [start,end] range for combining multiple updaters.

## DNF Package Manager Support

- Location: sysupdate/updaters/dnf.py
- Prefers dnf5 over dnf4 for better performance
- Auto-detects available DNF version via which command
- Runs concurrently with APT, Flatpak, and Snap updaters

## Updater Architecture (No Base Class)

Each updater (APT, DNF, Pacman, Flatpak, Snap) is a standalone class implementing
UpdaterProtocol (typing.Protocol). There is NO shared base class — ~200+ lines of
boilerplate duplicated across all 5 updaters:

- Logger/process init (~4 lines × 5)
- check_available with try/except (~5 lines × 5)
- check_updates error wrapper (~6 lines × 5)
- run_update scaffolding (~25 lines × 5)
- Buffer reading loop for \n/\r splitting (~20 lines × 4)
- \_get_current_versions helper (~15 lines × 3: DNF, Pacman, Snap)

Opportunity: Extract BaseUpdater class with common scaffolding, or at minimum
a shared buffer-reading utility and version-fetching helper.

## Concurrent Execution Model

app.py orchestrates updaters via asyncio.gather():

1. Instantiates all updaters in **init** (lines 160-166)
2. Checks availability concurrently: asyncio.gather(\*[check_available()])
3. Runs updates concurrently: asyncio.gather(\*coroutines, return_exceptions=True)
4. Each updater reports progress via ProgressCallback

## Subprocess Lifecycle — Gaps

- 15 subprocess creations, all via asyncio.create_subprocess_exec (no shell=True)
- All properly await process.wait() or process.communicate()
- NO explicit signal handling (SIGTERM/SIGINT)
- NO process.terminate()/kill() on exceptions or cancellation
- KeyboardInterrupt caught only at top level (app.py:179)
- Running subprocesses may orphan on Ctrl+C

## Self-Update Security Model

- SHA256 checksum verification of downloaded binaries (8KB chunks)
- Atomic binary replacement via shutil.move() / sudo mv
- Backup created before replacement, restored on failure
- GitHub API over HTTPS (implicit TLS)
- GAP: SHA256SUMS.txt not cryptographically signed (no GPG)
- GAP: No post-replacement verification (--version check)
- GAP: No GitHub API rate limit handling

## BaseUpdater Template Method Pattern (added by updater-refactor)

- `sysupdate/updaters/base.py:194-332` — `BaseUpdater` ABC
- All 5 updaters (APT, DNF, Pacman, Flatpak, Snap) extend `BaseUpdater`
- Subclasses implement: `name` (property), `check_available()`, `check_updates()`, `_do_upgrade(report)`
- `run_update()` is the template method — handles checking, dry-run, progress scaling, error handling, subprocess cleanup
- Subprocess cleanup: `finally` block calls `self._process.kill()` with `ProcessLookupError` guard
- `read_process_lines(stdout)` — shared async generator for chunked line reading with \n/\r handling

## UI Extraction (added by updater-refactor)

- `sysupdate/ui.py` — Rich terminal rendering extracted from app.py
- Contains: `StatusColumn`, `SpeedColumn`, `ETAColumn`, header/logo, summary table
- `sysupdate/app.py` — now only orchestration (294 lines), imports UI from ui.py

## Log Directory Change (added by security-utils-config)

- Root: `/var/log/sysupdate/`
- Non-root: `$XDG_STATE_HOME/sysupdate/logs/` or `~/.local/state/sysupdate/logs/`
- Old location `/tmp/update_logs/` is NO LONGER USED (except legacy bash script)
- Symlink protection: `os.O_NOFOLLOW` on file open, realpath validation on directory

## Self-Update Security Hardening (added by security-utils-config)

- Response size limits: `MAX_API_RESPONSE_BYTES` (2MB), `MAX_BINARY_DOWNLOAD_BYTES` (200MB), `MAX_CHECKSUM_FILE_BYTES` (100KB)
- PYAPP env var validation: filename must contain 'sysupdate', must be executable
- Atomic binary replacement via `os.replace()` (TOCTOU fix)
- Version comparison: `_is_newer_version()` with `_compare_dotted_versions()` fallback for non-PEP-440

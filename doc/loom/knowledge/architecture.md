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

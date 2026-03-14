# Concerns & Technical Debt

> Technical debt, warnings, issues, and improvements needed.
> This file is append-only - agents add discoveries, never delete.

(Add concerns as you discover them)

## Missing aiohttp Dependency

test_selfupdate.py imports aiohttp which is not in dependencies. Tests fail to collect when this module loads. Consider adding aiohttp to dev dependencies or removing selfupdate tests if feature is deprecated.

## File Size Violations (400-line limit per CLAUDE.md)

Source files over limit:

- sysupdate/app.py: 523 lines — progress columns + CLI + orchestration
- sysupdate/utils/parsing.py: 549 lines — 5 parser classes in one file
- sysupdate/updaters/apt.py: 473 lines — sequential + parallel paths
- sysupdate/updaters/dnf.py: 438 lines — long upgrade tracking method
- sysupdate/updaters/pacman.py: 431 lines — long upgrade tracking method

Test files over limit (less critical but notable):

- tests/test_selfupdate.py: 1070 lines
- tests/test_parsing.py: 648 lines
- tests/test_app.py: 514 lines
- tests/test_updaters.py: 512 lines

## Subprocess Cleanup Gap

No explicit process termination on exceptions or cancellation.
Running subprocesses may orphan when KeyboardInterrupt occurs.
Need: signal handlers, process.terminate()/kill() in exception paths.

## Code Duplication in Updaters

~200+ lines of near-identical boilerplate across 5 updaters.
No BaseUpdater class to share: logging init, check_available wrapper,
run_update scaffolding, buffer reading, version fetching.

## RESOLVED: File Size Violations (fixed by updater-refactor)

- app.py reduced from 523 → 294 lines (UI extracted to ui.py)
- parsing.py reduced from 549 → 136 lines (split into updater-specific files)
- All sysupdate/ files now under 400 lines

## RESOLVED: Code Duplication in Updaters (fixed by updater-refactor)

- BaseUpdater ABC eliminates ~200 lines of duplicated lifecycle code
- All 5 updaters now extend BaseUpdater

## RESOLVED: Subprocess Cleanup Gap (fixed by updater-refactor)

- BaseUpdater.run_update() has try/finally with self.\_process.kill()

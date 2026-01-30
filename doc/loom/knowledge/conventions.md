# Coding Conventions

> Discovered coding conventions in the codebase.
> This file is append-only - agents add discoveries, never delete.

## Version Management

Version is automatically derived from git tags using `hatch-vcs`:

- **Source of truth**: Git tags (e.g., `v2.1.0`)
- **Build config**: `pyproject.toml` - `dynamic = ["version"]` with `hatch-vcs` plugin
- **Generated file**: `sysupdate/_version.py` (created at build time, gitignored)
- **Runtime access**: `sysupdate/__init__.py` imports from `_version.py`

**Version formats**:
| Scenario | Example |
|----------|---------|
| Tagged commit | `2.1.0` |
| After tag (N commits) | `2.1.1.devN+g<hash>` |
| Dirty working tree | `2.1.1.devN+g<hash>.d<date>` |

**Release workflow**: Push a tag like `v2.1.0` → GitHub Actions builds with that version.

## Directory Structure

```
sysupdate/
├── __init__.py      # Package init with __version__
├── __main__.py      # CLI entry point
├── app.py           # Main application class
├── updaters/        # Package manager implementations
│   ├── __init__.py
│   ├── base.py      # Protocol and data structures
│   ├── apt.py       # APT updater
│   ├── flatpak.py   # Flatpak updater
│   └── aria2_downloader.py  # Parallel download support
└── utils/           # Shared utilities
    ├── __init__.py
    ├── logging.py   # Logging setup
    └── parsing.py   # Output parsing utilities
```

## File Naming

- Python files use `snake_case.py`
- Test files use `test_<module>.py` pattern
- Configuration: `pyproject.toml` (PEP 517/518)

## Code Style

- Type hints on all function signatures
- Dataclasses for structured data (`@dataclass`)
- Enums for state/phase tracking
- Protocol for interface definitions (structural typing)
- Docstrings on public functions and classes

## Testing

- Framework: pytest with pytest-asyncio
- Tests in `tests/` directory
- Async test mode: auto (`pyproject.toml:40`)
- Run with: `uv run pytest`

## Test Patterns for Updaters

- Use pytest.fixture for updater instance
- Mock asyncio.create_subprocess_exec for subprocess calls
- Test check_available: True when returncode=0, False otherwise
- Test check_updates: verify package parsing from mock output
- Test dry_run: verify no actual install, reaches COMPLETE phase

## Test Fixtures in conftest.py

- mock_subprocess: AsyncMock with returncode=0, stdout, wait, communicate
- Add sample output fixtures (e.g., snap_update_output, snap_no_updates_output)
- clear_availability_cache: autouse fixture to reset cache between tests

## Updater File Structure

Each updater module follows this structure:

1. Imports from base and utils
2. Skip patterns (frozenset for filtering)
3. Class with name attribute
4. **init** with \_logger and \_process
5. check_available, check_updates, run_update methods
6. Private \_run_X_update method for subprocess work

## Detected Conventions

- Tests in tests/ directory



## Testing File Structure

Test files follow pytest conventions:
- Location: tests/ directory at project root
- Naming: test_*.py (e.g., test_app.py, test_updaters.py)
- Organization: Tests grouped in classes by component (TestAptUpdater, TestFlatpakUpdater, etc.)
- Async Tests: @pytest.mark.asyncio decorator for async test functions
- Fixtures: Shared fixtures defined in conftest.py using @pytest.fixture decorator

## Fixture Patterns

Key fixtures in conftest.py:
- clear_availability_cache: autouse=True, clears cache before/after each test
- mock_subprocess: AsyncMock with returncode, stdout, wait, communicate attributes
- Output fixtures: apt_update_output, apt_upgrade_output, apt_no_updates_output, flatpak_update_output, snap_refresh_output (all @pytest.fixture, return sample text)
- Command availability cache: Tests clear _availability_cache to ensure test isolation

## Mocking Approach

Subprocess Mocking Pattern:
- Use unittest.mock.AsyncMock for subprocess objects
- Patch asyncio.create_subprocess_exec to return mock process
- Mock proc.returncode: 0 for success, non-zero for failure
- Mock proc.communicate() for capturing output (return tuple of bytes)
- Example: mock_exec.side_effect = [mock_update, mock_list] for sequential calls
- Use patch.object(updater, '_logger', MagicMock()) to silence logging in tests

## Async Testing Patterns

Async Test Conventions:
- Decorate async tests with @pytest.mark.asyncio
- Use pytest-asyncio for async fixture support
- Use AsyncMock from unittest.mock for async functions
- Progress tracking: Create list in test, pass callback to collect updates
- Example: progress_updates=[], callback=lambda p: progress_updates.append(p)
- Verify phase progression: any(p.phase == UpdatePhase.COMPLETE for p in progress_updates)

## Test Coverage Areas

Test Files:
- test_updaters.py: Updater tests (check_available, check_updates, dry_run mode)
- test_app.py: CLI tests (instantiation, run method, concurrent execution)
- test_parsing.py: Output parsing and progress trackers
- test_utils.py: Utility function tests (command_available, caching)
- test_selfupdate.py: Self-update module (checksums, architecture, GitHub client)

## Test Data and Sample Outputs

Fixture Outputs:
- apt_update_output: Hit/Get lines, package manager initialization
- apt_upgrade_output: Full dpkg output with versions (libssl3 3.0.11→3.0.13)
- flatpak_update_output: App list with tab-separated IDs, branches, status flags
- snap_refresh_list_output: Snap table format (Name, Version, Rev, Size, Publisher)
- Sample data used consistently across multiple test methods

## Error and Exception Testing

Error Handling Patterns:
- check_available exception handling: Catches Exception, returns False
- Network errors: Test with aiohttp.ClientError mocking
- Timeout handling: asyncio.TimeoutError testing
- HTTP errors: Mock response.status codes (404, 500)
- File not found: pytest.raises(FileNotFoundError) pattern
- RuntimeError for unsupported architecture: Verify exception message content

## Hardcoded Constants in app.py

Display Constants:
- DESC_WIDTH = 24 (line 91): Fixed description column width
- bar_width = 16 (line 253): Progress bar width
- logo_width = 50 (line 141): ASCII art centering width
- max_pkg_len = 12: Default max package name length

### Phase Style Mapping (PHASE_STYLES, lines 47-53)

- checking: dim, ○
- downloading: cyan, ↓
- installing: yellow, ⚙
- complete: green, ✓
- error: red, ✗

Header Gradient: cyan → dodger_blue2 → blue → purple → magenta

### Truncation Limits

- Message truncation in CHECKING phase: 15 chars (lines 205-206)
- Description total width: DESC_WIDTH (24 chars)
- Package name display: max_pkg_len per updater config
- Markup pattern: r'\[(green|red|dim|/)\]' for stripping Rich tags

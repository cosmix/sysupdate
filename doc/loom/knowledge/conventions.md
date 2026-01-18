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

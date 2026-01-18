# Coding Conventions

> Discovered coding conventions in the codebase.
> This file is append-only - agents add discoveries, never delete.

## Version Management

Version is defined in THREE locations (must be kept in sync):
1. `pyproject.toml:3` - `version = "2.0.0"` (source of truth for packaging)
2. `sysupdate/__init__.py:3` - `__version__ = "2.0.0"` (runtime import)
3. `sysupdate/__main__.py:38` - hardcoded in argparse `version` action

**Note**: For CI/CD release automation, consider using a single source of truth.

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

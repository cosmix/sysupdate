# System Update Manager

A beautiful, modern TUI for managing system updates on Ubuntu/Debian-based systems. Features concurrent APT and Flatpak updates with real-time progress, smooth animations, and a polished dark theme.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Concurrent Updates**: Updates APT packages and Flatpak applications simultaneously
- **Beautiful TUI**: Modern terminal interface built with Textual
- **Real-time Progress**: Live progress bars, package counts, and status updates
- **Smooth Animations**: Polished transitions and visual feedback
- **Dark Theme**: Tokyo Night-inspired color palette
- **Detailed Logging**: Timestamped logs for troubleshooting
- **Keyboard Navigation**: Full keyboard control with intuitive shortcuts

## Screenshots

```
╔═╗╦ ╦╔═╗╦ ╦╔═╗╔╦╗╔═╗╔╦╗╔═╗
╚═╗╚╦╝╚═╗║ ║╠═╝ ║║╠═╣ ║ ║╣
╚═╝ ╩ ╚═╝╚═╝╩  ═╩╝╩ ╩ ╩ ╚═╝
     System Update Manager v2.0

┌─ 📦 APT Packages ─────────────────────────────────┐
│  ████████████████████░░░░░░░░░  67%  47/70       │
│  Status: Installing linux-headers-6.8.0          │
│                                                   │
│  Recent:                                          │
│    ✓ libssl3          3.0.11 → 3.0.13            │
│    ✓ python3.11       3.11.6 → 3.11.8            │
│    ⟳ linux-headers    6.8.0-45 → 6.8.0-51        │
└───────────────────────────────────────────────────┘
┌─ 📱 Flatpak Apps ─────────────────────────────────┐
│  ████████████████████████████  100%  Complete!   │
│                                                   │
│  Updated 3 applications                           │
└───────────────────────────────────────────────────┘

 [Q] Quit   [L] Logs   [D] Details   [?] Help
```

## Installation

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/cosmix/sysupdate.git
cd sysupdate

# Install with uv
uv sync

# Run the application
uv run sysupdate
```

## Usage

```bash
# Run the update manager
sysupdate

# Enable verbose logging
sysupdate --verbose

# Dry run (show what would be updated)
sysupdate --dry-run

# Show version
sysupdate --version
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Q` | Quit application |
| `L` | Toggle log panel |
| `D` | Show package details |
| `?` | Show help |
| `Esc` | Close dialogs |

## Requirements

- Python 3.11 or higher
- Ubuntu/Debian-based Linux distribution
- `apt` package manager
- `flatpak` (optional, for Flatpak updates)
- `sudo` privileges for system updates

## Dependencies

- [Textual](https://textual.textualize.io/) - Modern TUI framework
- [Rich](https://rich.readthedocs.io/) - Beautiful terminal rendering

## Project Structure

```text
sysupdate/
├── __init__.py           # Package initialization
├── __main__.py           # CLI entry point
├── app.py                # Main Textual application
├── styles.tcss           # Textual CSS styling
├── widgets/              # Custom UI widgets
│   ├── header.py         # ASCII art header
│   ├── update_panel.py   # Progress panel
│   └── footer.py         # Keyboard shortcuts bar
├── updaters/             # Package manager backends
│   ├── base.py           # Protocol definitions
│   ├── apt.py            # APT updater
│   └── flatpak.py        # Flatpak updater
└── utils/                # Utility modules
    ├── logging.py        # Logging configuration
    └── parsing.py        # Output parsing
```

## Log Files

Update logs are saved to `/tmp/update_logs/` with timestamps:

- `sysupdate_YYYYMMDD_HHMMSS_main.log` - Main application log
- `sysupdate_YYYYMMDD_HHMMSS_apt.log` - APT update details
- `sysupdate_YYYYMMDD_HHMMSS_flatpak.log` - Flatpak update details

## Legacy Bash Script

The original bash script is still available as `sysupdate-legacy.sh` for systems without Python 3.11+:

```bash
./sysupdate-legacy.sh
```

## Testing Utilities

### `test_downgrade.sh`

Testing utility for simulating package downgrades - useful for testing the update manager.

```bash
# Dry run to see what would happen
./test_downgrade.sh --dry-run

# Downgrade 3 random packages
./test_downgrade.sh

# Downgrade 5 packages
./test_downgrade.sh --count 5
```

#### Options

- `--dry-run`: Show what would be done without actually doing it
- `--count N`: Number of packages to downgrade (default: 3)
- `--update`: Update package lists before checking
- `--skip-confirm`: Skip confirmation prompt
- `--help`: Show help message

## Development

```bash
# Install development dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run the app in development mode
uv run textual run --dev sysupdate.app:SysUpdateApp
```

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

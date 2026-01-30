# sysupdate

A fast, beautiful CLI for managing system updates on Linux. Runs package manager updates concurrently with real-time progress tracking.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Supported Package Managers

| Package Manager | Distribution                         |
| --------------- | ------------------------------------ |
| APT             | Debian, Ubuntu, Linux Mint, Pop!\_OS |
| DNF             | Fedora, RHEL, CentOS, Rocky Linux    |
| Pacman          | Arch Linux, Manjaro, EndeavourOS     |
| Flatpak         | All distributions                    |
| Snap            | All distributions                    |

## Features

- **Concurrent Updates**: All available package managers run in parallel
- **Multi-Distro Support**: Works on Debian, Fedora, Arch-based systems and more
- **Parallel Downloads**: Uses aria2c for faster APT package downloads (optional)
- **Real-time Progress**: Live progress bars with package names and speed
- **Self-Update**: Built-in command to update sysupdate itself from GitHub Releases
- **Minimal Output**: Clean, focused interface using Rich
- **Detailed Logging**: Timestamped logs saved for troubleshooting

## Installation

```bash
# Clone the repository
git clone https://github.com/cosmix/sysupdate.git
cd sysupdate

# Install with uv
uv sync

# Run
uv run sysupdate
```

### Optional: Parallel Downloads

Install aria2 for faster parallel package downloads:

```bash
sudo apt install aria2
```

## Usage

```bash
# Run updates
sysupdate

# Dry run (show what would be updated)
sysupdate --dry-run

# Verbose mode (detailed package info)
sysupdate --verbose

# Show version
sysupdate --version

# Check for sysupdate updates
sysupdate self-update --check-only

# Update sysupdate to latest version
sysupdate self-update
```

### Example Output

```text
                                 _       _
   ___ _   _ ___ _   _ _ __   __| | __ _| |_ ___
  / __| | | / __| | | | '_ \ / _` |/ _` | __/ _ \
  \__ \ |_| \__ \ |_| | |_) | (_| | (_| | ||  __/
  |___/\__, |___/\__,_| .__/ \__,_|\__,_|\__\___|
       |___/          |_|

  ✓ APT                     ━━━━━━━━━━━━━━━━ 100% 0:00:42
  ✓ Flatpak                 ━━━━━━━━━━━━━━━━ 100% 0:00:15
  ✓ Snap                    ━━━━━━━━━━━━━━━━ 100% 0:00:08

   ────────────────────────────────────────

   ✓ Updated 15 packages (10 APT, 2 Flatpak, 3 Snap)

   APT Packages (10)

   Package              Old             →   New
   libssl3              3.0.11              3.0.13
   openssl              3.0.11              3.0.13
   python3.11           3.11.6              3.11.8
   ... and 7 more
```

_On Fedora, APT is replaced with DNF. On Arch, it's replaced with Pacman._

## Requirements

- Python 3.11+
- Linux (Debian/Ubuntu, Fedora/RHEL, Arch, or derivatives)
- `sudo` privileges
- At least one supported package manager (APT, DNF, or Pacman)
- `flatpak` (optional)
- `snap` (optional)
- `aria2` (optional, for parallel APT downloads)

## Log Files

Logs are saved to `/tmp/update_logs/`:

```text
sysupdate_YYYYMMDD_HHMMSS_main.log
sysupdate_YYYYMMDD_HHMMSS_apt.log      # Debian/Ubuntu
sysupdate_YYYYMMDD_HHMMSS_dnf.log      # Fedora/RHEL
sysupdate_YYYYMMDD_HHMMSS_pacman.log   # Arch
sysupdate_YYYYMMDD_HHMMSS_flatpak.log
sysupdate_YYYYMMDD_HHMMSS_snap.log
```

## Testing

```bash
# Run tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Test with downgraded packages
./test_downgrade.sh --count 3
uv run sysupdate
```

### test_downgrade.sh

Utility to simulate package downgrades for testing:

```bash
./test_downgrade.sh --dry-run    # Preview
./test_downgrade.sh --count 5    # Downgrade 5 packages
./test_downgrade.sh              # Downgrade 3 packages (default)
```

## Legacy Script

The original bash script is available as `sysupdate-legacy.sh`:

```bash
./sysupdate-legacy.sh
```

## License

MIT - See [LICENSE](LICENSE)

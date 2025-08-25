# System Update Manager

A comprehensive bash script suite for managing system updates on Ubuntu/Debian-based systems with APT and Flatpak support.

- **Concurrent Updates**: Updates APT packages and Flatpak applications simultaneously
- **Modern inline TUI**: Clean, colored terminal interface with progress spinners
- **Detailed Logging**: Saves update logs with timestamps for troubleshooting
- **Package Testing**: Includes tools for testing update/downgrade scenarios
- **Smart Package Counting**: Accurately tracks number of updated packages

## Scripts

### `sysupdate.sh`

Main system update script that handles both APT and Flatpak updates concurrently.

#### Current Features

- Runs `apt update` and `apt full-upgrade` for system packages
- Updates all Flatpak applications
- Shows real-time progress with animated spinners
- Displays package counts for successful updates
- Creates timestamped logs in `/tmp/update_logs/`
- Graceful error handling with informative messages

#### Script Usage

```bash
./sysupdate.sh
```

The script will:

1. Request sudo privileges (needed for APT updates)
2. Run APT and Flatpak updates concurrently
3. Display progress and results
4. Save logs for review

### `test_downgrade.sh`

Testing utility for simulating package downgrades - useful for testing update scripts.

#### Test Features

- Randomly selects packages that can be downgraded (only apt for the time being!)
- Skips critical system packages to avoid breaking the system
- Creates automatic restore scripts
- Supports dry-run mode for safety
- Can hold packages at downgraded versions

#### How to use

```bash
# Downgrade 3 random packages (default)
./test_downgrade.sh

# Dry run to see what would happen
./test_downgrade.sh --dry-run

# Downgrade 5 packages
./test_downgrade.sh --count 5

# Update package lists first
./test_downgrade.sh --update

# Skip confirmation prompt
./test_downgrade.sh --skip-confirm
```

#### Options

- `--dry-run`: Show what would be done without actually doing it
- `--no-hold`: Don't hold packages after downgrading
- `--update`: Update package lists before checking
- `--count N`: Number of packages to downgrade (default: 3)
- `--no-deps`: Don't downgrade dependencies
- `--skip-confirm`: Skip confirmation prompt
- `--help`: Show help message

### `restore_packages.sh`

Auto-generated script created by `test_downgrade.sh` to restore downgraded packages.

#### Usage

```bash
./restore_packages.sh
```

This script will:

1. Unhold any held packages
2. Update package lists
3. Upgrade all packages to latest versions

## Requirements

- Ubuntu/Debian-based Linux distribution
- `apt` package manager
- `flatpak` (optional, for Flatpak updates)
- `sudo` privileges for system updates
- Bash 4.0 or higher

## Installation

1. Clone or download the scripts to your preferred location
2. Make the scripts executable:

```bash
chmod +x sysupdate.sh test_downgrade.sh
```

## Log Files

Update logs are saved to `/tmp/update_logs/` with timestamps:

- `system_update_YYYYMMDD_HHMMSS_apt.log` - APT update details
- `system_update_YYYYMMDD_HHMMSS_flatpak.log` - Flatpak update details

## Safety Notes

- The `test_downgrade.sh` script modifies system packages - use with caution
- Always use `--dry-run` first when testing the downgrade script
- The script avoids downgrading critical system packages like kernel, systemd, etc.
- A restore script is automatically created when packages are downgraded

## License

See LICENSE file for details.

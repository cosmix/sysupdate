#!/bin/bash

# Random Package Downgrade Script
# Use with caution - this modifies your system packages!

set -e # Exit on any error

# Configuration
NUM_PACKAGES=3      # Number of packages to randomly downgrade
DRY_RUN=false       # Set to true to see what would be done without actually doing it
HOLD_PACKAGES=false # Whether to hold packages after downgrading
DO_UPDATE=false     # Whether to run apt update before checking packages
SKIP_CONFIRM=true   # Whether to skip confirmation prompt
NO_DEPS=false       # Whether to prevent dependency downgrades

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root directly."
        print_info "It will use sudo when needed."
        exit 1
    fi
}

# Function to get installed packages that have multiple versions available
get_downgradable_packages() {
    print_info "Finding packages with multiple versions available..." >&2

    local downgradable=()
    local count=0
    local checked=0

    while read -r package; do
        if [[ -z "$package" ]]; then
            continue
        fi
        ((checked++)) || true

        # Skip essential/important packages and those that trigger initrd updates
        if [[ $package =~ ^(base-files|bash|coreutils|dpkg|libc6|systemd|kernel|linux-|ubuntu-|apt|sudo|initramfs-|dracut|plymouth|cryptsetup|grub|zfs-initramfs|nvidia-dkms).*$ ]]; then
            continue
        fi

        # Check if package has multiple versions by actually getting the versions
        local actual_versions=()
        local output
        output=$(apt list -a "$package" 2>/dev/null | grep -v "WARNING" | grep -v "^Listing" | grep -E "^$package/" | awk '{print $2}' | sort -u | head -5)
        if [[ -n "$output" ]]; then
            mapfile -t actual_versions <<<"$output"
        fi

        if [[ ${#actual_versions[@]} -gt 1 ]]; then
            downgradable+=("$package")
            ((count++)) || true

            # Limit search to avoid taking too long
            if [[ $count -ge 50 ]]; then
                break
            fi
        fi
    done < <(apt list --installed 2>/dev/null | grep -v "^Listing" | cut -d/ -f1)
    printf '%s\n' "${downgradable[@]}"
}

# Function to get available versions for a package
get_package_versions() {
    local package=$1
    apt list -a "$package" 2>/dev/null | grep -v "WARNING" | grep -v "^Listing" | grep -E "^$package/" | awk '{print $2}' | sort -u | head -5
}

# Function to get current version of a package
get_current_version() {
    local package=$1
    dpkg -l "$package" 2>/dev/null | tail -1 | awk '{print $3}'
}

# Function to downgrade a package
downgrade_package() {
    local package=$1
    local target_version=$2
    local current_version=$3

    print_info "Downgrading $package from $current_version to $target_version"

    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would execute: sudo apt install -y --allow-downgrades $package=$target_version"
        return 0
    fi

    # Attempt the downgrade with or without dependencies based on flag
    local apt_opts="--allow-downgrades"
    if [[ "$NO_DEPS" == "true" ]]; then
        apt_opts="$apt_opts --no-install-recommends"
    fi
    
    # shellcheck disable=SC2086
    if sudo apt install -y $apt_opts "$package=$target_version"; then
        print_success "Successfully downgraded $package to $target_version"

        # Hold the package if requested
        if [[ "$HOLD_PACKAGES" == "true" ]]; then
            sudo apt-mark hold "$package"
            print_info "Package $package is now held at version $target_version"
        fi

        return 0
    else
        print_error "Failed to downgrade $package"
        return 1
    fi
}

# Function to create restore script
create_restore_script() {
    local downgraded_packages=("$@")
    local restore_script="restore_packages.sh"

    cat >"$restore_script" <<'EOF'
#!/bin/bash
# Restore script for downgraded packages
# Generated automatically

set -e

echo "Restoring packages to latest versions..."

EOF

    for package in "${downgraded_packages[@]}"; do
        echo "sudo apt-mark unhold $package" >>"$restore_script"
        echo "echo \"Unholding $package...\"" >>"$restore_script"
    done

    echo "" >>"$restore_script"
    echo "sudo apt update" >>"$restore_script"
    echo "sudo apt upgrade -y" >>"$restore_script"
    echo "echo \"All packages restored!\"" >>"$restore_script"

    chmod +x "$restore_script"
    print_success "Created restore script: $restore_script"
}

# Main function
main() {
    print_info "Random Package Downgrade Script"
    print_warning "This script will modify your system packages!"

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
        --dry-run)
            DRY_RUN=true
            print_info "Dry run mode enabled"
            shift
            ;;
        --no-hold)
            HOLD_PACKAGES=false
            print_info "Packages will not be held after downgrade"
            shift
            ;;
        --update)
            DO_UPDATE=true
            print_info "Will update package lists before checking"
            shift
            ;;
        --count | -n)
            NUM_PACKAGES="$2"
            print_info "Will attempt to downgrade $NUM_PACKAGES packages"
            shift 2
            ;;
        --no-deps)
            NO_DEPS=true
            print_info "Dependencies will not be downgraded"
            shift
            ;;
        --skip-confirm | -y)
            SKIP_CONFIRM=true
            shift
            ;;
        --help | -h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --dry-run       Show what would be done without doing it"
            echo "  --no-hold       Don't hold packages after downgrading"
            echo "  --update        Update package lists before checking"
            echo "  --count N       Number of packages to downgrade (default: 3)"
            echo "  --no-deps       Don't downgrade dependencies"
            echo "  --skip-confirm  Skip confirmation prompt"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
        esac
    done

    check_root

    if [[ "$DRY_RUN" == "false" && "$SKIP_CONFIRM" == "false" ]]; then
        read -p "Continue with package downgrade? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Aborted by user"
            exit 0
        fi
    fi

    # Update package lists
    if [[ "$DO_UPDATE" == "true" ]]; then
        print_info "Updating package lists..."
        sudo apt update
    fi

    # Find downgradable packages
    local downgradable_packages=()
    mapfile -t downgradable_packages < <(get_downgradable_packages)

    if [[ ${#downgradable_packages[@]} -eq 0 ]]; then
        print_error "No suitable packages found for downgrading"
        exit 1
    fi

    print_info "Found ${#downgradable_packages[@]} packages that can be downgraded"

    # Randomly select packages
    local selected_packages=()
    local attempts=0
    local max_attempts=$((${#downgradable_packages[@]} * 2))

    while [[ ${#selected_packages[@]} -lt $NUM_PACKAGES && $attempts -lt $max_attempts ]]; do
        local random_index=$((RANDOM % ${#downgradable_packages[@]}))
        local package="${downgradable_packages[$random_index]}"

        # Check if package is already selected
        if [[ ! " ${selected_packages[*]} " =~ " ${package} " ]]; then
            selected_packages+=("$package")

        fi

        ((attempts++)) || true

    done

    if [[ ${#selected_packages[@]} -eq 0 ]]; then
        print_error "Could not select any packages for downgrading"
        exit 1
    fi

    print_info "Selected packages for downgrading:"
    printf '%s\n' "${selected_packages[@]}"
    echo

    # Downgrade selected packages
    local successfully_downgraded=()

    for package in "${selected_packages[@]}"; do
        print_info "Processing package: $package"

        local current_version
        current_version=$(get_current_version "$package")
        local versions=()
        mapfile -t versions < <(get_package_versions "$package")

        if [[ ${#versions[@]} -lt 2 ]]; then
            print_warning "Package $package has no older versions available"
            continue
        fi

        # Remove the current version from available versions and pick a random older one
        local older_versions=()
        for version in "${versions[@]}"; do
            if [[ "$version" != "$current_version" ]]; then
                # Ensure we are actually downgrading
                if dpkg --compare-versions "$version" "lt" "$current_version"; then
                    older_versions+=("$version")
                fi
            fi
        done

        if [[ ${#older_versions[@]} -eq 0 ]]; then
            print_warning "No older versions found for $package"
            continue
        fi

        # Pick a random older version
        local random_version_index=$((RANDOM % ${#older_versions[@]}))
        local target_version="${older_versions[$random_version_index]}"

        if downgrade_package "$package" "$target_version" "$current_version"; then
            successfully_downgraded+=("$package")
        fi

        echo
    done

    # Summary
    echo
    print_success "Downgrade operation completed!"
    print_info "Successfully downgraded ${#successfully_downgraded[@]} packages:"
    printf '%s\n' "${successfully_downgraded[@]}"

    if [[ ${#successfully_downgraded[@]} -gt 0 ]]; then
        create_restore_script "${successfully_downgraded[@]}"

        if [[ "$HOLD_PACKAGES" == "true" && "$DRY_RUN" == "false" ]]; then
            echo
            print_info "Packages are held at their downgraded versions."
            print_info "To restore them later, run: ./restore_packages.sh"
            print_info "Or manually: sudo apt-mark unhold <package> && sudo apt upgrade"
        fi
    fi
}

# Run the main function with all arguments
main "$@"

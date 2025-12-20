#!/bin/bash

# Package Downgrade Script for Testing sysupdate
# Downgrades APT packages and/or Flatpak apps so you can test the update functionality

set -e # Exit on any error

# Configuration
NUM_PACKAGES=3      # Number of packages to downgrade (per type)
DRY_RUN=false       # Set to true to see what would be done without actually doing it
DO_APT=true         # Whether to downgrade APT packages
DO_FLATPAK=true     # Whether to downgrade Flatpak apps
VERBOSE=false       # Show debug output for troubleshooting

# Safe packages to downgrade - common tools that won't break the system
# These are frequently updated and typically have multiple versions available
SAFE_PACKAGES=(
    "curl"
    "wget"
    "git"
    "vim"
    "nano"
    "htop"
    "tree"
    "jq"
    "tmux"
    "neofetch"
    "zip"
    "unzip"
    "rsync"
    "less"
    "file"
    "ncdu"
    "bat"
    "ripgrep"
    "fd-find"
    "fzf"
)

# Safe Flatpak apps to downgrade - common apps that are frequently updated
# These are popular desktop apps with regular updates
SAFE_FLATPAKS=(
    "org.mozilla.firefox"
    "org.mozilla.Thunderbird"
    "org.libreoffice.LibreOffice"
    "org.videolan.VLC"
    "org.gimp.GIMP"
    "org.inkscape.Inkscape"
    "org.audacityteam.Audacity"
    "org.gnome.Calculator"
    "org.gnome.TextEditor"
    "org.gnome.Evince"
    "org.gnome.eog"
    "org.gnome.Logs"
    "org.gnome.FileRoller"
    "org.gnome.font-viewer"
    "org.freedesktop.Platform"
    "org.kde.okular"
    "com.spotify.Client"
    "com.visualstudio.code"
    "org.telegram.desktop"
    "com.slack.Slack"
)

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
print_debug() { [[ "$VERBOSE" == "true" ]] && echo -e "${YELLOW}[DEBUG]${NC} $1"; return 0; }

# Function to check if a package is installed
is_installed() {
    local package=$1
    dpkg -l "$package" 2>/dev/null | grep -q "^ii"
}

# Function to get available versions for a package
get_package_versions() {
    local package=$1
    apt-cache madison "$package" 2>/dev/null | awk '{print $3}' | sort -Vu | head -5
}

# Function to get current version of a package
get_current_version() {
    local package=$1
    dpkg-query -W -f='${Version}' "$package" 2>/dev/null
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

    if sudo apt install -y --allow-downgrades "$package=$target_version"; then
        print_success "Successfully downgraded $package to $target_version"
        return 0
    else
        print_error "Failed to downgrade $package"
        return 1
    fi
}

# ============== Flatpak Functions ==============

# Function to check if flatpak is available
has_flatpak() {
    command -v flatpak &>/dev/null
}

# Function to check if a Flatpak app is installed
is_flatpak_installed() {
    local app_id=$1
    flatpak list --app --columns=application 2>/dev/null | grep -q "^${app_id}$"
}

# Function to get the remote for a Flatpak app
get_flatpak_remote() {
    local app_id=$1
    # Use tab as field separator since flatpak list uses tabs between columns
    flatpak list --app --columns=application,origin 2>/dev/null | awk -F'\t' -v app="$app_id" '$1 == app {print $2}'
}

# Function to get current commit of a Flatpak app
get_flatpak_current_commit() {
    local app_id=$1
    flatpak info "$app_id" 2>/dev/null | grep -i "^Commit:" | awk '{print $2}'
}

# Function to get commit history for a Flatpak app
# Returns older commits (skips current), most recent previous first
get_flatpak_commits() {
    local remote=$1
    local app_id=$2
    local raw_output
    raw_output=$(flatpak remote-info --log "$remote" "$app_id" 2>&1)

    if [[ "$VERBOSE" == "true" ]]; then
        echo "  Raw log output for $app_id:" >&2
        echo "$raw_output" | head -20 | sed 's/^/    /' >&2
    fi

    # Get commit history - "Commit:" lines may have leading whitespace
    # Skip the first commit (current version), return up to 5 older ones
    echo "$raw_output" | grep -i "Commit:" | awk '{print $2}' | tail -n +2 | head -5
}

# Function to downgrade a Flatpak app
downgrade_flatpak() {
    local app_id=$1
    local target_commit=$2
    local current_commit=$3

    print_info "Downgrading $app_id"
    print_info "  From: ${current_commit:0:12}..."
    print_info "  To:   ${target_commit:0:12}..."

    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would execute: sudo flatpak update -y --commit=$target_commit $app_id"
        return 0
    fi

    if sudo flatpak update -y --commit="$target_commit" "$app_id"; then
        print_success "Successfully downgraded $app_id"
        return 0
    else
        print_error "Failed to downgrade $app_id"
        return 1
    fi
}

# Function to process Flatpak downgrades
process_flatpak_downgrades() {
    if ! has_flatpak; then
        print_warning "Flatpak is not installed, skipping Flatpak downgrades"
        return 0
    fi

    print_info "=== Flatpak Downgrades ==="
    echo

    # Find installed Flatpak apps from our safe list
    local candidates=()
    print_info "Finding installed Flatpak apps from safe list..."
    for app in "${SAFE_FLATPAKS[@]}"; do
        if is_flatpak_installed "$app"; then
            candidates+=("$app")
        fi
    done

    if [[ ${#candidates[@]} -eq 0 ]]; then
        print_warning "No suitable Flatpak apps found from safe list"
        return 0
    fi

    print_info "Found ${#candidates[@]} installed Flatpak app(s) from safe list"

    # Shuffle and select apps
    local selected=()
    local shuffled=()
    mapfile -t shuffled < <(printf '%s\n' "${candidates[@]}" | shuf)

    for app in "${shuffled[@]}"; do
        if [[ ${#selected[@]} -ge $NUM_PACKAGES ]]; then
            break
        fi

        # Check if app has older commits available
        local remote
        remote=$(get_flatpak_remote "$app")
        print_debug "App: $app, Remote: '${remote:-<empty>}'"
        if [[ -z "$remote" ]]; then
            print_debug "  Skipping $app: no remote found"
            continue
        fi

        local commits=()
        mapfile -t commits < <(get_flatpak_commits "$remote" "$app")
        print_debug "  Older commits available: ${#commits[@]}"

        if [[ ${#commits[@]} -gt 0 ]]; then
            selected+=("$app")
        else
            print_debug "  Skipping $app: no older commits in history"
        fi
    done

    if [[ ${#selected[@]} -eq 0 ]]; then
        print_warning "No Flatpak apps with older commits available"
        if [[ "$VERBOSE" != "true" ]]; then
            print_info "Run with --verbose to see why apps were skipped"
        fi
        return 0
    fi

    print_info "Will downgrade Flatpak apps: ${selected[*]}"
    echo

    # Downgrade each app
    local downgraded=()
    for app in "${selected[@]}"; do
        local remote
        remote=$(get_flatpak_remote "$app")
        local current_commit
        current_commit=$(get_flatpak_current_commit "$app")
        local commits=()
        mapfile -t commits < <(get_flatpak_commits "$remote" "$app")

        if [[ ${#commits[@]} -eq 0 ]]; then
            print_warning "No older commits for $app"
            continue
        fi

        # Use the first older commit (most recent previous version)
        local target_commit="${commits[0]}"

        if downgrade_flatpak "$app" "$target_commit" "$current_commit"; then
            downgraded+=("$app")
        fi
        echo
    done

    # Summary
    if [[ ${#downgraded[@]} -gt 0 ]]; then
        print_success "Downgraded ${#downgraded[@]} Flatpak app(s): ${downgraded[*]}"
    else
        print_warning "No Flatpak apps were downgraded"
    fi
}

# Main function
main() {
    print_info "Package Downgrade Script for Testing"

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -n | --count)
            NUM_PACKAGES="$2"
            shift 2
            ;;
        --apt-only)
            DO_APT=true
            DO_FLATPAK=false
            shift
            ;;
        --flatpak-only)
            DO_APT=false
            DO_FLATPAK=true
            shift
            ;;
        -v | --verbose)
            VERBOSE=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 [OPTIONS] [PACKAGES...]"
            echo ""
            echo "Downgrades APT packages and/or Flatpak apps so you can test sysupdate."
            echo ""
            echo "Options:"
            echo "  --dry-run        Show what would be done without doing it"
            echo "  -n, --count N    Number of packages to downgrade per type (default: 3)"
            echo "  --apt-only       Only downgrade APT packages"
            echo "  --flatpak-only   Only downgrade Flatpak apps"
            echo "  -v, --verbose    Show debug output for troubleshooting"
            echo "  -h, --help       Show this help message"
            echo ""
            echo "If PACKAGES are specified, those APT packages will be downgraded."
            echo "Otherwise, random packages from safe lists will be chosen."
            echo ""
            echo "By default, both APT and Flatpak downgrades are performed."
            exit 0
            ;;
        -*)
            print_error "Unknown option: $1"
            exit 1
            ;;
        *)
            # Positional arguments are package names
            SPECIFIED_PACKAGES+=("$1")
            shift
            ;;
        esac
    done

    if [[ $EUID -eq 0 ]]; then
        print_error "Don't run as root. The script will use sudo when needed."
        exit 1
    fi

    # Process APT downgrades
    if [[ "$DO_APT" == "true" ]]; then
        process_apt_downgrades
        echo
    fi

    # Process Flatpak downgrades
    if [[ "$DO_FLATPAK" == "true" ]]; then
        process_flatpak_downgrades
        echo
    fi

    # Final summary
    echo
    print_info "=== Done ==="
    print_info "Run 'uv run sysupdate' to update everything back"
}

# Function to process APT downgrades
process_apt_downgrades() {
    print_info "=== APT Package Downgrades ==="
    echo

    # Determine which packages to try
    local candidates=()
    if [[ ${#SPECIFIED_PACKAGES[@]} -gt 0 ]]; then
        candidates=("${SPECIFIED_PACKAGES[@]}")
        print_info "Using specified packages: ${candidates[*]}"
    else
        # Find installed packages from our safe list
        print_info "Finding installed APT packages from safe list..."
        for pkg in "${SAFE_PACKAGES[@]}"; do
            if is_installed "$pkg"; then
                candidates+=("$pkg")
            fi
        done
    fi

    if [[ ${#candidates[@]} -eq 0 ]]; then
        print_warning "No suitable APT packages found"
        return 0
    fi

    # Shuffle and select packages
    local selected=()
    local shuffled=()
    mapfile -t shuffled < <(printf '%s\n' "${candidates[@]}" | shuf)

    for pkg in "${shuffled[@]}"; do
        if [[ ${#selected[@]} -ge $NUM_PACKAGES ]]; then
            break
        fi

        # Check if package has an older version available
        local current_version
        current_version=$(get_current_version "$pkg")
        local versions=()
        mapfile -t versions < <(get_package_versions "$pkg")

        for ver in "${versions[@]}"; do
            if [[ "$ver" != "$current_version" ]] && dpkg --compare-versions "$ver" lt "$current_version" 2>/dev/null; then
                selected+=("$pkg")
                break
            fi
        done
    done

    if [[ ${#selected[@]} -eq 0 ]]; then
        print_warning "No APT packages with older versions available"
        return 0
    fi

    print_info "Will downgrade APT packages: ${selected[*]}"
    echo

    # Collect all package=version pairs for batch downgrade
    local pkg_specs=()
    local pkg_names=()
    for pkg in "${selected[@]}"; do
        local current_version
        current_version=$(get_current_version "$pkg")
        local versions=()
        mapfile -t versions < <(get_package_versions "$pkg")

        # Find the first older version
        local target_version=""
        for ver in "${versions[@]}"; do
            if [[ "$ver" != "$current_version" ]] && dpkg --compare-versions "$ver" lt "$current_version" 2>/dev/null; then
                target_version="$ver"
                break
            fi
        done

        if [[ -z "$target_version" ]]; then
            print_warning "No older version for $pkg"
            continue
        fi

        print_info "Will downgrade $pkg: $current_version → $target_version"
        pkg_specs+=("${pkg}=${target_version}")
        pkg_names+=("$pkg")
    done

    if [[ ${#pkg_specs[@]} -eq 0 ]]; then
        print_warning "No APT packages with valid downgrade targets"
        return 0
    fi

    echo
    print_info "Downgrading ${#pkg_specs[@]} package(s) in a single operation..."

    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would execute: sudo apt install -y --allow-downgrades ${pkg_specs[*]}"
        return 0
    fi

    # Try batch downgrade first
    if sudo apt install -y --allow-downgrades "${pkg_specs[@]}" 2>/dev/null; then
        print_success "Successfully downgraded ${#pkg_names[@]} APT package(s): ${pkg_names[*]}"
        return 0
    fi

    # Batch failed (likely due to dependency conflicts), fall back to individual downgrades
    print_warning "Batch downgrade failed due to dependency conflicts, trying individually..."
    echo

    local downgraded=()
    local failed=()
    for i in "${!pkg_specs[@]}"; do
        local spec="${pkg_specs[$i]}"
        local name="${pkg_names[$i]}"
        print_info "Attempting to downgrade $name..."
        if sudo apt install -y --allow-downgrades "$spec" 2>/dev/null; then
            print_success "Downgraded $name"
            downgraded+=("$name")
        else
            print_warning "Skipped $name (dependency conflict)"
            failed+=("$name")
        fi
    done

    echo
    if [[ ${#downgraded[@]} -gt 0 ]]; then
        print_success "Downgraded ${#downgraded[@]} package(s): ${downgraded[*]}"
    fi
    if [[ ${#failed[@]} -gt 0 ]]; then
        print_warning "Skipped ${#failed[@]} package(s) due to conflicts: ${failed[*]}"
    fi
}

# Initialize array for specified packages
SPECIFIED_PACKAGES=()

# Run the main function with all arguments
main "$@"

#!/bin/bash

# --- Configuration ---
# Define log file directory and base name
LOG_DIR="/tmp/update_logs"
LOG_BASE_NAME="system_update_$(date +%Y%m%d_%H%M%S)"

# Full paths for individual logs
APT_LOG="${LOG_DIR}/${LOG_BASE_NAME}_apt.log"
FLATPAK_LOG="${LOG_DIR}/${LOG_BASE_NAME}_flatpak.log"

# Create the log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# --- Utility Functions ---

# Function to show status with spinner
show_status() {
    local task_name="$1"
    local status_file="$2"
    local max_len="$3"
    local delay=0.2
    local spinstr="|/-\\"

    # Use default max_len if not provided
    if [ -z "$max_len" ]; then
        max_len=${#task_name}
    fi

    while [ ! -f "$status_file" ]; do
        for ((i = 0; i < ${#spinstr}; i++)); do
            printf "\r%-*s %c" "$max_len" "$task_name" "${spinstr:$i:1}"
            sleep "$delay"
            # Check again in case task finished during spinner rotation
            [ -f "$status_file" ] && break 2
        done
    done

    # Task finished, show final status
    local exit_code
    exit_code=$(cat "$status_file" 2>/dev/null)

    # Handle empty or invalid exit code
    if [[ -z "$exit_code" || ! "$exit_code" =~ ^[0-9]+$ ]]; then
        exit_code="1"
    fi

    if [ "$exit_code" -eq 0 ]; then
        printf "\r%-*s ✅ SUCCESS\n" "$max_len" "$task_name"
    else
        printf "\r%-*s ❌ FAILED (Exit Code: %s)\n" "$max_len" "$task_name" "$exit_code"
    fi
}

# Function to manage both status displays concurrently
manage_status_displays() {
    local apt_task="$1"
    local apt_status_file="$2"
    local flatpak_task="$3"
    local flatpak_status_file="$4"

    local delay=0.2
    local spinstr="|/-\\"
    local apt_finished=false
    local flatpak_finished=false
    
    # Calculate the maximum task name length for alignment
    local apt_len=${#apt_task}
    local flatpak_len=${#flatpak_task}
    local max_len=$apt_len
    if [ $flatpak_len -gt $max_len ]; then
        max_len=$flatpak_len
    fi

    # Reserve space for both lines without printing anything yet
    printf "\n\n"

    while [ "$apt_finished" = false ] || [ "$flatpak_finished" = false ]; do
        for ((i = 0; i < ${#spinstr}; i++)); do
            # Save cursor position and move to beginning of first line
            printf "\033[s\033[2A\r"

            # Update APT line
            if [ "$apt_finished" = false ]; then
                if [ -f "$apt_status_file" ]; then
                    local apt_exit_code
                    apt_exit_code=$(cat "$apt_status_file" 2>/dev/null)
                    if [[ -z "$apt_exit_code" || ! "$apt_exit_code" =~ ^[0-9]+$ ]]; then
                        apt_exit_code="1"
                    fi

                    printf "\033[K" # Clear current line
                    if [ "$apt_exit_code" -eq 0 ]; then
                        printf "%-*s ✅ SUCCESS" "$max_len" "$apt_task"
                    else
                        printf "%-*s ❌ FAILED (Exit Code: %s)" "$max_len" "$apt_task" "$apt_exit_code"
                    fi
                    apt_finished=true
                else
                    printf "\033[K%-*s %c" "$max_len" "$apt_task" "${spinstr:$i:1}" # Clear line, show spinner
                fi
            else
                # APT finished, just preserve the line
                local apt_exit=$(cat "$apt_status_file" 2>/dev/null || echo "1")
                printf "\033[K"
                if [ "$apt_exit" -eq 0 ]; then
                    printf "%-*s ✅ SUCCESS" "$max_len" "$apt_task"
                else
                    printf "%-*s ❌ FAILED (Exit Code: %s)" "$max_len" "$apt_task" "$apt_exit"
                fi
            fi

            # Move to second line
            printf "\n\r"

            # Update Flatpak line
            if [ "$flatpak_finished" = false ]; then
                if [ -f "$flatpak_status_file" ]; then
                    local flatpak_exit_code
                    flatpak_exit_code=$(cat "$flatpak_status_file" 2>/dev/null)
                    if [[ -z "$flatpak_exit_code" || ! "$flatpak_exit_code" =~ ^[0-9]+$ ]]; then
                        flatpak_exit_code="1"
                    fi

                    printf "\033[K" # Clear current line
                    if [ "$flatpak_exit_code" -eq 0 ]; then
                        printf "%-*s ✅ SUCCESS" "$max_len" "$flatpak_task"
                    else
                        printf "%-*s ❌ FAILED (Exit Code: %s)" "$max_len" "$flatpak_task" "$flatpak_exit_code"
                    fi
                    flatpak_finished=true
                else
                    printf "\033[K%-*s %c" "$max_len" "$flatpak_task" "${spinstr:$i:1}" # Clear line, show spinner
                fi
            else
                # Flatpak finished, just preserve the line
                local flatpak_exit=$(cat "$flatpak_status_file" 2>/dev/null || echo "1")
                printf "\033[K"
                if [ "$flatpak_exit" -eq 0 ]; then
                    printf "%-*s ✅ SUCCESS" "$max_len" "$flatpak_task"
                else
                    printf "%-*s ❌ FAILED (Exit Code: %s)" "$max_len" "$flatpak_task" "$flatpak_exit"
                fi
            fi

            # Restore cursor position
            printf "\033[u"

            sleep "$delay"

            # Break early if both finished
            [ "$apt_finished" = true ] && [ "$flatpak_finished" = true ] && break 2
        done
    done
}

# --- Task Functions (truly silent) ---

# Function to handle apt updates and upgrades (runs in background)
run_apt_updates_background() {
    local status_file="$1"
    local exit_code=0

    {
        sudo apt update && sudo apt full-upgrade -y
    } >"$APT_LOG" 2>&1
    exit_code=$?

    # Write the exit code to the status file when truly finished
    echo "$exit_code" >"$status_file"
}

# Function to handle flatpak updates (runs in background)
run_flatpak_updates_background() {
    local status_file="$1"
    local exit_code=0

    flatpak update -y >"$FLATPAK_LOG" 2>&1
    exit_code=$?

    # Write the exit code to the status file when truly finished
    echo "$exit_code" >"$status_file"
}

# --- Script Execution ---

# --- Prettier Header ---
# Define colors and styles for better output
BOLD=$(tput bold)
BLUE=$(tput setaf 4)
NC=$(tput sgr0) # No Color

# Print a formatted header
echo
printf "${BLUE}┌───────────────────────────────────────────────────────────┐${NC}\n"
printf "${BLUE}│${NC} ${BOLD}%-61s ${BLUE}│${NC}\n" "⤴️ Updating your system software..."
printf "${BLUE}└───────────────────────────────────────────────────────────┘${NC}\n"
echo 

# Request sudo password upfront
echo "🔑 Please enter your sudo password to allow system updates:"
if ! sudo -v; then
    echo "❌ [ERROR] Failed to obtain sudo privileges. Exiting."
    exit 1
fi
echo "✅ Sudo privileges obtained. Proceeding with updates..."
echo

# Create temporary status files
APT_STATUS_FILE=$(mktemp)
FLATPAK_STATUS_FILE=$(mktemp)

# Ensure status files are empty before starting
rm -f "$APT_STATUS_FILE" "$FLATPAK_STATUS_FILE"

# Start both background tasks
run_apt_updates_background "$APT_STATUS_FILE" &
APT_PID=$!
run_flatpak_updates_background "$FLATPAK_STATUS_FILE" &
FLATPAK_PID=$!

# Show concurrent status displays
manage_status_displays "Updating APT packages..." "$APT_STATUS_FILE" "Updating Flatpak applications..." "$FLATPAK_STATUS_FILE"

# Wait for all background tasks to complete
wait $APT_PID
wait $FLATPAK_PID

# Read exit codes from status files
APT_EXIT_CODE=$(cat "$APT_STATUS_FILE" 2>/dev/null)
FLATPAK_EXIT_CODE=$(cat "$FLATPAK_STATUS_FILE" 2>/dev/null)

# Handle empty or invalid exit codes
if [[ -z "$APT_EXIT_CODE" || ! "$APT_EXIT_CODE" =~ ^[0-9]+$ ]]; then
    APT_EXIT_CODE="1"
fi

if [[ -z "$FLATPAK_EXIT_CODE" || ! "$FLATPAK_EXIT_CODE" =~ ^[0-9]+$ ]]; then
    FLATPAK_EXIT_CODE="1"
fi

# Clean up temp files
rm -f "$APT_STATUS_FILE" "$FLATPAK_STATUS_FILE"

echo
echo "✅ All updates completed. Logs available at:"
echo "  - $APT_LOG"
echo "  - $FLATPAK_LOG"

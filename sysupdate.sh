#!/bin/bash

# System Update Manager

# --- Configuration ---
LOG_DIR="/tmp/update_logs"
LOG_BASE_NAME="system_update_$(date +%Y%m%d_%H%M%S)"
APT_LOG="${LOG_DIR}/${LOG_BASE_NAME}_apt.log"
FLATPAK_LOG="${LOG_DIR}/${LOG_BASE_NAME}_flatpak.log"

mkdir -p "$LOG_DIR"

# --- Color Definitions ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# --- Enhanced Spinner Frames ---
SPIN_FRAMES=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")

# --- Utility Functions ---

# Function to show status with enhanced spinner
show_status() {
    local task_name="$1"
    local status_file="$2"
    local max_len="$3"
    local delay=0.1
    local spin_index=0
    
    # Use default max_len if not provided
    if [ -z "$max_len" ]; then
        max_len=${#task_name}
    fi

    while [ ! -f "$status_file" ]; do
        printf "\r${CYAN}%s${NC} %-*s" "${SPIN_FRAMES[$spin_index]}" "$max_len" "$task_name"
        spin_index=$(( (spin_index + 1) % ${#SPIN_FRAMES[@]} ))
        sleep "$delay"
    done

    # Task finished, show final status
    local exit_code
    exit_code=$(cat "$status_file" 2>/dev/null)

    # Handle empty or invalid exit code
    if [[ -z "$exit_code" || ! "$exit_code" =~ ^[0-9]+$ ]]; then
        exit_code="1"
    fi

    if [ "$exit_code" -eq 0 ]; then
        printf "\r${GREEN}✅${NC} %-*s ${GREEN}SUCCESS${NC}\n" "$max_len" "$task_name"
    else
        printf "\r${RED}❌${NC} %-*s ${RED}FAILED (Exit Code: %s)${NC}\n" "$max_len" "$task_name" "$exit_code"
    fi
}

# Function to manage both status displays concurrently with colors
manage_status_displays() {
    local apt_task="$1"
    local apt_status_file="$2"
    local apt_count_file="$3"
    local apt_error_file="$4"
    local flatpak_task="$5"
    local flatpak_status_file="$6"
    local flatpak_count_file="$7"
    local flatpak_error_file="$8"

    local delay=0.1
    local apt_finished=false
    local flatpak_finished=false
    local spin_index=0

    # Calculate the maximum task name length for alignment
    local apt_len=${#apt_task}
    local flatpak_len=${#flatpak_task}
    local max_len=$apt_len
    if [ "$flatpak_len" -gt "$max_len" ]; then
        max_len=$flatpak_len
    fi

    # Start display - write two lines that we'll keep updating
    printf "${CYAN}%s${NC}  ${BOLD}%-*s${NC}\n" "${SPIN_FRAMES[0]}" "$max_len" "$apt_task"
    printf "${CYAN}%s${NC}  ${BOLD}%-*s${NC}" "${SPIN_FRAMES[0]}" "$max_len" "$flatpak_task"
    
    while [ "$apt_finished" = false ] || [ "$flatpak_finished" = false ]; do
        # Move back to start of second line (where we are now)
        printf "\r"
        
        # Check and update Flatpak line first (since we're on it)
        if [ "$flatpak_finished" = false ]; then
            if [ -f "$flatpak_status_file" ]; then
                local flatpak_exit_code
                flatpak_exit_code=$(cat "$flatpak_status_file" 2>/dev/null)
                if [[ -z "$flatpak_exit_code" || ! "$flatpak_exit_code" =~ ^[0-9]+$ ]]; then
                    flatpak_exit_code="1"
                fi

                printf "\033[K" # Clear current line
                if [ "$flatpak_exit_code" -eq 0 ]; then
                    local flatpak_count
                    flatpak_count=$(cat "$flatpak_count_file" 2>/dev/null || echo "0")
                    if [ "$flatpak_count" -eq 0 ]; then
                        printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${DIM}Already up to date${NC}" "$max_len" "$flatpak_task"
                    else
                        printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${GREEN}%s updated${NC}" "$max_len" "$flatpak_task" "$flatpak_count"
                    fi
                else
                    local flatpak_error
                    flatpak_error=$(cat "$flatpak_error_file" 2>/dev/null | head -1)
                    if [ -z "$flatpak_error" ]; then
                        printf "${RED}✗${NC}  ${BOLD}%-*s${NC} ${RED}Failed${NC}" "$max_len" "$flatpak_task"
                    else
                        printf "${RED}✗${NC}  ${BOLD}%-*s${NC} ${RED}%s${NC}" "$max_len" "$flatpak_task" "$flatpak_error"
                    fi
                fi
                flatpak_finished=true
            else
                printf "\033[K${CYAN}%s${NC}  ${BOLD}%-*s${NC}" "${SPIN_FRAMES[$spin_index]}" "$max_len" "$flatpak_task"
            fi
        else
            # Flatpak already finished, just redraw it
            local flatpak_exit
            flatpak_exit=$(cat "$flatpak_status_file" 2>/dev/null || echo "1")
            printf "\033[K"
            if [ "$flatpak_exit" -eq 0 ]; then
                local flatpak_count
                flatpak_count=$(cat "$flatpak_count_file" 2>/dev/null || echo "0")
                if [ "$flatpak_count" -eq 0 ]; then
                    printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${DIM}Already up to date${NC}" "$max_len" "$flatpak_task"
                else
                    printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${GREEN}%s updated${NC}" "$max_len" "$flatpak_task" "$flatpak_count"
                fi
            else
                printf "${RED}✗${NC}  ${BOLD}%-*s${NC} ${RED}Failed${NC}" "$max_len" "$flatpak_task"
            fi
        fi

        # Now move up to APT line and update it
        printf "\033[1A\r"
        if [ "$apt_finished" = false ]; then
            if [ -f "$apt_status_file" ]; then
                local apt_exit_code
                apt_exit_code=$(cat "$apt_status_file" 2>/dev/null)
                if [[ -z "$apt_exit_code" || ! "$apt_exit_code" =~ ^[0-9]+$ ]]; then
                    apt_exit_code="1"
                fi

                printf "\033[K" # Clear current line
                if [ "$apt_exit_code" -eq 0 ]; then
                    local apt_count
                    apt_count=$(cat "$apt_count_file" 2>/dev/null || echo "0")
                    if [ "$apt_count" -eq 0 ]; then
                        printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${DIM}Already up to date${NC}" "$max_len" "$apt_task"
                    else
                        printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${GREEN}%s updated${NC}" "$max_len" "$apt_task" "$apt_count"
                    fi
                else
                    local apt_error
                    apt_error=$(cat "$apt_error_file" 2>/dev/null | head -1)
                    if [ -z "$apt_error" ]; then
                        printf "${RED}✗${NC}  ${BOLD}%-*s${NC} ${RED}Failed${NC}" "$max_len" "$apt_task"
                    else
                        printf "${RED}✗${NC}  ${BOLD}%-*s${NC} ${RED}%s${NC}" "$max_len" "$apt_task" "$apt_error"
                    fi
                fi
                apt_finished=true
            else
                printf "\033[K${CYAN}%s${NC}  ${BOLD}%-*s${NC}" "${SPIN_FRAMES[$spin_index]}" "$max_len" "$apt_task"
            fi
        else
            # APT already finished, just redraw it
            local apt_exit
            apt_exit=$(cat "$apt_status_file" 2>/dev/null || echo "1")
            printf "\033[K"
            if [ "$apt_exit" -eq 0 ]; then
                local apt_count
                apt_count=$(cat "$apt_count_file" 2>/dev/null || echo "0")
                if [ "$apt_count" -eq 0 ]; then
                    printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${DIM}Already up to date${NC}" "$max_len" "$apt_task"
                else
                    printf "${GREEN}✓${NC}  ${BOLD}%-*s${NC} ${GREEN}%s updated${NC}" "$max_len" "$apt_task" "$apt_count"
                fi
            else
                printf "${RED}✗${NC}  ${BOLD}%-*s${NC} ${RED}Failed${NC}" "$max_len" "$apt_task"
            fi
        fi
        
        # Move back down to second line for next iteration
        printf "\n"

        sleep "$delay"
        spin_index=$(( (spin_index + 1) % ${#SPIN_FRAMES[@]} ))

        # Break early if both finished
        [ "$apt_finished" = true ] && [ "$flatpak_finished" = true ] && break
    done
    
    # Final newline to move below both lines
    printf "\n"
}

# --- Task Functions (truly silent) ---

# Function to handle apt updates and upgrades (runs in background)
run_apt_updates_background() {
    local status_file="$1"
    local package_count_file="$2"
    local error_file="$3"
    local exit_code=0
    local package_count=0
    local upgraded_count=0
    local newly_installed_count=0
    local apt_output

    # Capture all output (including stderr to prevent UI disruption)
    apt_output=$(
        {
            # Run apt update first
            if ! sudo apt update 2>&1; then
                echo "FAILED_UPDATE"
                exit 1
            fi

            # Run the actual upgrade
            sudo apt full-upgrade -y 2>&1
        }
    )
    exit_code=$?

    # Save output to log
    echo "$apt_output" > "$APT_LOG"

    if [ "$exit_code" -eq 0 ] || echo "$apt_output" | grep -q "^0 upgraded"; then
        # Parse multiple apt output formats
        # Format 1: "X upgraded, Y newly installed, Z to remove and A not upgraded"
        local apt_summary_line
        apt_summary_line=$(echo "$apt_output" | grep -E "^[0-9]+ (upgraded|newly installed|to remove)" | tail -1)

        if [ -n "$apt_summary_line" ]; then
            # Extract upgraded count
            upgraded_count=$(echo "$apt_summary_line" | sed -n 's/^\([0-9]\+\) upgraded.*/\1/p')
            [ -z "$upgraded_count" ] && upgraded_count=0

            # Extract newly installed count  
            newly_installed_count=$(echo "$apt_summary_line" | sed -n 's/.*\([0-9]\+\) newly installed.*/\1/p')
            [ -z "$newly_installed_count" ] && newly_installed_count=0

            package_count=$((upgraded_count + newly_installed_count))
        else
            # Check for other indicators
            if echo "$apt_output" | grep -q "All packages are up to date"; then
                package_count=0
            else
                # Count actual installations
                package_count=$(echo "$apt_output" | grep -c "^Setting up " || echo "0")
            fi
        fi
        
        echo "$package_count" >"$package_count_file"
        echo "0" >"$status_file"
    else
        # Extract error message
        echo "$apt_output" | grep -E "(E:|ERROR:|Failed)" | head -1 >"$error_file"
        if [ ! -s "$error_file" ]; then
            echo "Package upgrade failed" >"$error_file"
        fi
        echo "1" >"$status_file"
    fi
}

# Function to handle flatpak updates (runs in background)
run_flatpak_updates_background() {
    local status_file="$1"
    local package_count_file="$2"
    local error_file="$3"
    local exit_code=0
    local package_count=0
    local flatpak_output

    # Capture all output
    flatpak_output=$(flatpak update -y 2>&1)
    exit_code=$?

    # Save output to log
    echo "$flatpak_output" > "$FLATPAK_LOG"

    if [ "$exit_code" -eq 0 ]; then
        # ROBUST PARSING: Handle multiple flatpak output formats

        # Primary method: Count from numbered list
        local numbered_apps
        numbered_apps=$(echo "$flatpak_output" | grep -E "^[[:space:]]*[0-9]+\." |
            grep -v "\.Locale\|\.Extension\|\.Platform\|\.GL\.\|\.Sdk" |
            awk '{print $2}' | sort -u | wc -l || echo "0")

        # Secondary method: Count from action lines
        local action_apps
        action_apps=$(echo "$flatpak_output" | grep -E "^(Updating|Installing) " |
            grep -v "\.Locale\|\.Extension\|\.Platform\|\.GL\.\|\.Sdk" |
            awk -F'/' '{print $1}' | awk '{print $2}' | sort -u | wc -l || echo "0")

        # Use the most reliable count
        if [ "$numbered_apps" -gt 0 ]; then
            package_count=$numbered_apps
        elif [ "$action_apps" -gt 0 ]; then
            package_count=$action_apps
        else
            # Check if already up to date
            if echo "$flatpak_output" | grep -q "Nothing to do"; then
                package_count=0
            fi
        fi

        echo "$package_count" >"$package_count_file"
        echo "0" >"$status_file"
    else
        # Extract error message
        echo "$flatpak_output" | grep -E "(error:|Error:|Failed)" | head -1 >"$error_file"
        if [ ! -s "$error_file" ]; then
            echo "Flatpak update failed" >"$error_file"
        fi
        echo "1" >"$status_file"
    fi
}

# --- Script Execution ---

# --- Prettier Header with Colors ---
echo
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${BOLD}${WHITE}System Update Manager${NC} ${DIM}v2.0${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo

# Request sudo password upfront
echo -e "${YELLOW}▸ Authentication required for system updates${NC}"
if ! sudo -v; then
    echo -e "${RED}✗ Failed to obtain sudo privileges. Exiting.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Authentication successful${NC}"
echo

# Create temporary status files
APT_STATUS_FILE=$(mktemp)
FLATPAK_STATUS_FILE=$(mktemp)
APT_COUNT_FILE=$(mktemp)
FLATPAK_COUNT_FILE=$(mktemp)
APT_ERROR_FILE=$(mktemp)
FLATPAK_ERROR_FILE=$(mktemp)

# Ensure status files are empty before starting
rm -f "$APT_STATUS_FILE" "$FLATPAK_STATUS_FILE" "$APT_COUNT_FILE" "$FLATPAK_COUNT_FILE" "$APT_ERROR_FILE" "$FLATPAK_ERROR_FILE"

# Start both background tasks
run_apt_updates_background "$APT_STATUS_FILE" "$APT_COUNT_FILE" "$APT_ERROR_FILE" &
APT_PID=$!
run_flatpak_updates_background "$FLATPAK_STATUS_FILE" "$FLATPAK_COUNT_FILE" "$FLATPAK_ERROR_FILE" &
FLATPAK_PID=$!

# Show starting message
echo -e "${BOLD}Updating your system...${NC}"
echo

# Show concurrent status displays
manage_status_displays "APT packages" "$APT_STATUS_FILE" "$APT_COUNT_FILE" "$APT_ERROR_FILE" "Flatpak applications" "$FLATPAK_STATUS_FILE" "$FLATPAK_COUNT_FILE" "$FLATPAK_ERROR_FILE"

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

# Get final counts for summary
APT_COUNT=$(cat "$APT_COUNT_FILE" 2>/dev/null || echo "0")
FLATPAK_COUNT=$(cat "$FLATPAK_COUNT_FILE" 2>/dev/null || echo "0")

# Clean up temp files
rm -f "$APT_STATUS_FILE" "$FLATPAK_STATUS_FILE" "$APT_COUNT_FILE" "$FLATPAK_COUNT_FILE" "$APT_ERROR_FILE" "$FLATPAK_ERROR_FILE"

echo
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${BOLD}${WHITE}Update Summary${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ "$APT_EXIT_CODE" -eq 0 ] && [ "$FLATPAK_EXIT_CODE" -eq 0 ]; then
    echo -e "  ${GREEN}✓ All updates completed successfully${NC}"
else
    echo -e "  ${YELLOW}⚠ Some updates encountered issues${NC}"
fi

echo -e "  ${DIM}APT packages updated: ${BOLD}$APT_COUNT${NC}"
echo -e "  ${DIM}Flatpak apps updated: ${BOLD}$FLATPAK_COUNT${NC}"
echo
echo -e "  ${DIM}Logs saved to:${NC}"
echo -e "  ${DIM}• $APT_LOG${NC}"
echo -e "  ${DIM}• $FLATPAK_LOG${NC}"
echo

# Check if debug log exists and has content
if [ -f "${LOG_DIR}/${LOG_BASE_NAME}_flatpak_debug.log" ]; then
    echo -e "  ${DIM}• ${LOG_DIR}/${LOG_BASE_NAME}_flatpak_debug.log (debug info)${NC}"
fi
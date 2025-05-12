#!/bin/bash

# Directory and script paths
BASE_DIR="/home/cpknight/Projects/email-automation"
PYTHON="python3"
PROCESSOR="$BASE_DIR/email_processor.py"
CLASSIFIER="$BASE_DIR/email_classifier.py"
SUMMARY_INBOX="$BASE_DIR/email_summary_inbox.py"
SUMMARY_SPAM="$BASE_DIR/email_summary_spam.py"
SUMMARY_NOTIFICATIONS="$BASE_DIR/email_summary_notifications.py"
SUMMARY_CORRESPONDENCE="$BASE_DIR/email_summary_correspondence.py"
ARCHIVE_NOTIFICATIONS="$BASE_DIR/email_archive_notifications.py"
ARCHIVE_SPAM="$BASE_DIR/email_archive_spam.py"
ARCHIVE_CORRESPONDENCE="$BASE_DIR/email_archive_correspondence.py"
ARCHIVE_SENT="$BASE_DIR/email_archive_sent.py"

# Lock file to enforce single instance
LOCK_FILE="$BASE_DIR/email_automation.lock"

# State files for persistent scheduling and retries
STATE_FILE="$BASE_DIR/email_automation_state.txt"
RETRY_STATE_FILE="$BASE_DIR/email_automation_retry_state.txt"

# Schedules (in seconds)
PROCESSOR_INTERVAL=$((15 * 60))  # 15 minutes
CLASSIFIER_INTERVAL=$((60 * 60))  # 1 hour
DAILY_INTERVAL=$((24 * 60 * 60)) # 1 day
LOOKAHEAD_PERIOD=$((24 * 60 * 60)) # 24 hours
DAILY_TARGET_HOUR=16  # 10 AM MT = 16:00 UTC

# Retry settings
MAX_RETRIES=3
RETRY_DELAY=60  # seconds

# ANSI color codes
GREY50="\033[90m"
YELLOW="\033[33m"
GREEN="\033[32m"
CYAN="\033[36m"
MAGENTA="\033[35m"
RED="\033[31m"
RESET="\033[0m"

# Debug flag
DEBUG=false
if [ "$1" = "--debug" ]; then
    DEBUG=true
fi

# Function to get UTC timestamp
get_utc_timestamp() {
    date -u '+%Y-%m-%d %H:%M:%S UTC'
}

# Function to check and set lock
check_lock() {
    if [ -f "$LOCK_FILE" ]; then
        pid=$(cat "$LOCK_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Another instance is running (PID $pid). Exiting.${RESET}"
            exit 1
        else
            echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Stale lock file found. Removing.${RESET}"
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"; exit' INT TERM EXIT
}

# Function to read/write state
read_state() {
    if [ -f "$STATE_FILE" ]; then
        source "$STATE_FILE"
        : ${LAST_PROCESSOR:=0}
        : ${LAST_CLASSIFIER:=0}
        : ${LAST_ARCHIVE_NOTIFICATIONS:=0}
        : ${LAST_ARCHIVE_SPAM:=0}
        : ${LAST_ARCHIVE_CORRESPONDENCE:=0}
        : ${LAST_ARCHIVE_SENT:=0}
        : ${LAST_SUMMARY_INBOX:=0}
        : ${LAST_SUMMARY_SPAM:=0}
        : ${LAST_SUMMARY_NOTIFICATIONS:=0}
        : ${LAST_SUMMARY_CORRESPONDENCE:=0}
    else
        LAST_PROCESSOR=0
        LAST_CLASSIFIER=0
        LAST_ARCHIVE_NOTIFICATIONS=0
        LAST_ARCHIVE_SPAM=0
        LAST_ARCHIVE_CORRESPONDENCE=0
        LAST_ARCHIVE_SENT=0
        LAST_SUMMARY_INBOX=0
        LAST_SUMMARY_SPAM=0
        LAST_SUMMARY_NOTIFICATIONS=0
        LAST_SUMMARY_CORRESPONDENCE=0
    fi
}

write_state() {
    cat << EOF > "$STATE_FILE"
LAST_PROCESSOR=$LAST_PROCESSOR
LAST_CLASSIFIER=$LAST_CLASSIFIER
LAST_ARCHIVE_NOTIFICATIONS=$LAST_ARCHIVE_NOTIFICATIONS
LAST_ARCHIVE_SPAM=$LAST_ARCHIVE_SPAM
LAST_ARCHIVE_CORRESPONDENCE=$LAST_ARCHIVE_CORRESPONDENCE
LAST_ARCHIVE_SENT=$LAST_ARCHIVE_SENT
LAST_SUMMARY_INBOX=$LAST_SUMMARY_INBOX
LAST_SUMMARY_SPAM=$LAST_SUMMARY_SPAM
LAST_SUMMARY_NOTIFICATIONS=$LAST_SUMMARY_NOTIFICATIONS
LAST_SUMMARY_CORRESPONDENCE=$LAST_SUMMARY_CORRESPONDENCE
EOF
}

# Function to read/write retry state
read_retry_state() {
    if [ -f "$RETRY_STATE_FILE" ]; then
        source "$RETRY_STATE_FILE"
        : ${RETRY_PROCESSOR:=0}
        : ${RETRY_CLASSIFIER:=0}
        : ${RETRY_ARCHIVE_NOTIFICATIONS:=0}
        : ${RETRY_ARCHIVE_SPAM:=0}
        : ${RETRY_ARCHIVE_CORRESPONDENCE:=0}
        : ${RETRY_ARCHIVE_SENT:=0}
        : ${RETRY_SUMMARY_INBOX:=0}
        : ${RETRY_SUMMARY_SPAM:=0}
        : ${RETRY_SUMMARY_NOTIFICATIONS:=0}
        : ${RETRY_SUMMARY_CORRESPONDENCE:=0}
    else
        RETRY_PROCESSOR=0
        RETRY_CLASSIFIER=0
        RETRY_ARCHIVE_NOTIFICATIONS=0
        RETRY_ARCHIVE_SPAM=0
        RETRY_ARCHIVE_CORRESPONDENCE=0
        RETRY_ARCHIVE_SENT=0
        RETRY_SUMMARY_INBOX=0
        RETRY_SUMMARY_SPAM=0
        RETRY_SUMMARY_NOTIFICATIONS=0
        RETRY_SUMMARY_CORRESPONDENCE=0
    fi
}

write_retry_state() {
    cat << EOF > "$RETRY_STATE_FILE"
RETRY_PROCESSOR=$RETRY_PROCESSOR
RETRY_CLASSIFIER=$RETRY_CLASSIFIER
RETRY_ARCHIVE_NOTIFICATIONS=$RETRY_ARCHIVE_NOTIFICATIONS
RETRY_ARCHIVE_SPAM=$RETRY_ARCHIVE_SPAM
RETRY_ARCHIVE_CORRESPONDENCE=$RETRY_ARCHIVE_CORRESPONDENCE
RETRY_ARCHIVE_SENT=$RETRY_ARCHIVE_SENT
RETRY_SUMMARY_INBOX=$RETRY_SUMMARY_INBOX
RETRY_SUMMARY_SPAM=$RETRY_SUMMARY_SPAM
RETRY_SUMMARY_NOTIFICATIONS=$RETRY_SUMMARY_NOTIFICATIONS
RETRY_SUMMARY_CORRESPONDENCE=$RETRY_SUMMARY_CORRESPONDENCE
EOF
}

# Function to format seconds to human-readable time
format_time() {
    local seconds=$1
    local hours=$((seconds / 3600))
    local minutes=$(((seconds % 3600) / 60))
    local secs=$((seconds % 60))
    if [ "$hours" -ge 24 ]; then
        local days=$((hours / 24))
        hours=$((hours % 24))
        printf "%dd %02dh %02dm %02ds" "$days" "$hours" "$minutes" "$secs"
    else
        printf "%02dh %02dm %02ds" "$hours" "$minutes" "$secs"
    fi
}

# Function to get next scheduled time
get_next_scheduled_time() {
    local last_run=$1
    local interval=$2
    local now=$3
    if [ "$last_run" -eq 0 ] || [ $((now - last_run)) -ge "$interval" ]; then
        echo "$now"  # Run now if overdue
    else
        echo $((last_run + interval))  # Next run is last + interval
    fi
}

# Function to get next daily target (10 AM MT = 16:00 UTC)
get_next_daily_target() {
    local now=$1
    local today=$(date -u -d "@$now" '+%Y-%m-%d')
    local target_today=$(date -u -d "$today $DAILY_TARGET_HOUR:00:00 UTC" '+%s')
    if [ "$now" -ge "$target_today" ]; then
        local tomorrow=$(date -u -d "$today +1 day" '+%Y-%m-%d')
        date -u -d "$tomorrow $DAILY_TARGET_HOUR:00:00 UTC" '+%s'
    else
        echo "$target_today"
    fi
}

# Function to check Proton Mail Bridge process
check_bridge_process() {
    if ! pgrep -f "proton-bridge" >/dev/null 2>&1; then
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${RED}Proton Mail Bridge process not running. Skipping script execution.${RESET}"
        return 1
    fi
    return 0
}

# Function to get friendly script name
get_friendly_name() {
    local script=$1
    case "$script" in
        "PROCESSOR") echo "Email processor" ;;
        "CLASSIFIER") echo "Email classifier" ;;
        "ARCHIVE_NOTIFICATIONS") echo "Notifications folder archiver" ;;
        "ARCHIVE_SPAM") echo "Spam folder archiver" ;;
        "ARCHIVE_CORRESPONDENCE") echo "Correspondence folder archiver" ;;
        "ARCHIVE_SENT") echo "Sent folder archiver" ;;
        "SUMMARY_INBOX") echo "Inbox summary generator" ;;
        "SUMMARY_SPAM") echo "Spam summary generator" ;;
        "SUMMARY_NOTIFICATIONS") echo "Notifications summary generator" ;;
        "SUMMARY_CORRESPONDENCE") echo "Correspondence summary generator" ;;
        *) echo "$script" ;;
    esac
}

# Function to get script path from name
get_script_path() {
    local script=$1
    case "$script" in
        "PROCESSOR") echo "$PROCESSOR" ;;
        "CLASSIFIER") echo "$CLASSIFIER" ;;
        "ARCHIVE_NOTIFICATIONS") echo "$ARCHIVE_NOTIFICATIONS" ;;
        "ARCHIVE_SPAM") echo "$ARCHIVE_SPAM" ;;
        "ARCHIVE_CORRESPONDENCE") echo "$ARCHIVE_CORRESPONDENCE" ;;
        "ARCHIVE_SENT") echo "$ARCHIVE_SENT" ;;
        "SUMMARY_INBOX") echo "$SUMMARY_INBOX" ;;
        "SUMMARY_SPAM") echo "$SUMMARY_SPAM" ;;
        "SUMMARY_NOTIFICATIONS") echo "$SUMMARY_NOTIFICATIONS" ;;
        "SUMMARY_CORRESPONDENCE") echo "$SUMMARY_CORRESPONDENCE" ;;
        *) echo "$script" ;;
    esac
}

# Function to print look-ahead schedule
print_lookahead_schedule() {
    local now=$(date +%s)
    local end=$((now + LOOKAHEAD_PERIOD))
    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}24-hour look-ahead schedule:${RESET}"
    
    declare -A events
    local next_processor=$(get_next_scheduled_time "$LAST_PROCESSOR" "$PROCESSOR_INTERVAL" "$now")
    while [ "$next_processor" -le "$end" ]; do
        events["$next_processor"]="Processor"
        next_processor=$((next_processor + PROCESSOR_INTERVAL))
    done
    
    local next_classifier=$(get_next_scheduled_time "$LAST_CLASSIFIER" "$CLASSIFIER_INTERVAL" "$now")
    while [ "$next_classifier" -le "$end" ]; do
        events["$next_classifier"]="Classifier"
        next_classifier=$((next_classifier + CLASSIFIER_INTERVAL))
    done
    
    local next_daily=$(get_next_daily_target "$now")
    if [ "$next_daily" -le "$end" ]; then
        events["$next_daily"]="Archives"
        events["$((next_daily + 1))"]="Summaries"
    fi
    
    echo -e "  ┌──────────────┬──────────────┬─────────────────────────┐"
    printf "  │ %-12s │ %-12s │ %-23s │\n" "Event" "Time Until" "Scheduled Time"
    echo -e "  ├──────────────┼──────────────┼─────────────────────────┤"
    for time in $(echo "${!events[@]}" | tr ' ' '\n' | sort -n); do
        local event="${events[$time]}"
        local time_until=$((time - now))
        local color
        case "$event" in
            "Processor") color="$GREEN" ;;
            "Classifier") color="$CYAN" ;;
            "Archives"|"Summaries") color="$MAGENTA" ;;
        esac
        printf "  │ ${color}%-12s${RESET} │ %-12s │ %-20s │\n" "$event" "$(format_time "$time_until")" "$(date -u -d "@$time" '+%Y-%m-%d %H:%M:%S UTC')"
    done
    echo -e "  └──────────────┴──────────────┴─────────────────────────┘"
}

# Function to print next event look-ahead
print_next_event() {
    local now=$(date +%s)
    local next_processor=$(get_next_scheduled_time "$LAST_PROCESSOR" "$PROCESSOR_INTERVAL" "$now")
    local next_classifier=$(get_next_scheduled_time "$LAST_CLASSIFIER" "$CLASSIFIER_INTERVAL" "$now")
    local next_daily=$(get_next_daily_target "$now")
    
    local next_time=$next_processor
    local next_script="Processor"
    if [ "$next_classifier" -lt "$next_time" ]; then
        next_time=$next_classifier
        next_script="Classifier"
    fi
    if [ "$next_daily" -lt "$next_time" ]; then
        next_time=$next_daily
        next_script="Archives"
    fi
    
    local time_until=$((next_time - now))
    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Next event: $next_script in $(format_time $time_until) at $(date -u -d "@$next_time" '+%Y-%m-%d %H:%M:%S UTC')${RESET}"
    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Next archives: $(date -u -d "@$next_daily" '+%Y-%m-%d %H:%M:%S UTC') ($(format_time $((next_daily - now))))${RESET}"
    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Next summaries: $(date -u -d "@$next_daily" '+%Y-%m-%d %H:%M:%S UTC') ($(format_time $((next_daily - now))))${RESET}"
}

# Function to check Proton Mail Bridge status
check_bridge() {
    if ! nc -z 127.0.0.1 1143 >/dev/null 2>&1; then
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Proton Mail Bridge not responding on 127.0.0.1:1143. Waiting $RETRY_DELAY seconds...${RESET}"
        sleep "$RETRY_DELAY"
        if ! nc -z 127.0.0.1 1143 >/dev/null 2>&1; then
            echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Proton Mail Bridge still down. Proceeding with caution.${RESET}"
            return 1
        fi
    fi
    return 0
}

# Function to run a script with retry logic
run_script() {
    local script="$1"
    local interval="$2"
    local last_run_var="$3"
    local retry_var="$4"
    local now=$(date +%s)
    local last_run="${!last_run_var:-0}"
    local retries="${!retry_var:-0}"
    local next_run
    
    if [ "$interval" -eq 0 ]; then
        next_run=$now
    else
        if [ "$last_run" -eq 0 ] || [ $((now - last_run)) -ge "$interval" ]; then
            next_run=$now  # Run now if overdue
        else
            next_run=$((last_run + interval))  # Next run is last + interval
        fi
    fi
    
    if [ "$DEBUG" = true ]; then
        local friendly_name=$(get_friendly_name "$(basename "$script" .py | tr '[:lower:]' '[:upper:]' | sed 's/EMAIL_//')")
        local time_since=$((now - last_run))
        local time_to_next=$((next_run - now))
        [ "$last_run" -eq 0 ] && time_since="never" || time_since=$(format_time "$time_since")
        [ "$time_to_next" -lt 0 ] && time_to_next=0
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Checking $friendly_name: last ran $time_since ago, next in $(format_time $time_to_next)${RESET}"
    fi
    
    if [ "$now" -ge "$next_run" ]; then
        if ! check_bridge_process; then
            return 0
        fi
        check_bridge
        while [ "$retries" -lt "$MAX_RETRIES" ]; do
            echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Running $script (Attempt $((retries + 1))/$MAX_RETRIES)${RESET}"
            "$PYTHON" "$script"
            local exit_code=$?
            
            if [ "$exit_code" -eq 0 ]; then
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}$script completed successfully.${RESET}"
                eval "$last_run_var=$now"
                eval "$retry_var=0"
                write_state
                write_retry_state
                if [ "$interval" -ne 0 ]; then
                    print_next_event
                fi
                return 0
            else
                retries=$((retries + 1))
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}$script failed with exit code $exit_code. Retry $retries/$MAX_RETRIES after $RETRY_DELAY seconds.${RESET}"
                eval "$retry_var=$retries"
                write_retry_state
                if [ "$retries" -lt "$MAX_RETRIES" ]; then
                    sleep "$RETRY_DELAY"
                else
                    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}$script failed after $MAX_RETRIES retries. Moving on.${RESET}"
                    eval "$retry_var=0"
                    write_retry_state
                    if [ "$interval" -ne 0 ]; then
                        print_next_event
                    fi
                    return 0
                fi
            fi
        done
    fi
    return 0
}

# Main loop
main_loop() {
    check_lock
    read_state
    read_retry_state
    
    # Startup message with last run times and overdue check
    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Starting email_automation.sh (PID $$) at $BASE_DIR/email_automation.sh${RESET}"
    echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Intervals: Processor every $(format_time $PROCESSOR_INTERVAL), Classifier every $(format_time $CLASSIFIER_INTERVAL), Daily tasks every $(format_time $DAILY_INTERVAL) at ${DAILY_TARGET_HOUR}:00 UTC${RESET}"
    
    local now=$(date +%s)
    local next_daily=$(get_next_daily_target "$now")
    local overdue=false
    for script in "PROCESSOR" "CLASSIFIER" "ARCHIVE_NOTIFICATIONS" "ARCHIVE_SPAM" "ARCHIVE_CORRESPONDENCE" "ARCHIVE_SENT" "SUMMARY_INBOX" "SUMMARY_SPAM" "SUMMARY_NOTIFICATIONS" "SUMMARY_CORRESPONDENCE"; do
        local var="LAST_$script"
        local friendly_name=$(get_friendly_name "$script")
        if [ -z "${!var}" ] || [ "${!var}" -eq 0 ]; then
            echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name has never run.${RESET}"
            if [[ "$script" != "PROCESSOR" && "$script" != "CLASSIFIER" ]]; then
                overdue=true
            fi
        else
            local time_since=$((now - ${!var}))
            echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name last ran $(format_time $time_since) ago at $(date -u -d "@${!var}" '+%Y-%m-%d %H:%M:%S UTC').${RESET}"
            if [[ "$script" != "PROCESSOR" && "$script" != "CLASSIFIER" && $time_since -ge $DAILY_INTERVAL ]]; then
                overdue=true
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name is overdue by $(format_time $time_since).${RESET}"
            fi
        fi
    done
    
    if ! check_bridge_process; then
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${RED}Initial check failed: Proton Mail Bridge not running. Proceeding with caution.${RESET}"
    fi
    
    if [ "$overdue" = true ]; then
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Some daily tasks are overdue. Running catch-up sequence...${RESET}"
        run_script "$PROCESSOR" "0" "LAST_PROCESSOR" "RETRY_PROCESSOR" && true
        run_script "$CLASSIFIER" "0" "LAST_CLASSIFIER" "RETRY_CLASSIFIER" && true
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Running daily archives${RESET}"
        for script in "ARCHIVE_NOTIFICATIONS" "ARCHIVE_SPAM" "ARCHIVE_CORRESPONDENCE" "ARCHIVE_SENT"; do
            local friendly_name=$(get_friendly_name "$script")
            local script_path=$(get_script_path "$script")
            run_script "$script_path" "0" "LAST_$script" "RETRY_$script" && true
            if [ "$?" -eq 0 ]; then
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name executed successfully in catch-up.${RESET}"
            else
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${RED}The $friendly_name failed in catch-up.${RESET}"
            fi
        done
        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Running daily summaries${RESET}"
        for script in "SUMMARY_INBOX" "SUMMARY_SPAM" "SUMMARY_NOTIFICATIONS" "SUMMARY_CORRESPONDENCE"; do
            local friendly_name=$(get_friendly_name "$script")
            local script_path=$(get_script_path "$script")
            run_script "$script_path" "0" "LAST_$script" "RETRY_$script" && true
            if [ "$?" -eq 0 ]; then
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name executed successfully in catch-up.${RESET}"
            else
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${RED}The $friendly_name failed in catch-up.${RESET}"
            fi
        done
    fi
    
    # Print initial look-ahead
    print_lookahead_schedule
    print_next_event
    
    while true; do
        now=$(date +%s)
        next_daily=$(get_next_daily_target "$now")

        run_script "$PROCESSOR" "$PROCESSOR_INTERVAL" "LAST_PROCESSOR" "RETRY_PROCESSOR" && true
        run_script "$CLASSIFIER" "$CLASSIFIER_INTERVAL" "LAST_CLASSIFIER" "RETRY_CLASSIFIER" && true

        if [ "$now" -ge "$next_daily" ]; then
            local run_daily=false
            for script in "ARCHIVE_NOTIFICATIONS" "ARCHIVE_SPAM" "ARCHIVE_CORRESPONDENCE" "ARCHIVE_SENT" "SUMMARY_INBOX" "SUMMARY_SPAM" "SUMMARY_NOTIFICATIONS" "SUMMARY_CORRESPONDENCE"; do
                local var="LAST_$script"
                local last_run="${!var:-0}"
                if [ "$last_run" -eq 0 ] || [ $((now - last_run)) -ge "$DAILY_INTERVAL" ]; then
                    run_daily=true
                    break
                fi
            done
            if [ "$run_daily" = true ]; then
                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Running daily archives${RESET}"
                for script in "ARCHIVE_NOTIFICATIONS" "ARCHIVE_SPAM" "ARCHIVE_CORRESPONDENCE" "ARCHIVE_SENT"; do
                    local friendly_name=$(get_friendly_name "$script")
                    local script_path=$(get_script_path "$script")
                    run_script "$script_path" "0" "LAST_$script" "RETRY_$script" && true
                    if [ "$?" -eq 0 ]; then
                        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name executed successfully.${RESET}"
                    else
                        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${RED}The $friendly_name failed.${RESET}"
                    fi
                done

                echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}Running daily summaries${RESET}"
                for script in "SUMMARY_INBOX" "SUMMARY_SPAM" "SUMMARY_NOTIFICATIONS" "SUMMARY_CORRESPONDENCE"; do
                    local friendly_name=$(get_friendly_name "$script")
                    local script_path=$(get_script_path "$script")
                    run_script "$script_path" "0" "LAST_$script" "RETRY_$script" && true
                    if [ "$?" -eq 0 ]; then
                        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${YELLOW}The $friendly_name executed successfully.${RESET}"
                    else
                        echo -e "${GREY50}[$(get_utc_timestamp)]${RESET} ${RED}The $friendly_name failed.${RESET}"
                    fi
                done
            fi
        fi

        sleep 10  # Check every 10s for responsiveness
    done
}

# Start the main loop
main_loop

#!/bin/bash

# Directory and script paths
BASE_DIR="/home/cpknight/Projects/email-automation"
PYTHON="python3"
PROCESSOR="$BASE_DIR/email_processor.py"
CLASSIFIER="$BASE_DIR/email_classifier.py"
SUMMARY_INBOX="$BASE_DIR/email_summary_inbox.py"
SUMMARY_SPAM="$BASE_DIR/email_summary_spam.py"
ARCHIVE_NOTIFICATIONS="$BASE_DIR/email_archive_notifications.py"
ARCHIVE_SPAM="$BASE_DIR/email_archive_spam.py"
ARCHIVE_CORRESPONDENCE="$BASE_DIR/email_archive_correspondence.py"
ARCHIVE_SENT="$BASE_DIR/email_archive_sent.py"

# Lock file to enforce single instance
LOCK_FILE="$BASE_DIR/email_automation.lock"

# State file for persistent scheduling
STATE_FILE="$BASE_DIR/email_automation_state.txt"

# Schedules (in seconds)
PROCESSOR_INTERVAL=$((15 * 60))  # 15 minutes
CLASSIFIER_INTERVAL=$((60 * 60))  # 1 hour
DAILY_INTERVAL=$((24 * 60 * 60)) # 1 day

# Function to check and set lock
check_lock() {
    if [ -f "$LOCK_FILE" ]; then
        pid=$(cat "$LOCK_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "Another instance is running (PID $pid). Exiting."
            exit 1
        else
            echo "Stale lock file found. Removing."
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
    else
        LAST_PROCESSOR=0
        LAST_CLASSIFIER=0
        LAST_DAILY=0
    fi
}

write_state() {
    cat << EOF > "$STATE_FILE"
LAST_PROCESSOR=$LAST_PROCESSOR
LAST_CLASSIFIER=$LAST_CLASSIFIER
LAST_DAILY=$LAST_DAILY
EOF
}

# Function to run a script if due
run_if_due() {
    local script="$1"
    local interval="$2"
    local last_run_var="$3"
    local now=$(date +%s)
    local last_run="${!last_run_var}"

    if [ $((now - last_run)) -ge "$interval" ]; then
        echo "Running $script at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        "$PYTHON" "$script"
        eval "$last_run_var=$now"
        write_state
        return 0
    fi
    return 1
}

# Main loop
main_loop() {
    check_lock
    read_state

    while true; do
        now=$(date +%s)

        # Run processor every 15 minutes
        run_if_due "$PROCESSOR" "$PROCESSOR_INTERVAL" "LAST_PROCESSOR"

        # Run classifier every hour
        run_if_due "$CLASSIFIER" "$CLASSIFIER_INTERVAL" "LAST_CLASSIFIER"

        # Run daily tasks (archives first, then summaries)
        if [ $((now - LAST_DAILY)) -ge "$DAILY_INTERVAL" ]; then
            echo "Running daily archives at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
            "$PYTHON" "$ARCHIVE_NOTIFICATIONS"
            "$PYTHON" "$ARCHIVE_SPAM"
            "$PYTHON" "$ARCHIVE_CORRESPONDENCE"
            "$PYTHON" "$ARCHIVE_SENT"

            echo "Running daily summaries at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
            "$PYTHON" "$SUMMARY_INBOX"
            "$PYTHON" "$SUMMARY_SPAM"

            LAST_DAILY=$now
            write_state
        fi

        # Sleep for 60 seconds to check schedule again, minimal CPU usage
        sleep 60
    done
}

# Start the main loop
main_loop

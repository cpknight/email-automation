#!/bin/bash

SERVICE_NAME="email-automation"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
SCRIPT_DIR="/home/cpknight/Projects/email-automation"

# Ensure scripts are executable
chmod +x "$SCRIPT_DIR/email_automation.sh"

# Copy service file
sudo cp "$SCRIPT_DIR/email-automation.service" "$SERVICE_FILE"
sudo chmod 644 "$SERVICE_FILE"

# Reload systemd, enable, and start service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo "Service $SERVICE_NAME installed and started."
systemctl status "$SERVICE_NAME"

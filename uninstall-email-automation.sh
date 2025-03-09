#!/bin/bash

SERVICE_NAME="email-automation"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

# Stop and disable service
sudo systemctl stop "$SERVICE_NAME"
sudo systemctl disable "$SERVICE_NAME"

# Remove service file
sudo rm -f "$SERVICE_FILE"

# Reload systemd
sudo systemctl daemon-reload

echo "Service $SERVICE_NAME uninstalled."

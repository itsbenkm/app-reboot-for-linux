#!/usr/bin/env bash

USER_HOME=$HOME
INSTALL_DIR="$USER_HOME/.local/bin/app-reboot"

echo "Uninstalling app-reboot..."

# 1. Remove Autostart
rm -f "$USER_HOME/.config/autostart/app-reboot-restorer.desktop"

# 2. Remove User Systemd Timer/Service + logout save
systemctl --user stop app-reboot-saver.timer 2>/dev/null
systemctl --user disable app-reboot-saver.timer 2>/dev/null
systemctl --user stop app-reboot-saver-logout.service 2>/dev/null
systemctl --user disable app-reboot-saver-logout.service 2>/dev/null
rm -f "$USER_HOME/.config/systemd/user/app-reboot-saver.timer"
rm -f "$USER_HOME/.config/systemd/user/app-reboot-saver-periodic.service"
rm -f "$USER_HOME/.config/systemd/user/app-reboot-saver-logout.service"
systemctl --user daemon-reload

# 3. Remove System-wide Shutdown Service (Requires sudo)
if [ -f "/etc/systemd/system/app-reboot-saver.service" ]; then
    echo "Requesting sudo to remove the shutdown service..."
    sudo systemctl stop app-reboot-saver.service 2>/dev/null
    sudo systemctl disable app-reboot-saver.service 2>/dev/null
    sudo rm -f "/etc/systemd/system/app-reboot-saver.service"
    sudo systemctl daemon-reload
fi

# 4. Remove binaries
rm -rf "$INSTALL_DIR"

echo "Uninstallation complete."

#!/usr/bin/env bash

# Get current user and home directory
USER_NAME=$USER
USER_HOME=$HOME
INSTALL_DIR="$USER_HOME/.local/bin/app-reboot"

echo "Installing App-Reboot for user: $USER_NAME"

# 0. Check for dependencies
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# 1. Create installation directory and copy scripts
mkdir -p "$INSTALL_DIR"
rm -f "$INSTALL_DIR/saver.py" "$INSTALL_DIR/restorer.py"
cp saver.py restorer.py "$INSTALL_DIR/"

# Inject the current repository path so the save file stays contained here
REPO_DIR="$PWD"
sed -i "s|<REPO_DIR_PLACEHOLDER>|$REPO_DIR|g" "$INSTALL_DIR/saver.py"
sed -i "s|<REPO_DIR_PLACEHOLDER>|$REPO_DIR|g" "$INSTALL_DIR/restorer.py"

chmod +x "$INSTALL_DIR/saver.py"
chmod +x "$INSTALL_DIR/restorer.py"

echo "Scripts installed to $INSTALL_DIR"

# 2. Setup Systemd Service for Shutdown (requires sudo)
SERVICE_FILE="/tmp/app-reboot-saver.service"
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Save GUI Apps State Before Shutdown
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
User=$USER_NAME
ExecStart=$INSTALL_DIR/saver.py

[Install]
WantedBy=halt.target reboot.target shutdown.target
EOF

echo "Requesting sudo to install the shutdown service..."
sudo mv "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable app-reboot-saver.service

# 2.5 Setup Systemd User Timer for Periodic Fallback
USER_SYSTEMD_DIR="$USER_HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

TIMER_FILE="$USER_SYSTEMD_DIR/app-reboot-saver.timer"
cat <<EOF > "$TIMER_FILE"
[Unit]
Description=App-Reboot Periodic Save Timer

[Timer]
# Starts 2 minutes after boot, and runs every 2 minutes while awake.
OnBootSec=2m
OnUnitActiveSec=2m
Unit=app-reboot-saver-periodic.service

[Install]
WantedBy=timers.target
EOF

PERIODIC_SERVICE_FILE="$USER_SYSTEMD_DIR/app-reboot-saver-periodic.service"
cat <<EOF > "$PERIODIC_SERVICE_FILE"
[Unit]
Description=Periodic Save GUI Apps State

[Service]
Type=oneshot
ExecStart=$INSTALL_DIR/saver.py
EOF

echo "Enabling periodic safety net timer..."
systemctl --user daemon-reload
systemctl --user enable --now app-reboot-saver.timer

# 3. Setup Autostart for Login
AUTOSTART_DIR="$USER_HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
AUTOSTART_FILE="$AUTOSTART_DIR/app-reboot-restorer.desktop"

cat <<EOF > "$AUTOSTART_FILE"
[Desktop Entry]
Type=Application
Name=App-Reboot Restorer
Comment=Restores applications saved before last shutdown
Exec=$INSTALL_DIR/restorer.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

echo "Autostart configured for login."
echo ""
echo "Installation complete!"
echo "Your open applications will now be saved when you shut down, and restored one-by-one when you log in."

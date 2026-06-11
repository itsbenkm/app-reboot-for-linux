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
cp saver.py "$INSTALL_DIR/"
cp restorer.py "$INSTALL_DIR/"
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

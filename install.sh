#!/usr/bin/env bash
set -euo pipefail

# This installer must run as your normal user -- it calls sudo itself only for
# the system shutdown service. Running the whole thing as root would bake
# root's $HOME/$USER into the user-level units.
if [ "$(id -u)" -eq 0 ]; then
    echo "Please run install.sh as your normal user, not with sudo/root." >&2
    exit 1
fi

# Run from the script's own directory so relative copies and the baked-in
# project path are correct even if the installer is invoked from elsewhere.
cd "$(dirname "$(readlink -f "$0")")"

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
rm -f "$INSTALL_DIR/saver.py" "$INSTALL_DIR/restorer.py" "$INSTALL_DIR/aliases.sh"
cp saver.py restorer.py aliases.sh "$INSTALL_DIR/"

# Inject the current repository path so the save file stays contained here.
# Escape sed metacharacters (&, |, \) so paths containing them don't corrupt
# the substitution.
REPO_DIR="$PWD"
REPO_DIR_ESC=$(printf '%s' "$REPO_DIR" | sed -e 's/[&\\|]/\\&/g')
sed -i "s|<REPO_DIR_PLACEHOLDER>|$REPO_DIR_ESC|g" "$INSTALL_DIR/saver.py"
sed -i "s|<REPO_DIR_PLACEHOLDER>|$REPO_DIR_ESC|g" "$INSTALL_DIR/restorer.py"
sed -i "s|<REPO_DIR_PLACEHOLDER>|$REPO_DIR_ESC|g" "$INSTALL_DIR/aliases.sh"

chmod +x "$INSTALL_DIR/saver.py"
chmod +x "$INSTALL_DIR/restorer.py"

echo "Scripts installed to $INSTALL_DIR"

# 2. Setup Systemd Service for Shutdown (requires sudo).
# This is the LATE backup pass: it runs at system shutdown, by which point the
# user session is usually already gone. The `--late` flag makes it a no-op when
# a usable save already exists (from the logout save in step 2.6 or the periodic
# timer), so it can never clobber a good snapshot with an empty/partial one.
SERVICE_FILE="/tmp/app-reboot-saver.service"
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Save GUI Apps State at shutdown (late backup pass)
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
User=$USER_NAME
ExecStart=$INSTALL_DIR/saver.py --shutdown --late

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
# First save 5 minutes after boot (giving the restore time to finish so the
# periodic save can't race it), then every 2 minutes while awake.
OnBootSec=5m
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

# 2.6 Setup the user logout/session-stop save (the PRIMARY, accurate capture).
# Its ExecStop fires when the GNOME graphical session begins tearing down --
# while your apps are still alive -- so it records the true session. It runs
# entirely in user space (reads /proc, writes one JSON file) and TimeoutStopSec
# guarantees it can never delay logout/shutdown beyond a few seconds.
LOGOUT_SERVICE_FILE="$USER_SYSTEMD_DIR/app-reboot-saver-logout.service"
cat <<EOF > "$LOGOUT_SERVICE_FILE"
[Unit]
Description=Save GUI Apps State on logout (while apps are still alive)
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true
ExecStop=$INSTALL_DIR/saver.py --shutdown
TimeoutStopSec=10

[Install]
WantedBy=graphical-session.target
EOF

echo "Enabling periodic safety-net timer and logout save..."
systemctl --user daemon-reload
systemctl --user enable --now app-reboot-saver.timer
systemctl --user enable --now app-reboot-saver-logout.service

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
Terminal=false
EOF

echo "Autostart configured for login."

# 4. Make the 'app-reboot-cpu-limit' command available in new shells, by
# sourcing aliases.sh from ~/.bashrc (idempotent -- added at most once).
BASHRC="$USER_HOME/.bashrc"
if ! grep -q "source ~/.local/bin/app-reboot/aliases.sh" "$BASHRC" 2>/dev/null; then
    echo '[ -f ~/.local/bin/app-reboot/aliases.sh ] && source ~/.local/bin/app-reboot/aliases.sh' >> "$BASHRC"
    echo "Added the 'app-reboot-cpu-limit' command to $BASHRC (open a new terminal to use it)."
fi

echo ""
echo "Installation complete!"
echo "Your open applications will now be saved when you shut down, and restored one-by-one when you log in."

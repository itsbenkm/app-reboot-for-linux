# App-Reboot

App-Reboot is a smart session manager for Ubuntu (and other GNOME/Wayland-based Linux distributions). It automatically saves your running graphical applications when you shut down or restart, and gracefully reopens them when you log back in.

Unlike traditional startup scripts that launch everything at once (causing your computer to freeze or lag on boot), App-Reboot launches applications **one by one**, starting from the lightest application to the heaviest. It actively monitors your system's CPU load and waits for each application to stabilize before launching the next one.

## Key Features

- **Wayland Compatible**: Bypasses strict Wayland security boundaries by interrogating the kernel `cgroups` directly to map processes to `.desktop` files.
- **Staggered Launch**: Sorts applications by memory footprint and launches them sequentially to prevent "login storms".
- **Smart Wait**: Actively monitors `/proc/stat` to ensure your CPU load has dropped below 40% before launching the next application.
- **Background Filtering**: Automatically ignores background daemons (like `xdg-desktop-portal` or `gnome-shell`) so only user-facing apps are restored.

## Installation

1. Clone or download this repository.
2. Open your terminal in the downloaded folder.
3. Run the installer script:
   ```bash
   ./install.sh
   ```
   *(Note: The installer requires `sudo` because it creates a systemd hook that runs exactly when the system halts/reboots).*

## How It Works

### The State Saver (`saver.py`)
Triggered automatically by a `systemd` service (`app-reboot-saver.service`) when you shut down. 
It analyzes `/proc/<pid>/cgroup` to reliably determine which `.desktop` applications are running under your user account, calculates their memory usage, and saves this list to `~/.config/app-reboot/session.json`.

### The Session Restorer (`restorer.py`)
Triggered automatically by GNOME Autostart (`~/.config/autostart/app-reboot-restorer.desktop`) when you log in. 
It reads the saved JSON state, sorts the applications by memory usage (ascending), and uses `gio launch` to cleanly start them one by one, waiting for the system CPU to settle between each launch.

## Usage & Commands

Once installed, you don't need to do anything manually. It happens automatically!

However, you can run these tools manually from any terminal if you want:

- **Manually save the session right now:**
  ```bash
  app-reboot-saver
  ```
- **Manually trigger the restoration right now:**
  ```bash
  app-reboot-restorer
  ```
- **View currently saved apps:**
  To see exactly what the script has saved for your next boot, simply read the JSON file:
  ```bash
  cat ~/.config/app-reboot/session.json
  ```
  *(Or open that file in any text editor).*

## Note on Browser Tabs
App-Reboot will launch your web browser (Chrome, Firefox, etc.), but restoring the actual *tabs* depends on your browser settings. To ensure your tabs come back:
- **Firefox:** Settings -> General -> "Open previous windows and tabs"
- **Chrome:** Settings -> On startup -> "Continue where you left off"

## Uninstallation

If you wish to remove App-Reboot, run these commands:
```bash
# Disable and remove the systemd service
sudo systemctl disable app-reboot-saver.service
sudo rm /etc/systemd/system/app-reboot-saver.service
sudo systemctl daemon-reload

# Remove the Autostart entry
rm ~/.config/autostart/app-reboot-restorer.desktop

# Remove the installed scripts
rm -rf ~/.local/bin/app-reboot
rm ~/.local/bin/app-reboot-saver
rm ~/.local/bin/app-reboot-restorer
```

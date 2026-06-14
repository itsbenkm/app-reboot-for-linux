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

## Moving or Relocating the Folder

The installer records **this folder's location** so the tool always knows where to save and restore your session. If you move or rename the folder later, the installed hooks (systemd + autostart) will still point at the old path.

If you need to relocate it, just **re-run `./install.sh`** from the new location (or run `./uninstall.sh` *before* moving). The tool now detects a missing folder and tells you to do exactly this, instead of failing silently.

## Uninstallation

**⚠️ IMPORTANT: Do not just delete the folder!** 
Because this tool integrates with GNOME startup and systemd, deleting the folder will leave "ghost" hooks running in the background.

To cleanly remove the tool, run the provided uninstaller:
```bash
./uninstall.sh
```
This will safely remove the Autostart entries, systemd services, and background timers before deleting the application files.

## Changelog

**Latest Updates:**
- **Improved Background Filtering:** Added `org.gnome.Calendar` and `org.gnome.Software` to the ignore list so their background daemon processes are no longer falsely restored as foreground windows.
- **Robust App Launching:** Upgraded `gio launch` integration to verify successful D-Bus execution. It now includes an automatic fallback to directly launch applications via their `Exec` command in a detached session, preventing heavy applications (like Google Chrome) from silently timing out during high-load login sequences.

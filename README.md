# App-Reboot

App-Reboot is a smart session manager for Ubuntu (and other GNOME/Wayland-based Linux distributions). It automatically saves your running graphical applications when you shut down or restart, and gracefully reopens them when you log back in.

Unlike traditional startup scripts that launch everything at once (causing your computer to freeze or lag on boot), App-Reboot launches applications **one by one**, starting from the lightest application to the heaviest. It actively monitors your system's CPU load and waits for each application to stabilize before launching the next one.

## Key Features

- **Wayland Compatible**: Bypasses strict Wayland security boundaries by interrogating the kernel `cgroups` directly to map processes to `.desktop` files.
- **Staggered Launch**: Sorts applications by memory footprint and launches them sequentially to prevent "login storms".
- **Smart Wait**: Actively monitors `/proc/stat` to ensure your CPU load has dropped below 60% before launching the next application.
- **Background Filtering**: Automatically ignores background daemons (like `xdg-desktop-portal` or `gnome-shell`) so only user-facing apps are restored.
- **Terminal Session Restore**: Reopens your `gnome-terminal` sessions as tabs in a single window, each back in its original working directory, with a note showing what was running and how to resume it (commands are never auto-run).
- **Trusted-Path Launch**: Only restores `.desktop` files that resolve to a known system applications directory, so a tampered `reboot.json` can't make an arbitrary `Exec` line run on login.

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
Triggered automatically three ways, in order of accuracy:
- **On logout/shutdown** — a user service (`app-reboot-saver-logout.service`) whose `ExecStop` runs **while your apps are still alive**, as your GNOME session tears down. This is the most accurate capture and the primary mechanism on a normal logout, restart, or shutdown. A short `TimeoutStopSec` guarantees it can never delay the process. (On an abrupt power-cut it may not get to run — that's what the periodic timer below covers.)
- **Every couple of minutes** — a user timer (`app-reboot-saver.timer`) re-saves as a safety net.
- **At system shutdown** — a `systemd` service (`app-reboot-saver.service`) as a last-resort backup. It runs *late* (apps usually already gone), so it only fills in when no usable save exists and never clobbers a fresher one.

It analyzes `/proc/<pid>/cgroup` to reliably determine which `.desktop` applications are running under your user account and calculates their memory usage. It also records your open `gnome-terminal` sessions — each one's working directory and the command(s) running in it. Everything is saved to `reboot.json` **inside this project folder** (kept here so the tool stays self-contained).

### The Session Restorer (`restorer.py`)
Triggered automatically by GNOME Autostart (`~/.config/autostart/app-reboot-restorer.desktop`) when you log in. 
It reads the saved state from `reboot.json`, sorts the applications by memory usage (ascending), and uses `gio launch` to cleanly start them one by one, waiting for the system CPU to settle between each launch.

Your saved `gnome-terminal` sessions are restored **first**, as **tabs in a single window** — the first session opens a new window and the rest are added as tabs. Each tab opens in its original working directory; if a command was running there, the tab prints a short note showing the directory, what was running, and a ready-to-paste line to resume it. Commands are **never auto-run** — restoring a terminal only reopens it and reminds you, so nothing unexpected executes on login.

## Usage & Commands

Once installed, you don't need to do anything manually. It happens automatically!

However, you can run these tools manually from any terminal if you want:

- **Manually save the session right now:**
  ```bash
  ~/.local/bin/app-reboot/saver.py
  ```
- **Manually trigger the restoration right now:**
  ```bash
  ~/.local/bin/app-reboot/restorer.py
  ```
- **View currently saved state:**
  To see exactly what has been saved for your next boot (both apps and terminal sessions), read the JSON file in this project folder:
  ```bash
  cat reboot.json
  ```
  *(Or open that file in any text editor).*
- **Tune how aggressively apps relaunch:**
  The restorer waits for your CPU to settle below a threshold (default **60%**) before launching each app, to avoid a "login storm". Adjust it any time:
  ```bash
  app-reboot-cpu-limit 70     # set the threshold to 70% (integer 10-100)
  app-reboot-cpu-limit        # show the current value
  ```
  Lower = gentler on login (waits for a calmer system); higher = relaunches faster. Takes effect on your next login. (The command is available in new terminals after install; like wallpaper-rotator's `wallpaper-duration`, it's a small function sourced from your `~/.bashrc`.)

## Note on Browser Tabs
App-Reboot will launch your web browser (Chrome, Firefox, etc.), but restoring the actual *tabs* depends on your browser settings. To ensure your tabs come back:
- **Firefox:** Settings -> General -> "Open previous windows and tabs"
- **Chrome:** Settings -> On startup -> "Continue where you left off"

## Note on Terminal Sessions
App-Reboot remembers your open `gnome-terminal` sessions. On login they come back as **tabs in one window**, each in the directory it was in. If something was running, the tab greets you with a note like:

```
[App-Reboot] This terminal was in: /home/you/projects/site
It was running before shutdown (not auto-started):
    npm run dev
To resume, copy one of the lines above and run it.
```

The command is shown for you to re-run — it is **not** executed automatically. A couple of notes:
- Only `gnome-terminal` is supported.
- If you had terminals spread across several *windows*, they're consolidated into tabs of one window. The original window/tab grouping can't be recovered after a reboot (every shell shares one terminal-server process), so everything is gathered into a single window.

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
- **Configurable restore speed:** The CPU-settle threshold is now adjustable with the `app-reboot-cpu-limit <10-100>` command (no argument shows the current value) — mirroring wallpaper-rotator's `wallpaper-duration`. It's stored in a local `config` file in the project folder and read fresh at each login, so changes take effect on the next boot with no restart.
- **Don't drop apps that die first at shutdown:** Heavy apps (e.g. Google Chrome) can fully exit *before* the shutdown save scans, so a teardown-time scan misses them. The shutdown save now keeps every app from the most recent live (periodic) snapshot in addition to what it scans, so an app that was open is never lost just because it shut down quickly. The periodic timer keeps that snapshot fresh, so closed apps still fall off (at most one you closed in the last ~2 minutes before shutdown may reopen once). Also raised the restore CPU-settle threshold from 40% to 60% so apps relaunch faster on capable machines.
- **Fewer wrong restores, no more lost apps:** The shutdown save now records each app's process IDs, letting it tell an app that's still *quitting* (a process is still alive) from one you actually *closed* (all processes gone). This stops apps you closed — or that app-reboot itself reopened — from being resurrected forever, while making sure an app still shutting down (e.g. Google Chrome, whose helper processes exit first and leave only an unmatchable main process) is no longer dropped from the save. *Note:* the document viewer is relaunched, but the specific open file can't be restored — GNOME passes it to the viewer over D-Bus, not on the command line, so the path isn't visible to app-reboot.
- **Hardened restore against tampered `reboot.json`:** Before launching, the restorer now validates that each app's `.desktop` path resolves (via `os.path.realpath`, defeating symlink and `..` tricks) to a location under one of the known/trusted applications directories — the same set the saver scans. Since `reboot.json` lives in a world-readable, user-writable folder, this stops a tampered `path` from pointing at an arbitrary `.desktop` file whose `Exec` line would otherwise run on login. Untrusted entries are skipped with a clear warning.
- **Reliable logout capture:** Added a user logout service that saves your session *while your apps are still alive* (its `ExecStop` fires as the GNOME session tears down), making capture far more accurate than the late shutdown hook. It's time-bounded so it can never delay logout. The shutdown service is now a late backup that won't overwrite a good save, and the merge logic is identity-aware so apps you deliberately closed are no longer resurrected.
- **Terminal Session Restore:** App-Reboot now remembers open `gnome-terminal` sessions and reopens them as tabs in a single window, each in its original directory, with a note showing what was running and a ready-to-paste line to resume it (commands are never auto-run).
- **Improved Background Filtering:** Added `org.gnome.Calendar` and `org.gnome.Software` to the ignore list so their background daemon processes are no longer falsely restored as foreground windows.
- **Robust App Launching:** Upgraded `gio launch` integration to verify successful D-Bus execution. It now includes an automatic fallback to directly launch applications via their `Exec` command in a detached session, preventing heavy applications (like Google Chrome) from silently timing out during high-load login sequences.

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

However, a few commands are available (in any new terminal after install — they're small functions sourced from your `~/.bashrc`). Run **`app-reboot-help`** to see them all:

```
app-reboot-help              Show the available commands.
app-reboot-cpu-limit [n]     Show/set (10-100) the CPU % to wait below per app.
app-reboot-app-wait [secs]   Show/set (0-120) the max wait for that settle.
app-reboot-pause [secs]      Show/set (0-30) the pause after launching each app.
app-reboot-save              Save your current session right now.
app-reboot-restore           Re-open the saved session right now.
app-reboot-saved             List what's currently saved for next boot.
```

- **Tune the restore speed** — three knobs (all take effect on your next login):
  When restoring, the tool launches apps one at a time and, after each, waits for the CPU to settle below `cpu-limit` (default **60%**) before the next — but no longer than `app-wait` (default **15s**), so a heavy app like a browser can't stall the whole restore while it loads. `pause` (default **3s**) is the gap after each launch.
  ```bash
  app-reboot-cpu-limit 70     # wait below 70% CPU (10-100)
  app-reboot-app-wait 10      # ...but at most 10s per app (0-120) — lower = faster
  app-reboot-pause 2          # 2s pause after each launch (0-30)
  app-reboot-cpu-limit        # any command with no argument shows the current value
  ```
  Higher `cpu-limit` / lower `app-wait` = a faster, more aggressive restore; lower `cpu-limit` / higher `app-wait` = gentler on login. (Like wallpaper-rotator's `wallpaper-duration`.)
- **View what's saved** — `app-reboot-saved` (or `cat reboot.json` in the project folder).

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
- **Faster, tunable restore:** The per-app CPU-settle wait is now *capped* (default 15s) so a heavy app (e.g. Chrome) loading can't stall the whole restore for 30-45s, and the post-launch pause dropped from 5s to a configurable 3s. Two new commands join `app-reboot-cpu-limit`: `app-reboot-app-wait` (the cap) and `app-reboot-pause` — all shown in `app-reboot-help`.
- **Fixed a boot-time save wipe (empty *and* partial):** The periodic safety-net save could fire during boot — before or partway through the restore — and overwrite the saved session with an empty or partial scan, so little or nothing came back. Three guards now prevent this: the saver refuses to overwrite a non-empty session with an empty scan; the restorer holds a lock so the periodic save **skips entirely while a restore is in progress** (preventing partial overwrites); and the first post-boot periodic save is delayed (2→5 min).
- **Command set + `app-reboot-help`:** Added an `app-reboot-help` command that lists the available commands, plus convenience wrappers `app-reboot-save`, `app-reboot-restore`, and `app-reboot-saved` (alongside `app-reboot-cpu-limit`) — sourced from `~/.bashrc`, mirroring wallpaper-rotator's command set.
- **Configurable restore speed:** The CPU-settle threshold is now adjustable with the `app-reboot-cpu-limit <10-100>` command (no argument shows the current value) — mirroring wallpaper-rotator's `wallpaper-duration`. It's stored in a local `config` file in the project folder and read fresh at each login, so changes take effect on the next boot with no restart.
- **Don't drop apps that die first at shutdown:** Heavy apps (e.g. Google Chrome) can fully exit *before* the shutdown save scans, so a teardown-time scan misses them. The shutdown save now keeps every app from the most recent live (periodic) snapshot in addition to what it scans, so an app that was open is never lost just because it shut down quickly. The periodic timer keeps that snapshot fresh, so closed apps still fall off (at most one you closed in the last ~2 minutes before shutdown may reopen once). Also raised the restore CPU-settle threshold from 40% to 60% so apps relaunch faster on capable machines.
- **Closed apps stay closed, open apps aren't lost:** Shutdown reconciliation is identity-based (by app) — it keeps the apps from the most recent live snapshot rather than trusting an unreliable teardown-time scan, so an app still shutting down (e.g. Google Chrome, whose helper processes exit first) isn't dropped, while apps you actually closed aren't resurrected. *Note:* the document viewer is relaunched, but the specific open file can't be restored — GNOME passes it to the viewer over D-Bus, not on the command line, so the path isn't visible to app-reboot.
- **Hardened restore against tampered `reboot.json`:** Before launching, the restorer now validates that each app's `.desktop` path resolves (via `os.path.realpath`, defeating symlink and `..` tricks) to a location under one of the known/trusted applications directories — the same set the saver scans. Since `reboot.json` lives in a world-readable, user-writable folder, this stops a tampered `path` from pointing at an arbitrary `.desktop` file whose `Exec` line would otherwise run on login. Untrusted entries are skipped with a clear warning.
- **Reliable logout capture:** Added a user logout service that saves your session *while your apps are still alive* (its `ExecStop` fires as the GNOME session tears down), making capture far more accurate than the late shutdown hook. It's time-bounded so it can never delay logout. The shutdown service is now a late backup that won't overwrite a good save, and the merge logic is identity-aware so apps you deliberately closed are no longer resurrected.
- **Terminal Session Restore:** App-Reboot now remembers open `gnome-terminal` sessions and reopens them as tabs in a single window, each in its original directory, with a note showing what was running and a ready-to-paste line to resume it (commands are never auto-run).
- **Improved Background Filtering:** Added `org.gnome.Calendar` and `org.gnome.Software` to the ignore list so their background daemon processes are no longer falsely restored as foreground windows.
- **Robust App Launching:** Upgraded `gio launch` integration to verify successful D-Bus execution. It now includes an automatic fallback to directly launch applications via their `Exec` command in a detached session, preventing heavy applications (like Google Chrome) from silently timing out during high-load login sequences.

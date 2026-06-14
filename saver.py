#!/usr/bin/env python3
"""
saver.py - App-Reboot State Saver

This script identifies all graphical applications currently running under the 
active user session. It relies on systemd cgroups and executable mappings to 
match running processes to their installed .desktop files, bypassing Wayland's 
strict window-listing limitations.

It calculates the memory usage of each application and saves this data to a 
JSON file to be read later by restorer.py.
"""

import os
import glob
import shlex
import json
import re
import sys
import datetime

# Applications that shouldn't be restored even if they match a desktop file.
# These are typically system daemons, tray icons, or background services.
IGNORE_LIST = {
    'gnome-shell', 'gnome-software', 'evolution-alarm-notify', 'ibus-extension-gtk3',
    'xdg-desktop-portal-gnome', 'xdg-desktop-portal-gtk', 'xdg-desktop-portal',
    'snap-handle-link', 'python3', 'python3.12', 'gnome-remote-desktop-daemon',
    'ibus-daemon', 'ibus-x11', 'gjs', 'gjs-console', 'systemd', 'dbus-daemon',
    'update-notifier', 'session-manager', 'at-spi-dbus-bus', 'x-terminal-emulator',
    'SettingsDaemon', 'org.gnome.Calendar', 'org.gnome.Software'
}

def get_desktop_files():
    """Finds all .desktop files installed on the system across standard paths."""
    directories = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/snapd/desktop/applications",
        "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications")
    ]
    desktop_files = []
    for d in directories:
        if os.path.exists(d):
            desktop_files.extend(glob.glob(os.path.join(d, "*.desktop")))
            desktop_files.extend(glob.glob(os.path.join(d, "**", "*.desktop"), recursive=True))
    return desktop_files

def parse_desktop_files(files):
    """
    Parses a list of .desktop files to create a mapping.
    Maps both the base filename and the Exec binary to the full path of the .desktop file.
    """
    app_map = {}
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                name = None
                exec_cmd = None
                is_app = False
                no_display = False
                
                # Read properties line by line
                for line in file:
                    line = line.strip()
                    if line.startswith("Name=") and not name:
                        name = line.split("=", 1)[1]
                    elif line.startswith("Exec=") and not exec_cmd:
                        raw_exec = line.split("=", 1)[1]
                        # Clean up arguments (e.g. %U, %F) from the Exec string
                        parts = shlex.split(raw_exec)
                        if parts:
                            exec_cmd = os.path.basename(parts[0])
                    elif line.startswith("Type="):
                        if line.split("=", 1)[1] == "Application":
                            is_app = True
                    elif line.startswith("NoDisplay="):
                        if line.split("=", 1)[1].lower() == "true":
                            no_display = True
                            
                # Only include standard visible applications
                if name and is_app and not no_display:
                    base = os.path.basename(f).replace('.desktop', '')
                    app_map[base] = f
                    if exec_cmd:
                        app_map[exec_cmd] = f
        except Exception:
            pass
    return app_map

def get_gnome_terminal_sessions():
    """
    Finds all bash/zsh shell processes running inside GNOME Terminal
    and returns a list of their current working directories and running commands.
    """
    children_map = {}
    for p in os.listdir('/proc'):
        if p.isdigit():
            try:
                with open(f'/proc/{p}/stat', 'r') as f:
                    stat_content = f.read()
                    ppid = stat_content.split(')')[1].split()[1]
                    children_map.setdefault(ppid, []).append(p)
            except Exception:
                pass

    sessions = []
    current_uid = os.getuid()
    for pid in os.listdir('/proc'):
        if not pid.isdigit(): continue
        try:
            proc_dir = os.path.join('/proc', pid)
            if os.stat(proc_dir).st_uid != current_uid: continue
            
            with open(os.path.join(proc_dir, 'comm'), 'r') as f:
                comm = f.read().strip()
                
            if comm in ('bash', 'zsh', 'fish'):
                with open(os.path.join(proc_dir, 'stat'), 'r') as f:
                    stat_content = f.read()
                    ppid = stat_content.split(')')[1].split()[1]
                    
                with open(os.path.join('/proc', ppid, 'comm'), 'r') as f:
                    pcomm = f.read().strip()
                    
                if pcomm.startswith('gnome-terminal-'):
                    cwd = os.readlink(os.path.join(proc_dir, 'cwd'))
                    
                    cmds = []
                    for cpid in children_map.get(pid, []):
                        try:
                            with open(f'/proc/{cpid}/cmdline', 'rb') as f:
                                cmd_bytes = f.read()
                                if cmd_bytes:
                                    cmd_str = ' '.join([b.decode('utf-8', errors='ignore') for b in cmd_bytes.split(b'\x00')]).strip()
                                    if cmd_str and not cmd_str.startswith('gnome-terminal'):
                                        cmds.append(cmd_str)
                        except Exception:
                            pass
                            
                    sessions.append({
                        "cwd": cwd,
                        "running_commands": cmds
                    })
        except Exception:
            pass
    return sessions

def is_ignored(name):
    """Checks if a detected application is in the hardcoded ignore list.

    Uses exact membership rather than substring matching, so an ignored
    identifier (e.g. 'python3' or 'gjs') can't accidentally suppress an
    unrelated real application whose name merely contains that substring.
    """
    return name in IGNORE_LIST

def get_running_gui_apps(app_map):
    """
    Iterates over /proc to find running applications.
    Uses two strategies to identify applications:
    1. Parsing systemd cgroups (most accurate for GNOME/Wayland).
    2. Examining the executable name (fallback).
    """
    running_apps = {}
    page_size = os.sysconf("SC_PAGE_SIZE")
    current_uid = os.getuid()
    
    # Iterate through all Process IDs in /proc
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
            
        proc_dir = os.path.join('/proc', pid)
        try:
            # Skip processes that don't belong to the current user
            stat_info = os.stat(proc_dir)
            if stat_info.st_uid != current_uid:
                continue

            match_key = None

            # Strategy 1: Systemd cgroups (Highly accurate for GNOME Wayland)
            try:
                with open(os.path.join(proc_dir, 'cgroup'), 'r') as f:
                    cgroup = f.read()
                    # Example target: app.slice/app-org.gnome.Terminal.slice
                    match = re.search(r'app\.slice/app-([^/]+)\.(scope|slice)', cgroup)
                    if match:
                        name = match.group(1)
                        if match.group(2) == 'scope':
                            # Remove trailing PID generated by scopes
                            name = name.rsplit('-', 1)[0]
                        # Unescape systemd hex codes
                        name = name.replace(r'\x2d', '-')
                        
                        # Try matching the exact name
                        if name in app_map and not is_ignored(name):
                            match_key = name
                        # Try matching by stripping the 'gnome-' prefix (common in GNOME Shell)
                        elif name.startswith('gnome-') and name[6:] in app_map and not is_ignored(name[6:]):
                            match_key = name[6:]
            except Exception:
                pass

            # Strategy 2: Executable baseline (Fallback if cgroup fails)
            if not match_key:
                exe_path = os.readlink(os.path.join(proc_dir, 'exe'))
                basename = os.path.basename(exe_path)
                
                with open(os.path.join(proc_dir, 'cmdline'), 'rb') as f:
                    cmdline = f.read().split(b'\x00')
                
                cmd_basename = None
                if cmdline and cmdline[0]:
                    cmd_basename = os.path.basename(cmdline[0].decode('utf-8', errors='ignore'))

                if basename in app_map and not is_ignored(basename):
                    match_key = basename
                elif cmd_basename in app_map and not is_ignored(cmd_basename):
                    match_key = cmd_basename
                
            # If we successfully mapped the process to a desktop file
            if match_key:
                desktop_file = app_map[match_key]
                
                # Get memory usage from /proc/<pid>/statm
                with open(os.path.join(proc_dir, 'statm'), 'r') as f:
                    rss_pages = int(f.read().split()[1])
                    mem = rss_pages * page_size
                
                # Aggregate memory if multiple processes share the same desktop file
                if desktop_file not in running_apps:
                    running_apps[desktop_file] = {'mem': mem, 'path': desktop_file}
                else:
                    running_apps[desktop_file]['mem'] += mem
                    
        except (OSError, IOError, ValueError):
            # Ignore processes that die while we are inspecting them
            pass
            
    return list(running_apps.values())

def setup_logging(repo_dir):
    log_file = os.path.join(repo_dir, "monitor.log")
    # Keep monitor.log bounded: the periodic saver appends to it on every run
    # (every couple of minutes), so without trimming it would grow without
    # limit. Before appending this run's output, cap the file to the most
    # recent MAX_LOG_LINES lines.
    MAX_LOG_LINES = 2000
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            if len(lines) > MAX_LOG_LINES:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-MAX_LOG_LINES:])
    except Exception:
        pass
    class Logger:
        def __init__(self, filename):
            self.terminal = sys.stdout
            self.log = open(filename, 'a', encoding='utf-8')
        def write(self, message):
            self.terminal.write(message)
            self.log.write(message)
            self.log.flush()
        def flush(self):
            self.terminal.flush()
            self.log.flush()
    sys.stdout = Logger(log_file)
    sys.stderr = sys.stdout
    print(f"\n--- App-Reboot Saver Run: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

def main():
    # 3. Ensure the config directory exists
    # Use injected REPO_DIR so the save file stays within the cloned repository boundary
    REPO_DIR = "<REPO_DIR_PLACEHOLDER>"
    
    # Guard: the repo path was baked in at install time. If the folder was
    # moved or deleted, there's nowhere to save the session state, so fail
    # with a clear message instead of erroring obscurely later.
    if not os.path.isdir(REPO_DIR):
        sys.stderr.write(
            f"app-reboot: project folder '{REPO_DIR}' no longer exists "
            "(moved or deleted).\nRe-run install.sh from its new location.\n"
        )
        sys.exit(1)

    is_shutdown = "--shutdown" in sys.argv
    
    # Setup logging
    setup_logging(REPO_DIR)
    
    print("Saving current GUI applications state...")
    
    # 1. Parse all available applications
    files = get_desktop_files()
    app_map = parse_desktop_files(files)
    
    # 2. Match them against running processes
    apps_to_save = get_running_gui_apps(app_map)
    terminal_sessions = get_gnome_terminal_sessions()

    session_file = os.path.join(REPO_DIR, "reboot.json")
    
    if is_shutdown:
        print("Shutdown detected! Merging with previous state to prevent data loss from closing apps.")
        try:
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                
                old_terms = old_data.get("gnome_terminal_sessions", [])
                if not terminal_sessions and old_terms:
                    terminal_sessions = old_terms
                    print("Kept terminal sessions from previous save.")
                    
                old_apps = old_data.get("apps", [])
                if len(apps_to_save) < len(old_apps):
                    apps_to_save = old_apps
                    print("Kept apps from previous save.")
        except Exception as e:
            print(f"Failed to merge state: {e}")
            
    session_data = {
        "apps": apps_to_save,
        "gnome_terminal_sessions": terminal_sessions
    }
    
    # Save session to file results to JSON
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=4)
        
    print(f"Saved {len(apps_to_save)} applications and {len(terminal_sessions)} terminal sessions to {session_file}")
    for app in apps_to_save:
        print(f" - {os.path.basename(app['path'])} ({(app['mem'] / 1024 / 1024):.1f} MB)")
    for term in terminal_sessions:
        print(f" - Terminal at: {term.get('cwd') if isinstance(term, dict) else term}")

if __name__ == "__main__":
    main()

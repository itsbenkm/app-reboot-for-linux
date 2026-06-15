#!/usr/bin/env python3
"""
restorer.py - App-Reboot Session Restorer

This script is triggered on login via GNOME Autostart.
It reads the session state saved by saver.py and reopens the applications.
To prevent the system from freezing due to a "login storm", it launches the 
applications sequentially (lightest memory footprint first) and waits for the 
CPU load to stabilize before launching the next application.
"""

import os
import json
import time
import subprocess
import sys
import datetime

# Trusted directories that .desktop files may legitimately live in. These are
# exactly the locations saver.py scans in get_desktop_files(). A launchable
# app's path in reboot.json must resolve to a location under one of these; any
# other path is treated as tampering and skipped (reboot.json is user-writable
# in a world-readable folder, so an attacker could otherwise point `path` at an
# arbitrary .desktop file whose Exec line would run on login).
TRUSTED_DESKTOP_DIRS = [
    os.path.realpath(d) for d in (
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/snapd/desktop/applications",
        "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    )
]

def is_trusted_desktop(path):
    """
    Returns True only if `path` resolves to a location strictly under one of
    the known/trusted desktop-file directories. Both sides are passed through
    os.path.realpath so symlinks and '..' tricks can't escape a trusted dir.
    """
    real_path = os.path.realpath(path)
    for trusted in TRUSTED_DESKTOP_DIRS:
        if real_path.startswith(trusted + os.sep):
            return True
    return False

def get_cpu_usage():
    """
    Calculates the current CPU usage percentage by reading /proc/stat.
    It takes two snapshots 0.5 seconds apart to calculate the delta.
    """
    def read_cpu():
        with open('/proc/stat', 'r') as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith('cpu '):
                parts = [float(i) for i in line.split()[1:]]
                # idle time is the 4th column (index 3)
                idle = parts[3]
                # iowait is the 5th column (index 4)
                idle += parts[4]
                total = sum(parts)
                return idle, total
        return 0, 0

    idle1, total1 = read_cpu()
    time.sleep(0.5)
    idle2, total2 = read_cpu()

    total_diff = total2 - total1
    idle_diff = idle2 - idle1

    if total_diff == 0:
        return 0.0
    # CPU Usage = 100% - Idle%
    return 100.0 * (1.0 - idle_diff / total_diff)

def setup_logging(repo_dir):
    log_file = os.path.join(repo_dir, "monitor.log")
    # Keep monitor.log bounded (shared with saver.py, which appends on every
    # periodic run). Cap the file to the most recent MAX_LOG_LINES lines
    # before appending this run's output.
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
    print(f"\n--- App-Reboot Restorer Run: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

def main():
    # Use injected REPO_DIR so it reads from the cloned repository boundary
    REPO_DIR = "<REPO_DIR_PLACEHOLDER>"
    
    # Guard: the repo path was baked in at install time. If the folder was
    # moved or deleted, there's no saved session to read, so fail with a
    # clear message instead of erroring obscurely later.
    if not os.path.isdir(REPO_DIR):
        sys.stderr.write(
            f"app-reboot: project folder '{REPO_DIR}' no longer exists "
            "(moved or deleted).\nRe-run install.sh from its new location.\n"
        )
        sys.exit(1)

    # Setup logging
    setup_logging(REPO_DIR)
    
    session_file = os.path.join(REPO_DIR, "reboot.json")
    
    if not os.path.exists(session_file):
        print("No saved session found.")
        return

    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading session file: {e}")
        return

    apps = []
    terminal_sessions = []
    
    if isinstance(data, dict):
        apps = data.get("apps", [])
        terminal_sessions = data.get("gnome_terminal_sessions", [])
    elif isinstance(data, list):
        apps = data

    if terminal_sessions:
        # Filter out the standard gnome-terminal desktop file to prevent duplicates
        apps = [app for app in apps if 'org.gnome.Terminal.desktop' not in app.get('path', '')]

    # Sort apps by memory usage, ascending (lightest applications launch first)
    apps.sort(key=lambda x: x.get('mem', 0))

    print(f"Found {len(apps)} applications and {len(terminal_sessions)} terminal sessions to restore.")
    
    print("Waiting for system load to stabilize before restoring apps...")
    # Initial wait to let auto.updates or other heavy startup tasks begin
    time.sleep(5.0)
    
    # Wait up to 2 minutes (60 retries * 2 sec) for the CPU to drop below 40%
    wait_retries = 0
    while wait_retries < 60:
        cpu_usage = get_cpu_usage()
        print(f"Current startup CPU usage: {cpu_usage:.1f}%")
        if cpu_usage < 40.0:
            print("System stable. Proceeding with restore.")
            break
        print("System busy, waiting for it to settle...")
        time.sleep(2.0)
        wait_retries += 1
    else:
        # Loop exhausted without the CPU settling -- proceed regardless so a
        # persistently busy login can't block the restore indefinitely.
        print("CPU did not settle below 40% within the wait budget; proceeding anyway.")

    # Restore terminal sessions first, gathered as TABS in a single window.
    #
    # gnome-terminal only runs a per-tab command for the FIRST tab in one
    # invocation, so we launch the sessions sequentially: the first opens a
    # new --window, and each subsequent one uses --tab, which "opens a new tab
    # in the last-opened window" -- i.e. attaches to the window we just made.
    # A short delay keeps them ordered and attached to the right window.
    #
    # NOTE: the original window/tab grouping can't be recovered from /proc
    # (every shell shares one gnome-terminal-server parent), so all restored
    # sessions come back as tabs of one window.
    valid_terms = []
    for term in terminal_sessions:
        term_cwd = term.get('cwd') if isinstance(term, dict) else term
        cmds = term.get('running_commands', []) if isinstance(term, dict) else []
        if term_cwd and os.path.isdir(term_cwd):
            valid_terms.append((term_cwd, cmds))

    def sh_quote_for_echo(text):
        # Make text safe to embed inside a single-quoted bash string. The
        # '\'' trick closes the quote, adds a literal quote, then reopens it,
        # so the character also displays correctly in the echoed note.
        return text.replace("'", "'\\''")

    for idx, (term_cwd, cmds) in enumerate(valid_terms):
        print(f"Restoring terminal tab at {term_cwd}...")
        # First session opens the window; the rest attach to it as tabs.
        tab_flag = '--window' if idx == 0 else '--tab'
        try:
            if cmds:
                # Build an actionable note: where the terminal was, what it
                # was running, and a ready-to-paste line to resume it. We do
                # NOT auto-run the command -- that would be risky on login.
                note_lines = [
                    f"\\e[1;33m[App-Reboot] This terminal was in: {sh_quote_for_echo(term_cwd)}\\e[0m",
                    "\\e[1;33mIt was running before shutdown (not auto-started):\\e[0m",
                ]
                for c in cmds:
                    note_lines.append(f"\\e[0;36m    {sh_quote_for_echo(c)}\\e[0m")
                note_lines.append("\\e[0;32mTo resume, copy one of the lines above and run it.\\e[0m")
                note = "\\n".join(note_lines)

                # Print the note, then hand over to an interactive shell.
                bash_cmd = f"echo -e '{note}'; exec $SHELL"

                subprocess.Popen(['gnome-terminal', tab_flag, f'--working-directory={term_cwd}',
                                  '--', 'bash', '-c', bash_cmd],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            else:
                subprocess.Popen(['gnome-terminal', tab_flag, f'--working-directory={term_cwd}'],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            # Brief pause so the next --tab attaches to the window we just
            # opened (and to avoid hammering the terminal server).
            time.sleep(1.0)
        except Exception as e:
            print(f"Failed to launch terminal tab in {term_cwd}: {e}")
            
    if terminal_sessions:
        time.sleep(3.0)

    for app in apps:
        app_path = app.get('path')
        if not app_path or not os.path.exists(app_path):
            continue

        # Security: reboot.json is user-writable, so only launch desktop files
        # that resolve to a known/trusted applications directory. Otherwise a
        # tampered path could run an arbitrary Exec line on login.
        if not is_trusted_desktop(app_path):
            print(f"Skipping untrusted desktop file: {app_path}")
            continue

        print(f"Launching {os.path.basename(app_path)}...")
        try:
            import shutil
            import shlex
            
            launch_success = False
            # Try 'gio launch' first (standard on GNOME/Ubuntu)
            if shutil.which('gio'):
                try:
                    result = subprocess.run(['gio', 'launch', app_path], 
                                            stdout=subprocess.DEVNULL, 
                                            stderr=subprocess.DEVNULL,
                                            timeout=10)
                    if result.returncode == 0:
                        launch_success = True
                except subprocess.TimeoutExpired:
                    print(f"'gio launch' timed out for {app_path}, trying fallback.")
                    
            if not launch_success:
                # Universal Fallback: parse Exec line from desktop file
                with open(app_path, 'r', encoding='utf-8', errors='ignore') as dfile:
                    for line in dfile:
                        if line.startswith("Exec="):
                            raw_exec = line.strip().split("=", 1)[1]
                            # Remove desktop specifier arguments like %U, %f, etc.
                            clean_exec = ' '.join([arg for arg in shlex.split(raw_exec) if not arg.startswith('%')])
                            subprocess.Popen(shlex.split(clean_exec),
                                             stdout=subprocess.DEVNULL, 
                                             stderr=subprocess.DEVNULL,
                                             start_new_session=True)
                            break
        except Exception as e:
            print(f"Failed to launch {app_path}: {e}")
            continue

        # Initial baseline wait to allow the app to begin loading
        time.sleep(5.0)
        
        # Stability check: Wait until CPU usage drops below 40%
        # We retry a maximum of 60 times (total ~120 extra seconds) to prevent infinite hanging
        retries = 0
        max_retries = 60  
        
        while retries < max_retries:
            cpu_usage = get_cpu_usage()
            print(f"Current CPU usage: {cpu_usage:.1f}%")
            
            if cpu_usage < 40.0:  # Threshold for "stable"
                print("System stable. Proceeding to next app.")
                break
                
            print("System busy, waiting for it to settle...")
            time.sleep(2.0)
            retries += 1
        else:
            # Loop exhausted without settling -- launch the next app anyway
            # rather than stalling the whole restore on one busy moment.
            print("CPU did not settle below 40% within the wait budget; launching next app anyway.")

    print("All applications restored!")

if __name__ == "__main__":
    main()

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

def main():
    # Use injected REPO_DIR so it reads from the cloned repository boundary
    REPO_DIR = "<REPO_DIR_PLACEHOLDER>"
    session_file = os.path.join(REPO_DIR, "reboot.json")
    
    if not os.path.exists(session_file):
        print("No saved session found.")
        return

    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            apps = json.load(f)
    except Exception as e:
        print(f"Error reading session file: {e}")
        return

    # Sort apps by memory usage, ascending (lightest applications launch first)
    apps.sort(key=lambda x: x.get('mem', 0))

    print(f"Found {len(apps)} applications to restore.")
    
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

    for app in apps:
        app_path = app.get('path')
        if not app_path or not os.path.exists(app_path):
            continue
            
        print(f"Launching {os.path.basename(app_path)}...")
        try:
            import shutil
            import shlex
            
            launch_success = False
            # Try 'gio launch' first (standard on GNOME/Ubuntu)
            if shutil.which('gio'):
                result = subprocess.run(['gio', 'launch', app_path], 
                                        stdout=subprocess.DEVNULL, 
                                        stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    launch_success = True
                    
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
        # We retry a maximum of 5 times (total ~10 extra seconds) to prevent infinite hanging
        retries = 0
        max_retries = 5  
        
        while retries < max_retries:
            cpu_usage = get_cpu_usage()
            print(f"Current CPU usage: {cpu_usage:.1f}%")
            
            if cpu_usage < 40.0:  # Threshold for "stable"
                print("System stable. Proceeding to next app.")
                break
                
            print("System busy, waiting for it to settle...")
            time.sleep(2.0)
            retries += 1
            
    print("All applications restored!")

if __name__ == "__main__":
    main()

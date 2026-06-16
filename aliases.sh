#!/usr/bin/env bash
# =============================================================================
#  aliases.sh -- App-Reboot
# -----------------------------------------------------------------------------
#  User-facing command(s) for App-Reboot. install.sh copies this to
#  ~/.local/bin/app-reboot/aliases.sh and sources it from ~/.bashrc, so the
#  function below is available in every new terminal.
#
#  NOTE: this file is *sourced* into your interactive shell, so it deliberately
#  does NOT use `set -e`/`set -u` (that would change your shell's behaviour).
# =============================================================================

# Project folder, baked in at install time. This is where App-Reboot keeps its
# state (reboot.json) and the optional `config` file written below.
APP_REBOOT_DIR="<REPO_DIR_PLACEHOLDER>"
# Fixed install location of the scripts (independent of the project folder).
APP_REBOOT_BIN="$HOME/.local/bin/app-reboot"

# app-reboot-cpu-limit [percent]
#   No argument  -> show the current CPU-settle threshold.
#   With argument-> set it (integer 10-100). It takes effect on your NEXT login;
#                   the restorer reads this value each time it runs (no restart
#                   needed). Lower = gentler on login (waits for a calmer CPU
#                   before launching the next app); higher = relaunches faster.
app-reboot-cpu-limit() {
    local config="$APP_REBOOT_DIR/config"

    # Getter: no argument -> show current value (default 60 if unset).
    if [ -z "${1:-}" ]; then
        local current=60
        if [ -f "$config" ]; then
            current=$(grep '^CPU_THRESHOLD=' "$config" 2>/dev/null | cut -d'=' -f2)
            current=${current:-60}
        fi
        echo -e "Current CPU-settle threshold: \033[1m${current}%\033[0m (default 60)"
        echo "To change it:  app-reboot-cpu-limit <10-100>   (e.g. app-reboot-cpu-limit 70)"
        echo "Lower waits for a calmer system before each app; higher relaunches faster."
        return 0
    fi

    # Setter: validate an integer in the sane 10-100 range.
    if ! [[ "$1" =~ ^[0-9]+$ ]] || [ "$1" -lt 10 ] || [ "$1" -gt 100 ]; then
        echo -e "\033[0;31mInvalid value '$1'.\033[0m Use an integer from 10 to 100 (percent)."
        return 1
    fi

    # Guard: the baked-in folder must still exist (it holds the config file).
    if [ ! -d "$APP_REBOOT_DIR" ]; then
        echo -e "\033[0;31mapp-reboot: project folder '$APP_REBOOT_DIR' not found (moved or deleted).\033[0m" >&2
        echo "Re-run install.sh from its new location." >&2
        return 1
    fi

    printf 'CPU_THRESHOLD=%s\n' "$1" > "$config"
    echo "CPU-settle threshold set to ${1}%. Takes effect on your next login."
}

# Save your current session right now (same as what runs automatically).
app-reboot-save() {
    "$APP_REBOOT_BIN/saver.py"
}

# Re-open the saved session right now. Normally happens automatically at login;
# running it mid-session will re-launch the saved apps (may duplicate ones you
# already have open).
app-reboot-restore() {
    "$APP_REBOOT_BIN/restorer.py"
}

# List what's currently saved for the next boot.
app-reboot-saved() {
    local f="$APP_REBOOT_DIR/reboot.json"
    if [ ! -f "$f" ]; then
        echo "No saved session yet ($f)."
        return 1
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$f" <<'PY'
import json, os, sys
d = json.load(open(sys.argv[1]))
apps = d.get("apps", []); terms = d.get("gnome_terminal_sessions", [])
print(f"Saved session: {len(apps)} app(s), {len(terms)} terminal(s)")
for a in apps:
    print("  -", os.path.basename(a.get("path", "?")))
for t in terms:
    cwd = t.get("cwd") if isinstance(t, dict) else t
    cmds = t.get("running_commands", []) if isinstance(t, dict) else []
    print("  - terminal:", cwd, ("(" + ", ".join(cmds) + ")") if cmds else "")
PY
    else
        cat "$f"
    fi
}

# Show the available App-Reboot commands.
app-reboot-help() {
    cat <<'HELP'
App-Reboot commands:
  app-reboot-help              Show this help.
  app-reboot-cpu-limit [n]     Show, or set (10-100), the CPU-settle threshold
                               used while restoring apps. Takes effect next login.
  app-reboot-save              Save your current session right now.
  app-reboot-restore           Re-open the saved session right now.
  app-reboot-saved             List what's currently saved for next boot.

App-Reboot otherwise runs automatically: it saves your open apps and terminals
on logout (and every couple of minutes as a safety net), and restores them when
you log back in.
HELP
}

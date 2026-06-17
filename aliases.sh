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

# --- internal config helpers (KEY=value in the project folder's `config`) ----
# Read one KEY, echoing its value or DEFAULT.
_app_reboot_config_get() {  # KEY DEFAULT
    local config="$APP_REBOOT_DIR/config" v=""
    [ -f "$config" ] && v=$(grep "^$1=" "$config" 2>/dev/null | tail -1 | cut -d'=' -f2)
    echo "${v:-$2}"
}
# Upsert one KEY without clobbering the others (the file holds several settings).
_app_reboot_config_set() {  # KEY VALUE
    local config="$APP_REBOOT_DIR/config"
    if [ ! -d "$APP_REBOOT_DIR" ]; then
        echo -e "\033[0;31mapp-reboot: project folder '$APP_REBOOT_DIR' not found (moved or deleted).\033[0m" >&2
        echo "Re-run install.sh from its new location." >&2
        return 1
    fi
    touch "$config"
    if grep -q "^$1=" "$config"; then
        sed -i "s|^$1=.*|$1=$2|" "$config"
    else
        printf '%s=%s\n' "$1" "$2" >> "$config"
    fi
}
# Generic "show or set an integer setting" command body.
_app_reboot_num_command() {  # KEY DEFAULT MIN MAX LABEL UNIT [VALUE]
    local key="$1" def="$2" lo="$3" hi="$4" label="$5" unit="$6" val="${7:-}"
    if [ -z "$val" ]; then
        echo -e "Current ${label}: \033[1m$(_app_reboot_config_get "$key" "$def")${unit}\033[0m (default ${def}${unit})"
        return 0
    fi
    if ! [[ "$val" =~ ^[0-9]+$ ]] || [ "$val" -lt "$lo" ] || [ "$val" -gt "$hi" ]; then
        echo -e "\033[0;31mInvalid value '$val'.\033[0m Use an integer from ${lo} to ${hi}."
        return 1
    fi
    _app_reboot_config_set "$key" "$val" || return 1
    echo "${label} set to ${val}${unit}. Takes effect on your next login."
}

# Each command: no argument shows the current value; an argument sets it. All
# take effect on the NEXT login (the restorer re-reads them each run).
#   app-reboot-cpu-limit <10-100>  launch next app once CPU is below this %
#   app-reboot-app-wait  <0-120>   max seconds to wait for that settle per app
#   app-reboot-pause     <0-30>    pause (seconds) after launching each app
app-reboot-cpu-limit() { _app_reboot_num_command CPU_THRESHOLD 60 10 100 "CPU-settle threshold" "%" "${1:-}"; }
app-reboot-app-wait()  { _app_reboot_num_command APP_WAIT      15  0 120 "per-app wait cap"      "s" "${1:-}"; }
app-reboot-pause()     { _app_reboot_num_command PAUSE          3  0  30 "post-launch pause"     "s" "${1:-}"; }

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
  app-reboot-cpu-limit [n]     Show/set (10-100) the CPU % to wait below before
                               launching the next app while restoring.
  app-reboot-app-wait [secs]   Show/set (0-120) the max seconds to wait for that
                               settle per app (lower = faster restore).
  app-reboot-pause [secs]      Show/set (0-30) the pause after launching each app.
  app-reboot-save              Save your current session right now.
  app-reboot-restore           Re-open the saved session right now.
  app-reboot-saved             List what's currently saved for next boot.

The three tunables take effect on your next login. App-Reboot otherwise runs
automatically: it saves your open apps and terminals on logout (and every couple
of minutes as a safety net), and restores them when you log back in.
HELP
}

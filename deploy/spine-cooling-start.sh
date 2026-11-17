#!/bin/bash
# Start the spine-cooling UI once when the desktop session starts.
# Closing the window leaves it closed until the next boot.
# Installed by deploy/install-boot.sh. Do not run this over SSH.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

LOG="$ROOT/logs/autostart.log"
PIDFILE="$ROOT/logs/autostart.pid"
DISABLE="$ROOT/logs/autostart.disabled"
SHUTDOWN_EXIT=86
# Changes on every boot, including after the power cable is pulled.
BOOT_ID=""
if [[ -r /proc/sys/kernel/random/boot_id ]]; then
  BOOT_ID="$(tr -d '[:space:]' < /proc/sys/kernel/random/boot_id)"
fi

# True when pid is this launcher or the UI process, not a recycled pid.
our_process() {
  local pid="$1"
  local cmd=""
  [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || return 1
  cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  [[ "$cmd" == *spine-cooling-start.sh* || "$cmd" == *"src/main.py"* ]]
}

# Pid file is "<boot id>\n<pid>". A power cut leaves the previous boot's pid
# on disk, and Linux may give that number to an unrelated process.
if [[ -f "$PIDFILE" ]]; then
  old_boot="$(sed -n '1p' "$PIDFILE" 2>/dev/null || true)"
  old_pid="$(sed -n '2p' "$PIDFILE" 2>/dev/null || true)"
  old_boot="$(printf '%s' "$old_boot" | tr -d '[:space:]')"
  old_pid="$(printf '%s' "$old_pid" | tr -d '[:space:]')"
  # Older files were a single line containing only the pid.
  if [[ -z "$old_pid" && "$old_boot" =~ ^[0-9]+$ ]]; then
    old_pid="$old_boot"
    old_boot=""
  fi
  if our_process "$old_pid" && { [[ -z "$old_boot" ]] || [[ "$old_boot" == "$BOOT_ID" ]]; }; then
    echo "$(date -Is) already running (pid $old_pid)" >>"$LOG"
    exit 0
  fi
fi
printf '%s\n%s\n' "$BOOT_ID" "$$" >"$PIDFILE"

if [[ -x "$ROOT/venv/bin/python" ]]; then
  PY="$ROOT/venv/bin/python"
else
  PY="$(command -v python3)"
fi

# The desktop is up, but the compositor and pigpio need a moment after login.
sleep 3
for _ in $(seq 1 30); do
  if [[ -S /run/pigpio.sock || -S /var/run/pigpio.sock ]]; then
    break
  fi
  if command -v pigs >/dev/null 2>&1 && pigs t >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [[ -f "$LOG" ]]; then
  size="$(stat -c%s "$LOG" 2>/dev/null || echo 0)"
  if [[ "$size" -gt 5000000 ]]; then
    mv "$LOG" "$LOG.1"
  fi
fi

if [[ -f "$DISABLE" ]]; then
  echo "$(date -Is) autostart disabled" >>"$LOG"
  rm -f "$PIDFILE"
  exit 0
fi

echo "$(date -Is) starting $PY" >>"$LOG"
"$PY" "$ROOT/src/main.py" >>"$LOG" 2>&1
code=$?
rm -f "$PIDFILE"
if [[ "$code" -eq "$SHUTDOWN_EXIT" ]]; then
  echo "$(date -Is) shutdown requested" >>"$LOG"
else
  echo "$(date -Is) exited $code" >>"$LOG"
fi
exit 0

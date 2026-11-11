#!/bin/bash
# Start the spine-cooling UI for a desktop session and bring it back if it exits.
# Installed by deploy/install-boot.sh. Do not run this over SSH.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

LOG="$ROOT/logs/autostart.log"
PIDFILE="$ROOT/logs/autostart.pid"
DISABLE="$ROOT/logs/autostart.disabled"
SHUTDOWN_EXIT=86

if [[ -f "$PIDFILE" ]]; then
  old_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "$(date -Is) already running (pid $old_pid)" >>"$LOG"
    exit 0
  fi
fi
echo $$ >"$PIDFILE"

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

echo "$(date -Is) starting $PY" >>"$LOG"

while true; do
  if [[ -f "$DISABLE" ]]; then
    echo "$(date -Is) autostart disabled" >>"$LOG"
    rm -f "$PIDFILE"
    exit 0
  fi
  "$PY" "$ROOT/src/main.py" >>"$LOG" 2>&1
  code=$?
  if [[ "$code" -eq "$SHUTDOWN_EXIT" ]]; then
    echo "$(date -Is) shutdown requested, not restarting" >>"$LOG"
    rm -f "$PIDFILE"
    exit 0
  fi
  echo "$(date -Is) exited $code, restarting in 3s" >>"$LOG"
  sleep 3
done

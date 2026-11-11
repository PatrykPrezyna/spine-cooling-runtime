#!/bin/bash
# One-time setup so the spine-cooling UI opens at boot with no one at the keyboard.
# Run on the Raspberry Pi, as the person who uses the touchscreen:
#   bash deploy/install-boot.sh
# Remove it with:
#   bash deploy/install-boot.sh --remove

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
START="$ROOT/deploy/spine-cooling-start.sh"

if [[ "$(id -u)" -eq 0 && -z "${SUDO_USER:-}" ]]; then
  echo "Run this as the desktop user, not as a root login: bash deploy/install-boot.sh"
  exit 1
fi

DESKTOP_USER="${SUDO_USER:-$USER}"
DESKTOP_HOME="$(getent passwd "$DESKTOP_USER" | cut -d: -f6)"
AUTOSTART_DIR="$DESKTOP_HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/spine-cooling.desktop"

remove_autostart() {
  rm -f "$DESKTOP_FILE"
  touch "$ROOT/logs/autostart.disabled"
  if [[ -f "$ROOT/logs/autostart.pid" ]]; then
    old_pid="$(cat "$ROOT/logs/autostart.pid" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]]; then
      kill "$old_pid" 2>/dev/null || true
    fi
  fi
  echo "Removed desktop autostart for $DESKTOP_USER."
  echo "Desktop auto-login and pigpiod were left as they are."
}

if [[ "${1:-}" == "--remove" ]]; then
  remove_autostart
  exit 0
fi

if [[ ! -x "$ROOT/venv/bin/python" ]]; then
  echo "No virtualenv at $ROOT/venv."
  echo "Create it first: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

chmod +x "$START"
rm -f "$ROOT/logs/autostart.disabled"
mkdir -p "$AUTOSTART_DIR"
cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Spine Cooling Runtime
Comment=Spine cooling device, started with the desktop
Exec=/bin/bash "$START"
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
chown -R "$DESKTOP_USER:" "$AUTOSTART_DIR"

echo "Enabling pigpiod so the pump is ready before the UI."
sudo systemctl enable --now pigpiod

if command -v raspi-config >/dev/null 2>&1; then
  echo "Setting boot to the desktop, logged in as $DESKTOP_USER."
  sudo raspi-config nonint do_boot_behaviour B4
else
  echo "raspi-config is not installed. In Raspberry Pi Configuration, set boot to Desktop Autologin."
fi

echo
echo "Installed. Reboot once: sudo reboot"
echo "After that the touchscreen UI opens by itself. Output is in logs/autostart.log."
echo "To stop launching at boot: bash deploy/install-boot.sh --remove"

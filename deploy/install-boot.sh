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

# Raspberry Pi OS Trixie dropped the pigpio apt package, and `make install`
# does not add pigpiod.service. systemctl then reports that the unit does not exist.
pigpiod_unit_present() {
  systemctl cat pigpiod.service >/dev/null 2>&1
}

pigpiod_bin() {
  if command -v pigpiod >/dev/null 2>&1; then
    command -v pigpiod
    return 0
  fi
  if [[ -x /usr/local/bin/pigpiod ]]; then
    echo /usr/local/bin/pigpiod
    return 0
  fi
  if [[ -x /usr/bin/pigpiod ]]; then
    echo /usr/bin/pigpiod
    return 0
  fi
  return 1
}

install_pigpiod_unit() {
  local bin="$1"
  echo "Writing /etc/systemd/system/pigpiod.service for $bin."
  sudo tee /etc/systemd/system/pigpiod.service >/dev/null <<EOF
[Unit]
Description=Daemon required to control GPIO pins via pigpio
After=network.target

[Service]
Type=forking
ExecStart=$bin -l
ExecStop=/bin/systemctl kill pigpiod

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
}

build_pigpio() {
  local src="/tmp/pigpio-79"
  echo "pigpio is not packaged on this image. Building pigpio v79."
  sudo apt-get update
  sudo apt-get install -y python3-setuptools python3-full python3-dev make gcc wget
  rm -rf "$src"
  wget -O /tmp/pigpio-v79.tar.gz https://github.com/joan2937/pigpio/archive/refs/tags/v79.tar.gz
  tar -C /tmp -zxf /tmp/pigpio-v79.tar.gz
  make -C "$src" -j"$(nproc)"
  sudo make -C "$src" install
  sudo ldconfig
}

ensure_pigpiod() {
  if pigpiod_unit_present; then
    return 0
  fi

  echo "pigpiod.service is not installed."
  local bin=""
  bin="$(pigpiod_bin || true)"
  if [[ -z "$bin" ]]; then
    echo "Trying apt for pigpio."
    sudo apt-get update
    sudo apt-get install -y pigpio python3-pigpio || true
    sudo systemctl daemon-reload || true
    bin="$(pigpiod_bin || true)"
  fi
  if pigpiod_unit_present; then
    return 0
  fi
  if [[ -z "$bin" ]]; then
    build_pigpio
    bin="$(pigpiod_bin || true)"
  fi
  if [[ -z "$bin" ]]; then
    echo "pigpiod is still not installed, so there is no unit to enable."
    exit 1
  fi
  install_pigpiod_unit "$bin"
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

echo "Enabling pigpiod so the pump is ready before the UI."
ensure_pigpiod
if ! sudo systemctl enable --now pigpiod; then
  echo "Could not start pigpiod. pigpio does not run on a Raspberry Pi 5."
  sudo systemctl status pigpiod --no-pager || true
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

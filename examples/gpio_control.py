"""Interactive BCM GPIO switch (pigpio).

Requires the pigpio daemon:
  sudo pigpiod

Stop the main spine-cooling app first — it also drives GPIO 6 (compressor).

Run:
  python gpio_control.py

Then type pin + on/off, for example:
  6on
  16off
  q to quit
"""

import re
import shutil
import subprocess
import sys

import pigpio

_CMD = re.compile(r"^(\d+)(on|off|high|low|hi|lo)$")
_MODE_NAMES = {
    0: "INPUT",
    1: "OUTPUT",
    2: "ALT5",
    3: "ALT4",
    4: "ALT0",
    5: "ALT1",
    6: "ALT2",
    7: "ALT3",
}


def _level_from_word(word: str) -> int:
    return 0 if word in ("off", "low", "lo") else 1


def _mode_name(pi: pigpio.pi, pin: int) -> str:
    mode = pi.get_mode(pin)
    return f"{_MODE_NAMES.get(mode, str(mode))}({mode})"


def _pinctrl_drive(pin: int, level: int) -> bool:
    """Bookworm/Trixie fallback if pigpio write does not stick."""
    pinctrl = shutil.which("pinctrl")
    if pinctrl is None:
        return False
    drive = "dh" if level else "dl"
    result = subprocess.run(
        [pinctrl, "set", str(pin), "op", "pn", drive],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _force_output(pi: pigpio.pi, pin: int, level: int) -> None:
    # Leftover stepper waves / PWM from the main app can leave a pin stuck.
    try:
        pi.wave_tx_stop()
    except Exception:
        pass
    try:
        pi.set_PWM_dutycycle(pin, 0)
    except Exception:
        pass
    try:
        pi.set_servo_pulsewidth(pin, 0)
    except Exception:
        pass
    try:
        pi.set_pad_strength(0, 16)
    except Exception:
        pass

    rc_mode = pi.set_mode(pin, pigpio.OUTPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_OFF)
    rc_write = pi.write(pin, 1 if level else 0)
    mask = 1 << pin
    if level:
        pi.set_bank_1(mask)
    else:
        pi.clear_bank_1(mask)

    mode = _mode_name(pi, pin)
    got = pi.read(pin)
    word = "HIGH" if got else "LOW"
    print(
        f"GPIO {pin}: wrote {level}  read {got} {word}  mode={mode}  "
        f"set_mode={rc_mode} write={rc_write}"
    )
    if got == level and pi.get_mode(pin) == pigpio.OUTPUT:
        return

    if _pinctrl_drive(pin, level):
        got = pi.read(pin)
        word = "HIGH" if got else "LOW"
        print(f"GPIO {pin}: pinctrl fallback, now read {got} {word}")
        if got == level:
            return

    print(
        f"GPIO {pin} did not go to {level}. A ~2.4 V reading means the pin is "
        "not a solid LOW (another process, overlay, or LED/optocoupler load). "
        "Stop the main app, then: sudo systemctl restart pigpiod"
    )


def _set_pin(pi: pigpio.pi, pin: int, level: int) -> None:
    if pin < 0 or pin > 27:
        print(f"GPIO {pin} is out of range (0-27)")
        return
    _force_output(pi, pin, level)


def main() -> int:
    pi = pigpio.pi()
    if not pi.connected:
        print("pigpio daemon is not running. Start it with: sudo pigpiod", file=sys.stderr)
        return 1

    try:
        print("Stop the cooling app first if testing GPIO 6 (compressor).")
        print("type 6on / 16off (BCM pin + on|off), q to quit")
        while True:
            try:
                line = input("> ").strip().lower()
            except EOFError:
                print()
                break
            if not line:
                continue
            if line in ("q", "quit", "exit"):
                break
            match = _CMD.fullmatch(line.replace(" ", ""))
            if match is None:
                print("use e.g. 6on or 16off")
                continue
            pin = int(match.group(1))
            level = _level_from_word(match.group(2))
            _set_pin(pi, pin, level)
        return 0
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        pi.stop()


if __name__ == "__main__":
    sys.exit(main())

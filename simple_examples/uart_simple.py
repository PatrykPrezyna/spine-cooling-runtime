"""UART communication for RX2309(12A)-COMP compressor controller.

Usage:
  python uart_simple.py [port] [baudrate] [speed_rpm]

  port       Serial port (default: /dev/ttyS0)
  baudrate   Baud rate   (default: 600)
  speed_rpm  Target RPM  (default: 2400, min safe value per spec is ~1800)

Examples:
  python uart_simple.py /dev/ttyS0 600 3000
  python uart_simple.py /dev/serial0 600 2400
"""

from __future__ import annotations

import sys
import time

import serial  # type: ignore

# ── Protocol constants ────────────────────────────────────────────────────────
FRAME_LEN       = 16
MASTER_ADDR     = 0x00
SLAVE_ADDR      = 0x01
START_CODE      = 0xAA
END_CODE        = 0x55

# ── Timing (spec: master sends every 1000 ms, slave replies after 20 ms) ──────
FRAME_PERIOD_S      = 1.0
REPLY_DELAY_S       = 0.030   # 30 ms — generous but not wasteful
SERIAL_TIMEOUT_S    = 0.50    # 16 bytes @ 600 baud ≈ 267 ms; 500 ms is safe
READ_RETRIES        = 3
READ_RETRY_DELAY_S  = 0.020

# ── Fault bit definitions (response byte 9 and byte 13) ──────────────────────
FAULT_BITS: dict[int, str] = {
    0: "Software overcurrent",
    1: "Overvoltage protection",
    2: "Undervoltage protection",
    3: "Phase loss protection",
    4: "Stall protection",
    5: "Hardware overcurrent",
    6: "Abnormal phase current",
}

# ── Safe operating range per spec ────────────────────────────────────────────
MIN_SAFE_RPM = 1800
MAX_SAFE_RPM = 6500


# ── Helpers ───────────────────────────────────────────────────────────────────

def checksum(frame: bytes | bytearray) -> int:
    """Two's complement of the sum of bytes 1..13 (spec: reverse + 1)."""
    return (-sum(frame[1:14])) & 0xFF


def build_frame(on: bool, speed_rpm: int) -> bytes:
    """Build a 16-byte command frame.

    Args:
        on:        True = compressor ON, False = OFF.
        speed_rpm: Target speed in RPM (will be clamped to safe range).
    """
    if on:
        speed_rpm = max(MIN_SAFE_RPM, min(MAX_SAFE_RPM, speed_rpm))
    else:
        speed_rpm = 0

    frame = bytearray(FRAME_LEN)
    frame[0]  = START_CODE
    frame[1]  = MASTER_ADDR
    frame[2]  = 0x01 if on else 0x00   # Bit0: 1=on, 0=off
    frame[3]  = speed_rpm & 0xFF        # speed low byte
    frame[4]  = (speed_rpm >> 8) & 0xFF # speed high byte
    # bytes 5..13 stay 0x00 (reserved)
    frame[14] = checksum(frame)
    frame[15] = END_CODE
    return bytes(frame)


def validate_reply(frame: bytes) -> str:
    """Check framing and checksum. Returns 'OK' or a description of the fault."""
    if len(frame) != FRAME_LEN:
        return f"BAD length={len(frame)}"
    if frame[0] != START_CODE:
        return f"BAD start=0x{frame[0]:02X}"
    if frame[1] != SLAVE_ADDR:
        return f"BAD addr=0x{frame[1]:02X}"
    if frame[15] != END_CODE:
        return f"BAD end=0x{frame[15]:02X}"
    expected = checksum(frame)
    if frame[14] != expected:
        return f"BAD checksum got=0x{frame[14]:02X} expected=0x{expected:02X}"
    return "OK"


def decode_telemetry(frame: bytes) -> dict:
    """Extract telemetry values from a valid slave reply frame."""
    actual_rpm   = frame[2] | (frame[3] << 8)
    current_a    = (frame[4] | (frame[5] << 8)) * 0.1   # 0.1 A precision
    voltage_v    = (frame[6] | (frame[7] << 8)) * 0.1   # 0.1 V precision

    # Byte 9: persistent faults (cleared on compressor start)
    # Byte 13: auto-clearing faults (cleared 120 s after upper computer reads)
    persistent_faults    = [msg for bit, msg in FAULT_BITS.items() if frame[9]  & (1 << bit)]
    auto_clear_faults    = [msg for bit, msg in FAULT_BITS.items() if frame[13] & (1 << bit)]

    return {
        "rpm":               actual_rpm,
        "current_a":         current_a,
        "voltage_v":         voltage_v,
        "persistent_faults": persistent_faults,
        "auto_clear_faults": auto_clear_faults,
    }


def read_reply(ser: serial.Serial) -> bytes:
    """Read one 16-byte reply frame with retries.

    Note: buffer is NOT cleared before writing so that late replies from a
    previous cycle can still be caught by validate_reply rather than silently
    dropped.
    """
    rx = b""
    for _ in range(READ_RETRIES):
        chunk = ser.read(FRAME_LEN - len(rx))
        if chunk:
            rx += chunk
        if len(rx) >= FRAME_LEN:
            break
        time.sleep(READ_RETRY_DELAY_S)
    return rx


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    port      = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
    baudrate  = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    speed_rpm = int(sys.argv[3]) if len(sys.argv) > 3 else 2400

    print(f"Opening {port} @ {baudrate} baud | target speed: {speed_rpm} RPM")
    print("Press Ctrl+C to stop.\n")

    try:
        with serial.Serial(
            port         = port,
            baudrate     = baudrate,
            bytesize     = serial.EIGHTBITS,
            parity       = serial.PARITY_NONE,
            stopbits     = serial.STOPBITS_ONE,
            timeout      = SERIAL_TIMEOUT_S,   # FIX: was 1.0 → caused up to 3 s blocking on retry
            write_timeout= 1.0,
        ) as ser:

            while True:
                cycle_start = time.monotonic()

                # Build frame each cycle — allows speed/on changes at runtime
                tx = build_frame(on=True, speed_rpm=speed_rpm)

                ser.write(tx)
                ser.flush()

                # NOTE: reset_input_buffer() removed — it silently dropped late
                # replies; validate_reply() handles stale/corrupt frames instead.
                time.sleep(REPLY_DELAY_S)

                rx     = read_reply(ser)
                status = validate_reply(rx)

                # ── Print TX/RX hex ───────────────────────────────────────────
                print("TX:", " ".join(f"{b:02X}" for b in tx))
                print("RX:", " ".join(f"{b:02X}" for b in rx) if rx else "<no data>")
                print("Status:", status)

                # ── Print decoded telemetry on good frames ────────────────────
                if status == "OK":
                    t = decode_telemetry(rx)
                    print(
                        f"  Speed:   {t['rpm']} RPM\n"
                        f"  Current: {t['current_a']:.1f} A\n"
                        f"  Voltage: {t['voltage_v']:.1f} V"
                    )
                    if t["persistent_faults"]:
                        print("  ⚠ Persistent faults:", ", ".join(t["persistent_faults"]))
                    if t["auto_clear_faults"]:
                        print("  ⚠ Auto-clear faults:", ", ".join(t["auto_clear_faults"]))

                print("-" * 40)

                # ── Hold the 1000 ms cycle period ────────────────────────────
                elapsed    = time.monotonic() - cycle_start
                sleep_left = FRAME_PERIOD_S - elapsed
                if sleep_left > 0:
                    time.sleep(sleep_left)

    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except serial.SerialException as exc:
        print(f"Serial error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
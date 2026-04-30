import argparse
import time
import pigpio

# TB6600 pin mapping (BCM)
PUL = 5
DIR = 25
ENA = 24

# Motor config
FULL_STEPS_PER_REV = 200
DEFAULT_MICROSTEPS = 4
ROTATIONS = 10


def _frequency_from_rpm(rpm: float, microsteps_per_rev: int) -> float:
    """Convert RPM to pulse frequency in Hz."""
    return (rpm / 60.0) * microsteps_per_rev


def _send_pulses_wave(pi: pigpio.pi, step_pin: int, frequency_hz: float, pulse_count: int):
    """
    Send an exact number of step pulses using pigpio DMA-timed waves.
    """
    if pulse_count <= 0:
        return

    # Keep pulse widths valid and close to 50% duty cycle.
    period_us = max(4, int(round(1_000_000.0 / frequency_hz)))
    high_us = max(2, period_us // 2)
    low_us = max(2, period_us - high_us)

    base_pair = [
        pigpio.pulse(1 << step_pin, 0, high_us),
        pigpio.pulse(0, 1 << step_pin, low_us),
    ]

    # Chunk for memory safety.
    remaining = pulse_count
    max_chunk_pulses = 1200
    while remaining > 0:
        chunk = min(max_chunk_pulses, remaining)
        pi.wave_clear()
        pi.wave_add_generic(base_pair * chunk)
        wave_id = pi.wave_create()
        if wave_id < 0:
            raise RuntimeError(f"pigpio wave_create failed with code {wave_id}")
        pi.wave_send_once(wave_id)
        while pi.wave_tx_busy():
            time.sleep(0.001)
        pi.wave_delete(wave_id)
        remaining -= chunk


def move_fixed_rotations(speed_rpm: float, ramp_rotations: float, start_rpm: float, microsteps: int):
    """
    Move the motor 10 rotations in one direction at the given speed.
    """
    microsteps_per_rev = FULL_STEPS_PER_REV * microsteps
    total_pulses = ROTATIONS * microsteps_per_rev

    ramp_pulses = int(max(0, min(total_pulses, round(ramp_rotations * microsteps_per_rev))))
    cruise_pulses = total_pulses - ramp_pulses

    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError("Cannot connect to pigpio daemon. Start it with: sudo pigpiod")

    pi.set_mode(PUL, pigpio.OUTPUT)
    pi.set_mode(DIR, pigpio.OUTPUT)
    pi.set_mode(ENA, pigpio.OUTPUT)

    try:
        # Enable driver (kept same polarity as your current script).
        pi.write(ENA, 0)
        pi.write(DIR, 0)  # One fixed direction

        print(f"Speed: {speed_rpm:.1f} RPM")
        print(f"Ramp: {ramp_rotations:.2f} rotations")
        print(f"Ramp start speed: {start_rpm:.1f} RPM")
        print(f"Microsteps/rev: {microsteps_per_rev}")
        print(f"Total pulses: {total_pulses}")

        # Linear ramp split into small constant-frequency blocks.
        if ramp_pulses > 0:
            ramp_blocks = min(50, ramp_pulses)
            for block in range(ramp_blocks):
                start_idx = (block * ramp_pulses) // ramp_blocks
                end_idx = ((block + 1) * ramp_pulses) // ramp_blocks
                block_pulses = end_idx - start_idx
                if block_pulses <= 0:
                    continue
                alpha = (block + 1) / float(ramp_blocks)
                block_rpm = start_rpm + (speed_rpm - start_rpm) * alpha
                block_freq = _frequency_from_rpm(block_rpm, microsteps_per_rev)
                _send_pulses_wave(pi, PUL, block_freq, block_pulses)

        if cruise_pulses > 0:
            cruise_freq = _frequency_from_rpm(speed_rpm, microsteps_per_rev)
            _send_pulses_wave(pi, PUL, cruise_freq, cruise_pulses)

        pi.write(ENA, 1)  # Disable driver
        print("Done: moved 10 rotations.")
    finally:
        pi.wave_clear()
        pi.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Move TB6600 stepper 10 rotations in one direction."
    )
    parser.add_argument(
        "--speed-rpm",
        "--speed_rpm",
        "--rpm",
        "--speed",
        dest="speed_rpm",
        type=float,
        default=60.0,
        help="Motor speed in RPM (default: 60).",
    )
    parser.add_argument(
        "--ramp-rotations",
        type=float,
        default=1.0,
        help="How many initial rotations to use for speed ramp-up (default: 1.0).",
    )
    parser.add_argument(
        "--start-rpm",
        type=float,
        default=10.0,
        help="Starting RPM for ramp-up phase (default: 10).",
    )
    parser.add_argument(
        "--microsteps",
        type=int,
        default=DEFAULT_MICROSTEPS,
        help="Microsteps per full step (default: 4).",
    )
    args = parser.parse_args()

    if args.speed_rpm <= 0:
        raise ValueError("speed-rpm must be > 0")
    if args.start_rpm <= 0:
        raise ValueError("start-rpm must be > 0")
    if args.start_rpm > args.speed_rpm:
        raise ValueError("start-rpm must be <= speed-rpm")
    if args.ramp_rotations < 0:
        raise ValueError("ramp-rotations must be >= 0")
    if args.microsteps <= 0:
        raise ValueError("microsteps must be > 0")
    if args.microsteps > 256:
        raise ValueError("microsteps looks too high; expected a driver setting like 1, 2, 4, 8, 16, 32...")

    move_fixed_rotations(
        args.speed_rpm,
        args.ramp_rotations,
        args.start_rpm,
        args.microsteps,
    )


if __name__ == "__main__":
    main()
from time import sleep
import argparse
import RPi.GPIO as GPIO

# TB6600 pin mapping (BCM)
PUL = 5
DIR = 25
ENA = 24

# Motor config
FULL_STEPS_PER_REV = 200
DEFAULT_MICROSTEPS = 4
ROTATIONS = 10


def _pulse_delay_from_rpm(rpm: float, microsteps_per_rev: int) -> float:
    """Convert RPM to half-period delay for HIGH/LOW pulse toggling."""
    pulses_per_second = (rpm / 60.0) * microsteps_per_rev
    return 1.0 / (2.0 * pulses_per_second)


def move_fixed_rotations(speed_rpm: float, ramp_rotations: float, start_rpm: float, microsteps: int):
    """
    Move the motor 10 rotations in one direction at the given speed.
    """
    microsteps_per_rev = FULL_STEPS_PER_REV * microsteps
    total_pulses = ROTATIONS * microsteps_per_rev

    ramp_pulses = int(max(0, min(total_pulses, ramp_rotations * microsteps_per_rev)))

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PUL, GPIO.OUT)
    GPIO.setup(DIR, GPIO.OUT)
    GPIO.setup(ENA, GPIO.OUT)

    try:
        # Enable driver (kept same polarity as your current script).
        GPIO.output(ENA, GPIO.LOW)
        GPIO.output(DIR, GPIO.LOW)  # One fixed direction

        print(f"Speed: {speed_rpm:.1f} RPM")
        print(f"Ramp: {ramp_rotations:.2f} rotations")
        print(f"Ramp start speed: {start_rpm:.1f} RPM")
        print(f"Microsteps/rev: {microsteps_per_rev}")
        print(f"Total pulses: {total_pulses}")

        for pulse_index in range(total_pulses):
            # Linear speed ramp-up to reduce skipped steps at startup.
            if ramp_pulses > 0 and pulse_index < ramp_pulses:
                alpha = pulse_index / float(ramp_pulses)
                current_rpm = start_rpm + (speed_rpm - start_rpm) * alpha
            else:
                current_rpm = speed_rpm
            pulse_delay = _pulse_delay_from_rpm(current_rpm, microsteps_per_rev)

            GPIO.output(PUL, GPIO.HIGH)
            sleep(pulse_delay)
            GPIO.output(PUL, GPIO.LOW)
            sleep(pulse_delay)

        GPIO.output(ENA, GPIO.HIGH)  # Disable driver
        print("Done: moved 10 rotations.")
    finally:
        GPIO.cleanup()


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

    move_fixed_rotations(
        args.speed_rpm,
        args.ramp_rotations,
        args.start_rpm,
        args.microsteps,
    )


if __name__ == "__main__":
    main()
from time import sleep
import argparse
import RPi.GPIO as GPIO

# TB6600 pin mapping (BCM)
PUL = 5
DIR = 25
ENA = 24

# Motor config
FULL_STEPS_PER_REV = 200
MICROSTEPS = 8
ROTATIONS = 10


def move_fixed_rotations(speed_rpm: float):
    """
    Move the motor 10 rotations in one direction at the given speed.
    """
    microsteps_per_rev = FULL_STEPS_PER_REV * MICROSTEPS
    total_pulses = ROTATIONS * microsteps_per_rev

    # Pulse frequency from RPM:
    # pulses/sec = (RPM / 60) * microsteps_per_rev
    pulses_per_second = (speed_rpm / 60.0) * microsteps_per_rev
    pulse_delay = 1.0 / (2.0 * pulses_per_second)  # HIGH + LOW make one pulse

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PUL, GPIO.OUT)
    GPIO.setup(DIR, GPIO.OUT)
    GPIO.setup(ENA, GPIO.OUT)

    try:
        # Enable driver (kept same polarity as your current script).
        GPIO.output(ENA, GPIO.LOW)
        GPIO.output(DIR, GPIO.LOW)  # One fixed direction

        print(f"Speed: {speed_rpm:.1f} RPM")
        print(f"Microsteps/rev: {microsteps_per_rev}")
        print(f"Total pulses: {total_pulses}")

        for _ in range(total_pulses):
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
    args = parser.parse_args()

    if args.speed_rpm <= 0:
        raise ValueError("speed-rpm must be > 0")

    move_fixed_rotations(args.speed_rpm)


if __name__ == "__main__":
    main()
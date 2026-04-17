import RPi.GPIO as GPIO
import time

# Set up GPIO mode
GPIO.setmode(GPIO.BCM)
GPIO.setup(14, GPIO.IN)

print("Reading GPIO 14 continuously (Press Ctrl+C to stop)...\n")

try:
    while True:
        state = GPIO.input(14)
        state_text = "HIGH" if state == 1 else "LOW"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] GPIO 14: {state_text} ({state})")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nProgram stopped")
finally:
    GPIO.cleanup()
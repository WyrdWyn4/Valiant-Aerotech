"""
Servo calibration script for camera orientation (SERVO9 / RC11 / dial S1).

Run this once with the flight controller powered on and the transmitter bound.
The script walks you through moving dial S1 to both extremes and records the
actual PWM values from SERVO_OUTPUT_RAW.servo9_raw.

Results are saved to a JSON file that servo_map.py reads at runtime.

Usage:
    python servo_calibrate.py                          # default: udpin:127.0.0.1:14550
    python servo_calibrate.py --connect /dev/ttyAMA0 --baud 921600
    python servo_calibrate.py --connect udpin:127.0.0.1:14560
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("MAVLINK_DIALECT", "ardupilotmega")
from pymavlink import mavutil  # type: ignore

# Where calibration results are saved by default.
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "integration" / "pipelines" / "task_one" / "configs" / "servo_calibration.json"
SERVO_CHANNEL = 9  # SERVO9 = AUX1
DEFAULT_SAMPLE_COUNT = 30  # Number of PWM readings to average per position.
SAMPLE_TIMEOUT_S = 10.0  # Max wait for enough samples.


def request_servo_stream(mav: object) -> None:
    """Ask the FC to send SERVO_OUTPUT_RAW at 10 Hz."""
    mav.mav.request_data_stream_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS,
        10,  # Hz
        1,   # start
    )


def read_servo9_pwm(mav: object, timeout: float = 2.0) -> int | None:
    """Read a single SERVO_OUTPUT_RAW message and return servo9_raw."""
    msg = mav.recv_match(type="SERVO_OUTPUT_RAW", blocking=True, timeout=timeout)
    if msg is None:
        return None
    return getattr(msg, "servo9_raw", None)


def sample_position(mav: object, label: str, sample_count: int = DEFAULT_SAMPLE_COUNT) -> tuple[float, float, list[int]]:
    """
    Collect sample_count PWM readings and return (mean, stdev, raw_samples).
    """
    print(f"\n--- Sampling '{label}' position ---")
    print(f"    Collecting {sample_count} readings...")

    samples: list[int] = []
    deadline = time.monotonic() + SAMPLE_TIMEOUT_S

    while len(samples) < sample_count and time.monotonic() < deadline:
        pwm = read_servo9_pwm(mav, timeout=1.0)
        if pwm is not None and pwm > 0:
            samples.append(pwm)
            sys.stdout.write(f"\r    [{len(samples)}/{sample_count}] latest={pwm}")
            sys.stdout.flush()

    print()  # newline after progress

    if len(samples) < 3:
        print(f"    ERROR: Only got {len(samples)} valid readings. Is SERVO9 configured?")
        sys.exit(1)

    mean = statistics.mean(samples)
    stdev = statistics.stdev(samples) if len(samples) > 1 else 0.0

    print(f"    Samples: {len(samples)}")
    print(f"    Mean:    {mean:.1f}")
    print(f"    Stdev:   {stdev:.1f}")
    print(f"    Range:   {min(samples)} - {max(samples)}")

    if stdev > 20:
        print("    WARNING: High variance. Hold the dial steady and retry if needed.")

    return mean, stdev, samples


def run_calibration(connect: str, baud: int, output: Path, sample_count: int = DEFAULT_SAMPLE_COUNT) -> None:
    print("=" * 60)
    print("  Valiant Aerotech - Camera Servo Calibration")
    print("  SERVO9 (AUX1) mapped to RC11 (dial S1)")
    print("=" * 60)
    print(f"\nConnecting to: {connect} (baud={baud})")

    mav = mavutil.mavlink_connection(connect, baud=baud)
    print("Waiting for heartbeat...")
    mav.wait_heartbeat()
    print(f"Connected: system={mav.target_system}, component={mav.target_component}")

    request_servo_stream(mav)

    # Give the stream a moment to start flowing.
    time.sleep(1.0)

    # --- Live monitor mode (optional quick check) ---
    print("\n--- Quick live check (5 readings) ---")
    print("    Current SERVO9 PWM values:")
    for i in range(5):
        pwm = read_servo9_pwm(mav, timeout=2.0)
        print(f"    [{i+1}] servo9_raw = {pwm}")
    print()

    # --- DOWN position ---
    input(
        "STEP 1: Turn dial S1 fully COUNTER-CLOCKWISE (DOWN position).\n"
        "        Hold it there and press ENTER to sample... "
    )
    down_mean, down_stdev, down_samples = sample_position(mav, "DOWN", sample_count)

    # fRONT position 
    input(
        "\nSTEP 2: Turn dial S1 fully CLOCKWISE (FRONT position).\n"
        "        Hold it there and press ENTER to sample... "
    )
    front_mean, front_stdev, front_samples = sample_position(mav, "FRONT", sample_count)

    # Compute threshold 
    pwm_down = round(down_mean)
    pwm_front = round(front_mean)
    pwm_threshold = (pwm_down + pwm_front) // 2

    # Ensure DOWN < FRONT convention; swap labels if the dial is wired in reverse.
    if pwm_down > pwm_front:
        print("\nNOTE: DOWN PWM > FRONT PWM. The dial may be wired in reverse.")
        print("      Swapping so PWM_DOWN < PWM_FRONT for threshold logic.")
        pwm_down, pwm_front = pwm_front, pwm_down
        down_mean, front_mean = front_mean, down_mean
        down_stdev, front_stdev = front_stdev, down_stdev
        down_samples, front_samples = front_samples, down_samples
        pwm_threshold = (pwm_down + pwm_front) // 2

    separation = abs(pwm_front - pwm_down)

    # Summary 
    print("\n" + "=" * 60)
    print("  CALIBRATION RESULTS")
    print("=" * 60)
    print(f"  PWM_DOWN      = {pwm_down}")
    print(f"  PWM_FRONT     = {pwm_front}")
    print(f"  PWM_THRESHOLD = {pwm_threshold}")
    print(f"  Separation    = {separation} us")
    print()

    if separation < 200:
        print("  WARNING: Low separation between positions.")
        print("  Consider checking servo endpoints or RC11 trim/range.")
    else:
        print("  Separation looks good.")

    # --- Save ---
    calibration = {
        "servo_channel": SERVO_CHANNEL,
        "rc_source": "RC11 (dial S1)",
        "pwm_down": pwm_down,
        "pwm_front": pwm_front,
        "pwm_threshold": pwm_threshold,
        "separation_us": separation,
        "down_stdev": round(down_stdev, 2),
        "front_stdev": round(front_stdev, 2),
        "down_sample_count": len(down_samples),
        "front_sample_count": len(front_samples),
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "connection": connect,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
    print(f"\n  Saved to: {output}")
    print("  servo_map.py will read this file at runtime.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate camera servo PWM positions (SERVO9 / RC11 / dial S1)."
    )
    parser.add_argument(
        "--connect",
        default="udpin:127.0.0.1:14550",
        help="MAVLink connection string (default: udpin:127.0.0.1:14550)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=921600,
        help="Baud rate for serial connections (default: 921600)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help=f"Number of PWM readings per position (default: {DEFAULT_SAMPLE_COUNT})",
    )
    args = parser.parse_args()
    run_calibration(args.connect, args.baud, args.output, args.samples)


if __name__ == "__main__":
    main()

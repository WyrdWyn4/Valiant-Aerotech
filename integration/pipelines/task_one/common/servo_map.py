"""
Camera orientation reader for Vivi (SERVO9 / RC11 / dial S1).

Reads SERVO_OUTPUT_RAW.servo9_raw via MAVLink and maps the PWM value to one of
two camera orientations:

    - "DOWN"  : camera faces the ground (dial S1 fully CCW)
    - "FRONT" : camera faces forward    (dial S1 fully CW)

Calibrated PWM values are loaded from servo_calibration.json, which is written
by the one-time calibration script (_tools/servo_calibrate.py).

This module does NOT send any MAVLink commands. It is read-only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("MAVLINK_DIALECT", "ardupilotmega")
from pymavlink import mavutil  # type: ignore

# Calibration file written by _tools/servo_calibrate.py.
_CALIBRATION_PATH = Path(__file__).resolve().parent.parent / "configs" / "servo_calibration.json"

# Fallback defaults if calibration has not been run yet.
_DEFAULT_PWM_DOWN = 1000
_DEFAULT_PWM_FRONT = 2000

SERVO_CHANNEL = 9  # SERVO9 = AUX1


def load_calibration(path: Optional[Path] = None) -> dict:
    """Load calibration values from JSON. Returns defaults if file is missing."""
    cal_path = path or _CALIBRATION_PATH
    if cal_path.exists():
        try:
            data = json.loads(cal_path.read_text(encoding="utf-8"))
            return {
                "pwm_down": int(data["pwm_down"]),
                "pwm_front": int(data["pwm_front"]),
                "pwm_threshold": int(data["pwm_threshold"]),
                "calibrated": True,
            }
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            print(f"[servo_map] WARNING: Failed to load {cal_path}: {exc}")

    # Uncalibrated fallback.
    pwm_down = _DEFAULT_PWM_DOWN
    pwm_front = _DEFAULT_PWM_FRONT
    return {
        "pwm_down": pwm_down,
        "pwm_front": pwm_front,
        "pwm_threshold": (pwm_down + pwm_front) // 2,
        "calibrated": False,
    }


class CameraOrientationReader:
    """
    Reads SERVO9 PWM from an existing MAVLink connection and returns camera
    orientation as "DOWN", "FRONT", or "UNKNOWN".

    Parameters
    ----------
    mav : mavutil.mavlink_connection
        An already-connected MAVLink connection (heartbeat received).
    calibration_path : Path, optional
        Override path to servo_calibration.json.
    request_stream : bool
        If True, send a data-stream request on init so the FC sends
        SERVO_OUTPUT_RAW messages. Set False if the stream is already active
        (e.g. when another monitor is running on the same link).
    """

    def __init__(
        self,
        mav: object,
        calibration_path: Optional[Path] = None,
        request_stream: bool = True,
    ) -> None:
        self.mav = mav
        self.cal = load_calibration(calibration_path)
        self._last_pwm: Optional[int] = None

        if not self.cal["calibrated"]:
            print(
                "[servo_map] WARNING: Using uncalibrated defaults "
                f"(DOWN={self.cal['pwm_down']}, FRONT={self.cal['pwm_front']}). "
                "Run _tools/servo_calibrate.py to measure actual values."
            )

        if request_stream:
            self._request_servo_stream()

    def _request_servo_stream(self) -> None:
        self.mav.mav.request_data_stream_send(
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS,
            10,  # Hz
            1,   # start
        )

    def get_camera_orientation(self, timeout: float = 1.0) -> str:
        """
        Block up to *timeout* seconds for a SERVO_OUTPUT_RAW message and
        return the camera orientation.

        Returns
        -------
        "DOWN", "FRONT", or "UNKNOWN"
        """
        msg = self.mav.recv_match(type="SERVO_OUTPUT_RAW", blocking=True, timeout=timeout)
        if msg is None:
            return "UNKNOWN"

        pwm = getattr(msg, "servo9_raw", 0)
        if pwm == 0:
            return "UNKNOWN"

        self._last_pwm = pwm
        return "DOWN" if pwm < self.cal["pwm_threshold"] else "FRONT"

    def get_camera_orientation_nonblocking(self) -> str:
        """
        Check for a buffered SERVO_OUTPUT_RAW without blocking. Falls back to
        the last known orientation if no new message is available.

        Returns
        -------
        "DOWN", "FRONT", or "UNKNOWN"
        """
        msg = self.mav.recv_match(type="SERVO_OUTPUT_RAW", blocking=False)
        if msg is not None:
            pwm = getattr(msg, "servo9_raw", 0)
            if pwm > 0:
                self._last_pwm = pwm

        if self._last_pwm is None:
            return "UNKNOWN"
        return "DOWN" if self._last_pwm < self.cal["pwm_threshold"] else "FRONT"

    @property
    def last_pwm(self) -> Optional[int]:
        """Most recently observed SERVO9 PWM value."""
        return self._last_pwm

    @property
    def threshold(self) -> int:
        return self.cal["pwm_threshold"]

    @property
    def is_calibrated(self) -> bool:
        return self.cal["calibrated"]


# Convenience standalone function matching the reference design in the context
# document.  Connects, reads one orientation, and returns it.


def get_camera_orientation(
    connection: str = "/dev/ttyAMA0",
    baud: int = 921600,
    timeout: float = 1.0,
) -> str:
    """
    One-shot convenience function: connect, read SERVO9, return orientation.

    For repeated use inside a long-running process, prefer
    CameraOrientationReader to avoid reconnecting each call.
    """
    mav = mavutil.mavlink_connection(connection, baud=baud)
    mav.wait_heartbeat()

    reader = CameraOrientationReader(mav, request_stream=True)
    return reader.get_camera_orientation(timeout=timeout)

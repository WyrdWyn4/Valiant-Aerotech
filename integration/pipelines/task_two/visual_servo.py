"""
visual_servo.py — PD controller converting pixel error to MAVLink velocity commands.

Converts the pixel offset of the target from frame centre into body-frame
velocity commands sent to the drone via SET_POSITION_TARGET_LOCAL_NED in
GUIDED mode.
"""

from __future__ import annotations

import time
from pymavlink import mavutil

from .config import (
    KP_X, KP_Y, KD_X, KD_Y,
    MAX_VEL, DEADBAND_PX,
    FRAME_W, FRAME_H,
)


class VisualServo:
    """Proportional-derivative visual servoing controller."""

    def __init__(self, mav_connection):
        self.mav = mav_connection
        self._last_err_x = 0.0
        self._last_err_y = 0.0
        self._last_time = time.time()

    # ── Core ──────────────────────────────────────────────────────────────

    def compute_velocity(self, cx: int, cy: int):
        """Compute correction velocities from pixel centre of detected target.

        Parameters
        ----------
        cx, cy : int
            Pixel coordinates of the target centre.

        Returns
        -------
        (vel_right, vel_vertical) : tuple[float, float]
            vel_right    – positive = drone should move right
            vel_vertical – positive = drone should move down (FRONT) or forward (DOWN)
        """
        now = time.time()
        dt = max(now - self._last_time, 1e-6)
        self._last_time = now

        # Pixel error from frame centre
        err_x = cx - FRAME_W // 2   # + = target is right of centre
        err_y = cy - FRAME_H // 2   # + = target is below centre

        # Derivative terms
        derr_x = (err_x - self._last_err_x) / dt
        derr_y = (err_y - self._last_err_y) / dt
        self._last_err_x = err_x
        self._last_err_y = err_y

        # PD control
        vel_right    = KP_X * err_x + KD_X * derr_x
        vel_vertical = KP_Y * err_y + KD_Y * derr_y

        # Clamp to safe maximum
        vel_right    = max(-MAX_VEL, min(MAX_VEL, vel_right))
        vel_vertical = max(-MAX_VEL, min(MAX_VEL, vel_vertical))

        return vel_right, vel_vertical

    def is_centered(self, cx: int, cy: int) -> bool:
        """Return True if the target is within the deadband of frame centre."""
        err_x = abs(cx - FRAME_W // 2)
        err_y = abs(cy - FRAME_H // 2)
        return err_x < DEADBAND_PX and err_y < DEADBAND_PX

    # ── MAVLink velocity commands ─────────────────────────────────────────

    def send_velocity_body(self, vel_x: float, vel_y: float, vel_z: float = 0.0):
        """Send a velocity command in body frame (NED).

        Parameters
        ----------
        vel_x : float   Forward  (positive = nose direction)
        vel_y : float   Right    (positive = starboard)
        vel_z : float   Down     (positive = descend)

        The drone MUST be in GUIDED mode for this to be accepted.
        """
        # Type mask: use velocity only — ignore position, acceleration, yaw
        type_mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_X_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_Y_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_Z_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )

        self.mav.mav.set_position_target_local_ned_send(
            0,                                     # time_boot_ms (0 = use system time)
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_NED,    # body-relative frame
            type_mask,
            0, 0, 0,       # x, y, z position  (ignored)
            vel_x, vel_y, vel_z,   # vx, vy, vz velocity
            0, 0, 0,       # ax, ay, az acceleration (ignored)
            0, 0,          # yaw, yaw_rate (ignored)
        )

    def stop(self):
        """Send zero velocity — hold current position."""
        self.send_velocity_body(0.0, 0.0, 0.0)

"""Pose and camera configuration objects."""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from .vector import Vec3


@dataclass
class Pose:
    """Vehicle pose at the exact instant the operator marks a target.

    position:
        Local ENU position of the autopilot/GPS reference point in metres.
    yaw_deg:
        Heading clockwise from north. This is needed for FRONT mode because it
        determines which wall the camera is looking toward and where the centre
        ray intersects that wall.
    pitch_deg:
        Nose-up angle. This affects the target height for FRONT mode and the
        ground intercept for DOWN mode.
    roll_deg:
        Side tilt. This affects lateral error, especially for DOWN mode.
    timestamp:
        Optional time used to match the target mark to telemetry logs.
    """

    position: Vec3
    yaw_deg: float
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CameraConfig:
    """Camera position offset relative to the autopilot/GPS reference point.

    If the camera is x cm below the GPS/autopilot origin, store that offset here.
    The offset gives the camera position. Yaw/pitch/roll still give the camera
    direction. Both are required for ray-plane projection.
    """

    # Body frame is +X forward, +Y right, +Z up. A camera 10 cm below the GPS is
    # Vec3(0, 0, -0.10).
    offset_body_m: Vec3 = Vec3(0.0, 0.0, -0.10)

    # Centre rays. Since the operator centres the target before pressing the key,
    # we use the centre ray instead of a full pixel projection model.
    front_ray_body: Vec3 = Vec3(1.0, 0.0, 0.0)
    down_ray_body: Vec3 = Vec3(0.0, 0.0, -1.0)

"""Geometry and attitude helper functions."""

from __future__ import annotations

import math

from .constants import EPS
from .modes import CameraMode
from .pose import CameraConfig, Pose
from .vector import UP, Vec3


def clamp_angle_360(deg: float) -> float:
    return deg % 360.0


def bearing_from_vector(v: Vec3) -> float:
    """Return bearing clockwise from north for a horizontal vector."""
    return clamp_angle_360(math.degrees(math.atan2(v.x, v.y)))


def cardinal_from_bearing(bearing_deg: float) -> str:
    """Map a bearing to a simple cardinal face name.

    We intentionally use simple north/east/south/west labels because the report
    should be clear to firefighters and because setup() builds a face model.
    """
    b = clamp_angle_360(bearing_deg)
    if b >= 315.0 or b < 45.0:
        return "north"
    if 45.0 <= b < 135.0:
        return "east"
    if 135.0 <= b < 225.0:
        return "south"
    return "west"


def rotate_about_axis(v: Vec3, axis: Vec3, angle_rad: float) -> Vec3:
    """Rotate vector v around axis using Rodrigues' rotation formula."""
    k = axis.normalized()
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return v * c + k.cross(v) * s + k * (k.dot(v) * (1.0 - c))


def body_to_world(v_body: Vec3, pose: Pose) -> Vec3:
    """Rotate a body-frame vector into the local ENU world frame.

    This is why yaw/pitch/roll are included: the target point is not just where
    the drone is; it is where the camera centre ray intersects a wall or the
    ground.

    Simplified interpretation:
    - yaw chooses the horizontal facing direction
    - pitch tilts the front ray up/down
    - roll tilts the right/up axes around the forward ray
    """
    yaw = math.radians(pose.yaw_deg)
    pitch = math.radians(pose.pitch_deg)
    roll = math.radians(pose.roll_deg)

    # Forward at yaw=0 points north. At yaw=90 points east.
    forward = Vec3(
        math.sin(yaw) * math.cos(pitch),
        math.cos(yaw) * math.cos(pitch),
        math.sin(pitch),
    ).normalized()

    # Level right vector before roll. At yaw=0, right points east.
    right_level = Vec3(math.cos(yaw), -math.sin(yaw), 0.0).normalized()

    # Up vector completes the local body basis.
    up_level = right_level.cross(forward).normalized()

    # Positive roll means the right side rotates downward, so right gains a
    # negative vertical component. If your autopilot reports the opposite sign,
    # invert roll_deg before creating Pose.
    right = right_level * math.cos(roll) - up_level * math.sin(roll)
    up = right_level * math.sin(roll) + up_level * math.cos(roll)

    # Body axes: +X forward, +Y right, +Z up.
    return forward * v_body.x + right * v_body.y + up * v_body.z


def camera_position_world(pose: Pose, camera: CameraConfig) -> Vec3:
    """Return camera centre position in local ENU coordinates."""
    return pose.position + body_to_world(camera.offset_body_m, pose)


def camera_centre_ray_world(pose: Pose, camera: CameraConfig, mode: CameraMode) -> Vec3:
    """Return the camera centre ray in local ENU.

    Because detect() returns only colour, this assumes the operator centred the
    target before pressing the key. If detect() later returns pixel centre, this
    should be replaced with a calibrated pixel-to-ray function.
    """
    if mode == CameraMode.FRONT:
        return body_to_world(camera.front_ray_body, pose).normalized()
    if mode == CameraMode.DOWN:
        return body_to_world(camera.down_ray_body, pose).normalized()
    raise ValueError(f"Unsupported camera mode: {mode}")


def round_dm(x: float) -> float:
    """Round to decimetre accuracy for final text.

    This avoids implying centimetre-level accuracy in the final report.
    """
    return round(float(x) + 1e-12, 1)

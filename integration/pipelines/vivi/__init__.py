"""Modular Vivi Task One target-report package.

This package is the split-up version of the original single-file vivi.py. It keeps
all public objects importable from `vivi` while storing the implementation in
smaller files.
"""

from .constants import ALLOWED_COLOURS, EPS
from .detection import TargetEvent, detect, mark_target
from .frames import LocalFrame
from .geometry import (
    bearing_from_vector,
    body_to_world,
    camera_centre_ray_world,
    camera_position_world,
    cardinal_from_bearing,
    clamp_angle_360,
    rotate_about_axis,
    round_dm,
)
from .localization import LocalizedTarget, TargetLocalizer
from .modes import CameraMode
from .model import BuildingModel, DoorReference, WallPlane
from .pose import CameraConfig, Pose
from .report import parse
from .survey import setup, survey
from .telemetry import MavlinkTelemetry, TelemetrySnapshot
from .vector import UP, Vec3

__all__ = [
    "ALLOWED_COLOURS",
    "EPS",
    "CameraMode",
    "Vec3",
    "UP",
    "Pose",
    "CameraConfig",
    "LocalFrame",
    "clamp_angle_360",
    "bearing_from_vector",
    "cardinal_from_bearing",
    "rotate_about_axis",
    "body_to_world",
    "camera_position_world",
    "camera_centre_ray_world",
    "round_dm",
    "DoorReference",
    "WallPlane",
    "BuildingModel",
    "survey",
    "setup",
    "MavlinkTelemetry",
    "TelemetrySnapshot",
    "TargetEvent",
    "LocalizedTarget",
    "detect",
    "mark_target",
    "TargetLocalizer",
    "parse",
]

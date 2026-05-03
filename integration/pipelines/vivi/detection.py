"""Detection and operator target-marking functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import time

from .constants import ALLOWED_COLOURS
from .modes import CameraMode
from .pose import Pose


@dataclass
class TargetEvent:
    """One operator-confirmed target sighting.

    detect() returns only the colour. mark_target() combines that colour with the
    pose/camera context needed by the geometry pipeline.
    """

    colour: str
    camera_mode: CameraMode
    pose: Pose
    selected_face: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    notes: str = ""


def detect(frame, detector: Optional[Callable] = None) -> str:
    """Return only the target colour.

    This is deliberately simple because detect() is only responsible for colour.
    The real CV package can be passed in as detector(frame), or this function can
    be replaced by that package.

    Expected detector outputs:
        "red"
        {"colour": "red"}
    """
    if detector is None:
        raise NotImplementedError(
            "Plug in the computer-vision detector here. It should return one of: "
            f"{sorted(ALLOWED_COLOURS)}."
        )

    result = detector(frame)
    if isinstance(result, dict):
        colour = result.get("colour")
    else:
        colour = result

    if not isinstance(colour, str):
        raise ValueError(f"detect() expected a colour string, got: {result!r}")

    colour = colour.strip().lower()
    if colour not in ALLOWED_COLOURS:
        raise ValueError(f"Invalid target colour {colour!r}. Allowed: {sorted(ALLOWED_COLOURS)}")

    return colour


def mark_target(
    colour: str,
    camera_mode: int | CameraMode,
    pose: Pose,
    *,
    selected_face: Optional[str] = None,
    notes: str = "",
) -> TargetEvent:
    """Create a target event after the operator presses the target key.

    The target must be centred in the current camera view before this function is
    called. If not, the code will still run, but the geometry will report the
    centre ray instead of the actual off-centre target.
    """
    colour = colour.strip().lower()
    if colour not in ALLOWED_COLOURS:
        raise ValueError(f"Invalid target colour {colour!r}. Allowed: {sorted(ALLOWED_COLOURS)}")

    return TargetEvent(
        colour=colour,
        camera_mode=CameraMode(camera_mode),
        pose=pose,
        selected_face=selected_face,
        timestamp=pose.timestamp,
        notes=notes,
    )

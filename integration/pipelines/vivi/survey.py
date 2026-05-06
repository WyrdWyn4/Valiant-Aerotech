"""Survey/setup functions for building and door geometry."""

from __future__ import annotations

from itertools import permutations
from pathlib import Path
from typing import Optional, Sequence
import json

from .geometry import bearing_from_vector, clamp_angle_360
from .model import BuildingModel, WallPlane
from .vector import Vec3


_CARDINAL_BEARINGS: dict[str, float] = {
    "north": 0.0,
    "east": 90.0,
    "south": 180.0,
    "west": 270.0,
}


def _angle_error_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two compass bearings."""
    return abs((clamp_angle_360(a - b + 180.0) - 180.0))


def _make_wall(p0: Vec3, p1: Vec3, centre: Vec3, height_m: float) -> WallPlane:
    """Create one wall from a bottom edge and building centre.

    The name is assigned later by _assign_unique_cardinal_names(). That avoids
    duplicate or wrong face labels when the building is rotated relative to north.
    """
    edge_mid = (p0 + p1) * 0.5

    # Outward normal points from the building centre through the wall midpoint.
    normal = (edge_mid - centre).horizontal().normalized()
    heading = bearing_from_vector(normal)

    return WallPlane(
        name="unassigned",
        p0=Vec3(p0.x, p0.y, 0.0),
        p1=Vec3(p1.x, p1.y, 0.0),
        normal=normal,
        height_m=height_m,
        heading_deg=heading,
    )


def _assign_unique_cardinal_names(walls: Sequence[WallPlane]) -> None:
    """Name each wall by the closest unique cardinal direction.

    This implements the field rule we actually want:
    - the face whose outward normal is closest to north is the north face;
    - the face closest to east is the east face;
    - the remaining faces are assigned south/west in the same way.

    Doing this as a global assignment is safer than thresholding each wall
    independently, because thresholding can create duplicate labels on rotated
    buildings or near 45-degree cases.
    """
    if len(walls) != 4:
        for i, wall in enumerate(walls, start=1):
            wall.name = f"face_{i}"
        return

    cardinal_names = list(_CARDINAL_BEARINGS.keys())
    best_assignment: tuple[float, tuple[str, ...]] | None = None

    for candidate_names in permutations(cardinal_names):
        total_error = sum(
            _angle_error_deg(wall.heading_deg, _CARDINAL_BEARINGS[name])
            for wall, name in zip(walls, candidate_names)
        )
        if best_assignment is None or total_error < best_assignment[0]:
            best_assignment = (total_error, candidate_names)

    assert best_assignment is not None
    for wall, name in zip(walls, best_assignment[1]):
        wall.name = name


def survey(
    building_corners: Sequence[Vec3],
    building_height_m: float,
    door_top_corners: Optional[Sequence[Vec3]] = None,
    *,
    door_corners: Optional[Sequence[Vec3]] = None,
    ground_z: Optional[float] = None,
    save_model_path: Optional[str | Path] = None,
) -> BuildingModel:
    """Build the local building model from three captured building corners.

    Parameters
    ----------
    building_corners:
        Exactly three adjacent building corners: A, B, C. A must be the shared
        corner; B and C must be adjacent to A along the two wall directions. The
        fourth corner is generated as D = B + C - A.

    building_height_m:
        Height used to validate wall targets and produce height descriptions.

    door_top_corners:
        Preferred door input for field use. Capture only the two top door-frame
        corners. The bottom two door corners are assumed to be on the ground.

    door_corners:
        Backward-compatible older input. If supplied, the same function accepts
        two or more points and derives the door reference from their u/z ranges.

    ground_z:
        Local ground height in the MAVLink/ENU frame. If omitted, assumes 0.0 m.
        This is correct when relative altitude is measured from the takeoff/ground
        level and building/door points are captured by flying to their height.

    save_model_path:
        Optional JSON file path to store the survey result for review/debugging.
    """
    if len(building_corners) != 3:
        raise ValueError("survey() expects exactly three building corners: A, B, C.")
    if building_height_m <= 0:
        raise ValueError("building_height_m must be positive.")

    A, B, C = building_corners
    if ground_z is None:
        ground_z = 0.0

    # Flatten building corners to the chosen ground plane. Wall targets still use
    # the vehicle/camera z for height, but the footprint itself should sit on the
    # ground plane.
    A = Vec3(A.x, A.y, ground_z)
    B = Vec3(B.x, B.y, ground_z)
    C = Vec3(C.x, C.y, ground_z)

    # Generate fourth corner. This assumes A is the shared corner and B/C are
    # adjacent corners. This is the key operator instruction for setup.
    D = B + C - A

    corners = [A, B, D, C]
    centre = Vec3(
        sum(p.x for p in corners) / 4.0,
        sum(p.y for p in corners) / 4.0,
        ground_z,
    )

    walls = [
        _make_wall(A, B, centre, building_height_m),
        _make_wall(B, D, centre, building_height_m),
        _make_wall(D, C, centre, building_height_m),
        _make_wall(C, A, centre, building_height_m),
    ]
    _assign_unique_cardinal_names(walls)

    model = BuildingModel(
        corners=corners,
        height_m=building_height_m,
        ground_z=ground_z,
        walls=walls,
    )

    # New preferred field workflow: capture only top two door corners. Keep the
    # old parameter name as a compatibility fallback.
    door_points = door_top_corners if door_top_corners is not None else door_corners
    if door_points is not None:
        model.attach_door_from_points(door_points, assume_bottom_on_ground=True)

    if save_model_path is not None:
        Path(save_model_path).write_text(json.dumps(model.to_json_dict(), indent=2), encoding="utf-8")

    return model


# Alias because the design discussion used both words.
setup = survey

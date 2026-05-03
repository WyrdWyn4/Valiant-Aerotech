"""Survey/setup functions for building and door geometry."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence
import json

from .geometry import bearing_from_vector, cardinal_from_bearing
from .model import BuildingModel, WallPlane
from .vector import Vec3


def _make_wall(p0: Vec3, p1: Vec3, centre: Vec3, height_m: float) -> WallPlane:
    """Create one wall from a bottom edge and building centre."""
    edge_mid = (p0 + p1) * 0.5

    # Outward normal points from the building centre through the wall midpoint.
    normal = (edge_mid - centre).horizontal().normalized()
    heading = bearing_from_vector(normal)
    face_name = cardinal_from_bearing(heading)

    return WallPlane(
        name=face_name,
        p0=Vec3(p0.x, p0.y, 0.0),
        p1=Vec3(p1.x, p1.y, 0.0),
        normal=normal,
        height_m=height_m,
        heading_deg=heading,
    )


def survey(
    building_corners: Sequence[Vec3],
    building_height_m: float,
    door_corners: Optional[Sequence[Vec3]] = None,
    *,
    ground_z: Optional[float] = None,
    save_model_path: Optional[str | Path] = None,
) -> BuildingModel:
    """Build the local building model from three captured building corners.

    Parameters
    ----------
    building_corners:
        Exactly three adjacent building corners: A, B, C.
        A must be the shared corner; B and C must be adjacent to A along the two
        wall directions. The fourth corner is generated as D = B + C - A.

        This is why three corners are enough for the rectangular building model:
        two adjacent edges define orientation, and the dimensions are represented
        by the measured/captured edge lengths. If the official dimensions are
        known and you want to force them, capture the corners at the correct
        ends or scale B/C before calling survey().

    building_height_m:
        Height used to validate wall targets and produce height descriptions.

    door_corners:
        Any three or four door-frame corner points. The code uses them to build a
        door reference on the nearest wall. If omitted, reports will use corners
        only.

    ground_z:
        Local ground height. If omitted, uses the average z of the three captured
        building corners.

    save_model_path:
        Optional JSON file path to store the survey result for review/debugging.
    """
    if len(building_corners) != 3:
        raise ValueError("survey() expects exactly three building corners: A, B, C.")
    if building_height_m <= 0:
        raise ValueError("building_height_m must be positive.")

    A, B, C = building_corners
    if ground_z is None:
        ground_z = (A.z + B.z + C.z) / 3.0

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

    # Guard against duplicate face names. Duplicate names usually mean the three
    # corners were captured in the wrong order, the building is highly diagonal,
    # or the cardinal naming is too coarse. We keep the model but make names
    # unique so wall lookup remains stable.
    seen: dict[str, int] = {}
    for wall in walls:
        count = seen.get(wall.name, 0)
        seen[wall.name] = count + 1
        if count:
            wall.name = f"{wall.name}_{count + 1}"

    model = BuildingModel(
        corners=corners,
        height_m=building_height_m,
        ground_z=ground_z,
        walls=walls,
    )

    if door_corners is not None:
        model.attach_door_from_points(door_corners)

    if save_model_path is not None:
        Path(save_model_path).write_text(json.dumps(model.to_json_dict(), indent=2), encoding="utf-8")

    return model


# Alias because the design discussion used both words.
setup = survey

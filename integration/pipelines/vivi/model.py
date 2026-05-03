"""Building, wall, and door data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .constants import EPS
from .geometry import round_dm
from .vector import UP, Vec3


@dataclass
class DoorReference:
    """Door reference derived from any 3 or 4 captured door-frame corners.

    u values are in the wall-local coordinate where +u means right when facing
    the wall from outside. z values are heights above the local ground plane.
    """

    face_name: str
    center_u: float
    left_u: float
    right_u: float
    bottom_z: float
    top_z: float

    @property
    def center_z(self) -> float:
        return 0.5 * (self.bottom_z + self.top_z)


@dataclass
class WallPlane:
    """A vertical wall plane with wall-local coordinates.

    p0 and p1 are the bottom edge endpoints. normal points outward from the
    building. u_axis points to the operator's right when facing the wall from
    outside. This makes wording like '0.7 m right of the door' unambiguous.
    """

    name: str
    p0: Vec3
    p1: Vec3
    normal: Vec3
    height_m: float
    heading_deg: float
    door: Optional[DoorReference] = None

    def __post_init__(self) -> None:
        self.normal = self.normal.horizontal().normalized()
        view_dir = self.normal * -1.0  # looking from outside toward the wall
        self.u_axis = view_dir.cross(UP).horizontal().normalized()
        self.length_m = (self.p1 - self.p0).horizontal().norm()

        # Instead of assuming p0 is left and p1 is right, define explicit u bounds.
        self.u0 = self.u_of(self.p0)
        self.u1 = self.u_of(self.p1)
        self.u_min = min(self.u0, self.u1)
        self.u_max = max(self.u0, self.u1)

    def signed_distance(self, p: Vec3) -> float:
        """Signed perpendicular distance from p to this wall plane."""
        return (p - self.p0).dot(self.normal)

    def project_point_to_plane(self, p: Vec3) -> Vec3:
        """Perpendicular projection of p onto the infinite wall plane."""
        return p - self.normal * self.signed_distance(p)

    def intersect_ray(self, origin: Vec3, direction: Vec3) -> Optional[Tuple[float, Vec3]]:
        """Intersect a ray with the infinite wall plane.

        Returns (t, point) where point = origin + t * direction. t must be
        positive, otherwise the wall is behind the camera.
        """
        denom = direction.dot(self.normal)
        if abs(denom) < EPS:
            return None
        t = (self.p0 - origin).dot(self.normal) / denom
        if t < 0.0:
            return None
        return t, origin + direction * t

    def u_of(self, p: Vec3) -> float:
        """Horizontal wall coordinate. +u means right when facing from outside."""
        return (p - self.p0).dot(self.u_axis)

    def contains_wall_point(self, p: Vec3, margin_m: float = 0.75) -> bool:
        """Check whether a projected point is plausibly on the finite wall.

        A small margin is allowed because GPS, operator centring, and attitude
        estimates will not be perfect during manual flight.
        """
        u = self.u_of(p)
        z_ok = -margin_m <= p.z <= self.height_m + margin_m
        u_ok = self.u_min - margin_m <= u <= self.u_max + margin_m
        return z_ok and u_ok

    def endpoint_label(self, endpoint: Vec3) -> str:
        """Human-friendly label for a wall endpoint.

        For north/south faces, western/eastern corners are intuitive. For east/west
        faces, southern/northern corners are intuitive.
        """
        if self.name in ("north", "south"):
            other = self.p1 if endpoint == self.p0 else self.p0
            return "western corner" if endpoint.x <= other.x else "eastern corner"
        if self.name in ("east", "west"):
            other = self.p1 if endpoint == self.p0 else self.p0
            return "southern corner" if endpoint.y <= other.y else "northern corner"
        return "nearest corner"

    def nearest_corner_reference(self, u: float) -> Tuple[float, str]:
        """Return distance to nearest endpoint and that endpoint's label."""
        d0 = abs(u - self.u0)
        d1 = abs(u - self.u1)
        if d0 <= d1:
            return d0, self.endpoint_label(self.p0)
        return d1, self.endpoint_label(self.p1)

    def best_horizontal_reference(self, u: float) -> Tuple[str, float, str]:
        """Choose nearest useful horizontal reference: door centre or corner.

        For a wall target, the relevant horizontal references are the door centre
        on that face and the nearest face corner.
        """
        corner_dist, corner_label = self.nearest_corner_reference(u)
        best_kind = "corner"
        best_dist = corner_dist
        best_phrase = f"{round_dm(corner_dist):.1f} m from the {corner_label}"

        if self.door is not None:
            door_dist = abs(u - self.door.center_u)
            if door_dist < best_dist:
                side = "right" if u > self.door.center_u else "left"
                best_kind = "door"
                best_dist = door_dist
                best_phrase = (
                    f"{round_dm(door_dist):.1f} m {side} of the door centre "
                    f"when facing the wall from outside"
                )

        return best_kind, best_dist, best_phrase


@dataclass
class BuildingModel:
    """Local 3D building model created during setup()/survey()."""

    corners: List[Vec3]
    height_m: float
    ground_z: float
    walls: List[WallPlane]

    def wall_by_name(self, name: str) -> WallPlane:
        for wall in self.walls:
            if wall.name == name:
                return wall
        raise KeyError(f"No wall named {name!r}. Available: {[w.name for w in self.walls]}")

    def nearest_wall_to_ground_point(self, p: Vec3) -> WallPlane:
        """Return the face with the smallest horizontal perpendicular distance."""
        return min(self.walls, key=lambda wall: abs(wall.signed_distance(Vec3(p.x, p.y, wall.p0.z))))

    def front_facing_wall(self, ray_dir: Vec3, origin: Optional[Vec3] = None) -> Optional[WallPlane]:
        """Choose the wall that the front camera is most likely viewing.

        Automatic wall selection should not require the operator to press N/E/S/W.
        The most reliable choice is the wall that the front-camera centre ray
        actually hits first. This uses both:

        1. the camera direction, from yaw/pitch/roll; and
        2. the camera origin, from the MAVLink position plus the camera offset.

        If ``origin`` is provided, each wall plane is intersected with the camera
        ray. The nearest valid forward intersection is selected. If no useful
        intersection exists, the method falls back to orientation only: the wall
        whose outward normal most strongly opposes the camera direction.
        """
        if not self.walls:
            return None

        ray_h = ray_dir.horizontal()
        try:
            ray_h = ray_h.normalized()
        except ValueError:
            ray_h = ray_dir

        if origin is not None:
            scored_hits: list[tuple[int, float, float, WallPlane]] = []

            for wall in self.walls:
                hit = wall.intersect_ray(origin, ray_dir)
                if hit is None:
                    continue

                t, point = hit
                if t < 0.0:
                    continue

                # Negative alignment means the camera ray points into the face
                # from outside, opposite the wall's outward normal. Values close
                # to zero mean the ray is almost parallel to the wall.
                alignment = ray_h.dot(wall.normal)
                if alignment > -0.05:
                    continue

                # Prefer hits that land on the finite wall rectangle. A margin is
                # allowed because survey/telemetry will be imperfect during field
                # use. If no finite hit exists, the fallback below still works.
                finite_score = 0 if wall.contains_wall_point(point, margin_m=2.0) else 1
                scored_hits.append((finite_score, t, alignment, wall))

            if scored_hits:
                # Sort by: finite wall hit first, nearest intersection second,
                # strongest opposing normal third.
                scored_hits.sort(key=lambda item: (item[0], item[1], item[2]))
                return scored_hits[0][3]

        # Fallback for older calls or bad geometry: choose by heading/alignment
        # only. This is less robust near corners but better than requiring manual
        # face selection.
        candidates = sorted(self.walls, key=lambda w: ray_h.dot(w.normal))
        return candidates[0] if candidates else None

    def attach_door_from_points(self, door_points: Sequence[Vec3]) -> None:
        """Attach a door reference to the nearest wall using any 3 or 4 frame points.

        We only need the door's wall-local u-range and z-range. With any three
        frame corners, min/max in u and z can estimate centre, left/right,
        bottom/top well enough for reporting.
        """
        if len(door_points) < 3:
            raise ValueError("At least three door-frame points are required.")

        avg = Vec3(
            sum(p.x for p in door_points) / len(door_points),
            sum(p.y for p in door_points) / len(door_points),
            sum(p.z for p in door_points) / len(door_points),
        )
        wall = min(self.walls, key=lambda w: abs(w.signed_distance(avg)))
        u_values = [wall.u_of(wall.project_point_to_plane(p)) for p in door_points]
        z_values = [p.z - self.ground_z for p in door_points]

        left_u = min(u_values)
        right_u = max(u_values)
        bottom_z = min(z_values)
        top_z = max(z_values)
        wall.door = DoorReference(
            face_name=wall.name,
            center_u=0.5 * (left_u + right_u),
            left_u=left_u,
            right_u=right_u,
            bottom_z=bottom_z,
            top_z=top_z,
        )

    def to_json_dict(self) -> dict:
        """Serializable model snapshot for field debugging."""
        return {
            "height_m": self.height_m,
            "ground_z": self.ground_z,
            "corners": [c.as_tuple() for c in self.corners],
            "walls": [
                {
                    "name": w.name,
                    "p0": w.p0.as_tuple(),
                    "p1": w.p1.as_tuple(),
                    "normal": w.normal.as_tuple(),
                    "heading_deg": w.heading_deg,
                    "height_m": w.height_m,
                    "door": None if w.door is None else {
                        "center_u": w.door.center_u,
                        "left_u": w.door.left_u,
                        "right_u": w.door.right_u,
                        "bottom_z": w.door.bottom_z,
                        "top_z": w.door.top_z,
                    },
                }
                for w in self.walls
            ],
        }

"""Target localization from marked events to wall/ground-relative positions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .constants import EPS
from .detection import TargetEvent
from .geometry import camera_centre_ray_world, camera_position_world, round_dm
from .modes import CameraMode
from .model import BuildingModel
from .pose import CameraConfig
from .vector import Vec3


@dataclass
class LocalizedTarget:
    """Result after geometry projection but before final text writing."""

    target_id: int
    colour: str
    camera_mode: CameraMode
    surface: str  # wall face name or "ground"
    location_text: str
    point_local: Vec3
    warnings: List[str] = field(default_factory=list)


class TargetLocalizer:
    """Project marked target events onto wall/ground geometry."""

    def __init__(self, model: BuildingModel, camera: Optional[CameraConfig] = None):
        self.model = model
        self.camera = camera if camera is not None else CameraConfig()

    def localize_event(self, event: TargetEvent, target_id: int) -> LocalizedTarget:
        if event.camera_mode == CameraMode.FRONT:
            return self._localize_front(event, target_id)
        if event.camera_mode == CameraMode.DOWN:
            return self._localize_down(event, target_id)
        raise ValueError(f"Unsupported camera mode: {event.camera_mode}")

    def _front_height_override_m(self, event: TargetEvent) -> Optional[float]:
        """Read an optional manual wall-target height from event.notes.

        main.py stores this as ``target_height_m=<value>`` when the operator
        enters a target height. Keeping it in notes avoids changing the
        TargetEvent dataclass and keeps old saved events compatible.
        """
        prefix = "target_height_m="
        for token in event.notes.replace(";", " ").split():
            if token.startswith(prefix):
                try:
                    return float(token[len(prefix):])
                except ValueError:
                    return None
        return None

    def _localize_front(self, event: TargetEvent, target_id: int) -> LocalizedTarget:
        """Project the current Vivi position onto a wall plane.

        FRONT mode no longer uses yaw, pitch, roll, or a front-camera ray to
        choose the wall. This matches the waypoint-test workflow: fly Vivi to a
        position horizontally aligned with the target, then mark the target. The
        current position is projected perpendicularly onto the selected wall, or
        onto the closest wall when no face was selected.
        """
        warnings: List[str] = []
        pose = event.pose

        # Use the camera centre for height/position, but do not use the camera
        # direction. For the normal 10 cm vertical offset this gives the same
        # horizontal position as the GPS/autopilot origin and a slightly better z.
        cam_pos = camera_position_world(pose, self.camera)

        if event.selected_face:
            try:
                wall = self.model.wall_by_name(event.selected_face)
            except Exception:
                warnings.append(
                    f"Selected face {event.selected_face!r} was not found; used closest wall instead."
                )
                wall = self.model.nearest_wall_to_ground_point(cam_pos)
        else:
            wall = self.model.nearest_wall_to_ground_point(cam_pos)

        # Perpendicular projection from current position onto the wall plane.
        # This is the core change: no yaw-based front ray is used here.
        point = wall.project_point_to_plane(cam_pos)

        height_override_m = self._front_height_override_m(event)
        if height_override_m is not None:
            height_m = height_override_m
            point = Vec3(point.x, point.y, self.model.ground_z + height_m)
        else:
            height_m = point.z - self.model.ground_z

        if height_m < -0.2:
            warnings.append("Projected wall target is below ground; clamped to ground height.")
            height_m = 0.0
            point = Vec3(point.x, point.y, self.model.ground_z)
        elif height_m > self.model.height_m + 0.5:
            warnings.append(
                "Projected wall target is above building height; clamped to building height. "
                "For better accuracy, enter the target height when marking."
            )
            height_m = self.model.height_m
            point = Vec3(point.x, point.y, self.model.ground_z + self.model.height_m)

        if not wall.contains_wall_point(point):
            warnings.append(
                "Projected target point is outside or near the edge of the finite wall model; review manually."
            )

        u = wall.u_of(point)
        ref_kind, _, ref_phrase = wall.best_horizontal_reference(u)

        door_height_phrase = ""
        if ref_kind == "door" and wall.door is not None and height_m > wall.door.top_z:
            door_height_phrase = f", about {round_dm(height_m - wall.door.top_z):.1f} m above the top of the door"

        location = (
            f"On the {wall.name} face of the building, approximately "
            f"{round_dm(height_m):.1f} m above ground and {ref_phrase}"
            f"{door_height_phrase}."
        )

        return LocalizedTarget(
            target_id=target_id,
            colour=event.colour.capitalize(),
            camera_mode=event.camera_mode,
            surface=wall.name,
            location_text=location,
            point_local=point,
            warnings=warnings,
        )

    def _localize_down(self, event: TargetEvent, target_id: int) -> LocalizedTarget:
        """Project a centred down-camera target onto the ground plane."""
        warnings: List[str] = []
        pose = event.pose
        cam_pos = camera_position_world(pose, self.camera)
        ray = camera_centre_ray_world(pose, self.camera, CameraMode.DOWN)

        # Intersect down-camera ray with z = ground_z.
        if abs(ray.z) < EPS:
            warnings.append("Down camera ray is nearly parallel to ground; used vertical fallback.")
            point = Vec3(cam_pos.x, cam_pos.y, self.model.ground_z)
        else:
            t = (self.model.ground_z - cam_pos.z) / ray.z
            if t < 0.0:
                warnings.append("Ground plane is behind down camera ray; used vertical fallback.")
                point = Vec3(cam_pos.x, cam_pos.y, self.model.ground_z)
            else:
                point = cam_pos + ray * t

        wall = self.model.nearest_wall_to_ground_point(point)
        distance_from_face = abs(wall.signed_distance(Vec3(point.x, point.y, wall.p0.z)))

        # Project the ground point onto the nearest wall line so the along-wall
        # reference can be compared to corners/door on the same face.
        projected_to_wall = wall.project_point_to_plane(Vec3(point.x, point.y, wall.p0.z))
        u = wall.u_of(projected_to_wall)
        _, _, ref_phrase = wall.best_horizontal_reference(u)

        location = (
            f"On the ground, approximately {round_dm(distance_from_face):.1f} m away "
            f"from the {wall.name} face of the building and {ref_phrase}."
        )

        return LocalizedTarget(
            target_id=target_id,
            colour=event.colour.capitalize(),
            camera_mode=event.camera_mode,
            surface="ground",
            location_text=location,
            point_local=point,
            warnings=warnings,
        )

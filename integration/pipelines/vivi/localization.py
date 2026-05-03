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

    def _localize_front(self, event: TargetEvent, target_id: int) -> LocalizedTarget:
        """Project a centred front-camera target onto a wall plane."""
        warnings: List[str] = []
        pose = event.pose
        cam_pos = camera_position_world(pose, self.camera)
        ray = camera_centre_ray_world(pose, self.camera, CameraMode.FRONT)

        # If the operator selects a face, trust it. This reduces wrong wall
        # selection when the drone is near a corner or looking diagonally.
        if event.selected_face:
            wall = self.model.wall_by_name(event.selected_face)
        else:
            wall = self.model.front_facing_wall(ray, origin=cam_pos)
            if wall is None:
                raise RuntimeError("No wall model available for front-camera localization.")

        hit = wall.intersect_ray(cam_pos, ray)
        if hit is None:
            # Fallback: perpendicular projection of camera position. This is less
            # accurate but matches the simplified fallback idea and is useful if
            # attitude data is missing or the ray is nearly parallel to the wall.
            warnings.append(
                "Front camera ray did not intersect selected wall; used perpendicular projection fallback."
            )
            point = wall.project_point_to_plane(cam_pos)
        else:
            _, point = hit

        if not wall.contains_wall_point(point):
            warnings.append(
                "Projected target point is outside or near the edge of the finite wall model; review manually."
            )

        height_m = point.z - self.model.ground_z
        if height_m < -0.2:
            warnings.append("Projected wall target is below ground; review pitch/altitude/camera offset.")
        if height_m > self.model.height_m + 0.5:
            warnings.append("Projected wall target is above building height; review pitch/altitude/camera offset.")

        u = wall.u_of(point)
        _, _, ref_phrase = wall.best_horizontal_reference(u)

        # Height is always included for wall targets because a wall location with
        # no height is ambiguous in 3D.
        location = (
            f"On the {wall.name} face of the building, approximately "
            f"{round_dm(max(0.0, height_m)):.1f} m above ground and {ref_phrase}."
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

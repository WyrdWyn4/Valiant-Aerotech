"""Serializable data models for the Task One desktop localizer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from .geometry import ConfidenceLabel, Point


class CalibrationMode(StrEnum):
    FULL_CORNERS = "Full wall corners"
    BOUNDARY_LINES = "Partial wall boundary lines"
    APPROXIMATE_EDGE = "Approximate single-edge partial wall"


class SurfaceType(StrEnum):
    WALL = "wall"
    GROUND = "ground"
    OTHER = "other"


TARGET_COLOURS = ["Black", "White", "Red", "Yellow", "Blue", "Green"]
FACE_DIRECTIONS = ["North", "South", "East", "West"]


@dataclass(slots=True)
class CircleAnnotation:
    center: Point
    radius_px: float


@dataclass(slots=True)
class LineAnnotation:
    start: Point
    end: Point


@dataclass(slots=True)
class DoorAnnotation:
    corners_tl_tr_br_bl: list[Point] = field(default_factory=list)
    left_edge: LineAnnotation | None = None
    right_edge: LineAnnotation | None = None

    def has_any_reference(self) -> bool:
        return bool(self.corners_tl_tr_br_bl or self.left_edge or self.right_edge)


@dataclass(slots=True)
class CalibrationAnnotations:
    corners_tl_tr_br_bl: list[Point] = field(default_factory=list)
    top_boundary: LineAnnotation | None = None
    right_boundary: LineAnnotation | None = None
    bottom_boundary: LineAnnotation | None = None
    left_boundary: LineAnnotation | None = None
    approximate_reference_edge: LineAnnotation | None = None
    approximate_reference_edge_side: str = "left"  # "left" or "right"


@dataclass(slots=True)
class ScreenshotSession:
    id: str
    image_path: str
    created_at_utc: str
    face_direction: str = "North"
    wall_width_m: float = 0.0
    wall_height_m: float = 0.0
    calibration_mode: str = CalibrationMode.FULL_CORNERS.value
    calibration: CalibrationAnnotations = field(default_factory=CalibrationAnnotations)
    door: DoorAnnotation = field(default_factory=DoorAnnotation)
    draft_circle: CircleAnnotation | None = None

    @classmethod
    def create(cls, image_path: str) -> "ScreenshotSession":
        return cls(
            id=str(uuid4()),
            image_path=image_path,
            created_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )


@dataclass(slots=True)
class ComputedWallLocation:
    x_from_left_m: float
    height_above_ground_m: float
    confidence: str
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TargetRecord:
    number: int
    surface_type: str
    colour: str
    description_text: str
    generated_text: str
    confidence: str
    warnings: list[str] = field(default_factory=list)
    screenshot_id: str | None = None
    circle: CircleAnnotation | None = None
    computed_wall_location: ComputedWallLocation | None = None
    manual_fields: dict[str, Any] = field(default_factory=dict)
    created_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


@dataclass(slots=True)
class ProjectSession:
    team_name: str = "Valiant_Aerotech"
    building_length_m: float = 0.0
    building_width_m: float = 0.0
    building_height_m: float = 0.0
    north_south_face_span_source: str = "length"  # "length" or "width"
    screenshots: list[ScreenshotSession] = field(default_factory=list)
    targets: list[TargetRecord] = field(default_factory=list)
    workspace_dir: str = "workspace"
    output_txt_path: str = "Task_1_Valiant_Aerotech_targets.txt"
    session_json_path: str = "task_one_target_localizer_session.json"

    def next_target_number(self) -> int:
        if not self.targets:
            return 1
        return max(target.number for target in self.targets) + 1

    def screenshot_by_id(self, screenshot_id: str) -> ScreenshotSession | None:
        for screenshot in self.screenshots:
            if screenshot.id == screenshot_id:
                return screenshot
        return None

    def target_by_number(self, target_number: int) -> TargetRecord | None:
        for target in self.targets:
            if target.number == target_number:
                return target
        return None

    def remove_target(self, target_number: int) -> None:
        self.targets = [target for target in self.targets if target.number != target_number]
        for new_number, target in enumerate(sorted(self.targets, key=lambda item: item.number), start=1):
            target.number = new_number

    def normalize_output_paths(self) -> None:
        expected = f"Task_1_{self.team_name}_targets.txt"
        existing = Path(self.output_txt_path)
        if not existing.name.startswith("Task_1_") or existing.name != expected:
            self.output_txt_path = str(existing.with_name(expected)) if existing.parent != Path('.') else expected


def dataclass_to_dict(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        raw = asdict(obj)
        return _convert_enums(raw)
    return obj


def _convert_enums(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _convert_enums(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_convert_enums(item) for item in value]
    return value


def point_from_json(raw: list[float] | tuple[float, float]) -> Point:
    return float(raw[0]), float(raw[1])


def line_from_json(raw: dict[str, Any] | None) -> LineAnnotation | None:
    if raw is None:
        return None
    return LineAnnotation(start=point_from_json(raw["start"]), end=point_from_json(raw["end"]))


def circle_from_json(raw: dict[str, Any] | None) -> CircleAnnotation | None:
    if raw is None:
        return None
    return CircleAnnotation(center=point_from_json(raw["center"]), radius_px=float(raw["radius_px"]))


def calibration_from_json(raw: dict[str, Any] | None) -> CalibrationAnnotations:
    raw = raw or {}
    return CalibrationAnnotations(
        corners_tl_tr_br_bl=[point_from_json(point) for point in raw.get("corners_tl_tr_br_bl", [])],
        top_boundary=line_from_json(raw.get("top_boundary")),
        right_boundary=line_from_json(raw.get("right_boundary")),
        bottom_boundary=line_from_json(raw.get("bottom_boundary")),
        left_boundary=line_from_json(raw.get("left_boundary")),
        approximate_reference_edge=line_from_json(raw.get("approximate_reference_edge")),
        approximate_reference_edge_side=str(raw.get("approximate_reference_edge_side", "left")),
    )


def door_from_json(raw: dict[str, Any] | None) -> DoorAnnotation:
    raw = raw or {}
    return DoorAnnotation(
        corners_tl_tr_br_bl=[point_from_json(point) for point in raw.get("corners_tl_tr_br_bl", [])],
        left_edge=line_from_json(raw.get("left_edge")),
        right_edge=line_from_json(raw.get("right_edge")),
    )


def computed_location_from_json(raw: dict[str, Any] | None) -> ComputedWallLocation | None:
    if raw is None:
        return None
    return ComputedWallLocation(
        x_from_left_m=float(raw["x_from_left_m"]),
        height_above_ground_m=float(raw["height_above_ground_m"]),
        confidence=str(raw["confidence"]),
        warnings=[str(item) for item in raw.get("warnings", [])],
    )


def screenshot_from_json(raw: dict[str, Any]) -> ScreenshotSession:
    return ScreenshotSession(
        id=str(raw["id"]),
        image_path=str(raw["image_path"]),
        created_at_utc=str(raw.get("created_at_utc", "")),
        face_direction=str(raw.get("face_direction", "North")),
        wall_width_m=float(raw.get("wall_width_m", 0.0)),
        wall_height_m=float(raw.get("wall_height_m", 0.0)),
        calibration_mode=str(raw.get("calibration_mode", CalibrationMode.FULL_CORNERS.value)),
        calibration=calibration_from_json(raw.get("calibration")),
        door=door_from_json(raw.get("door")),
        draft_circle=circle_from_json(raw.get("draft_circle")),
    )


def target_from_json(raw: dict[str, Any]) -> TargetRecord:
    return TargetRecord(
        number=int(raw["number"]),
        surface_type=str(raw["surface_type"]),
        colour=str(raw["colour"]),
        description_text=str(raw["description_text"]),
        generated_text=str(raw.get("generated_text", raw["description_text"])),
        confidence=str(raw.get("confidence", ConfidenceLabel.MANUAL.value)),
        warnings=[str(item) for item in raw.get("warnings", [])],
        screenshot_id=str(raw["screenshot_id"]) if raw.get("screenshot_id") else None,
        circle=circle_from_json(raw.get("circle")),
        computed_wall_location=computed_location_from_json(raw.get("computed_wall_location")),
        manual_fields=dict(raw.get("manual_fields", {})),
        created_at_utc=str(raw.get("created_at_utc", "")),
    )


def project_from_json(raw: dict[str, Any]) -> ProjectSession:
    session = ProjectSession(
        team_name=str(raw.get("team_name", "Valiant_Aerotech")),
        building_length_m=float(raw.get("building_length_m", 0.0)),
        building_width_m=float(raw.get("building_width_m", 0.0)),
        building_height_m=float(raw.get("building_height_m", 0.0)),
        north_south_face_span_source=str(raw.get("north_south_face_span_source", "length")),
        screenshots=[screenshot_from_json(item) for item in raw.get("screenshots", [])],
        targets=[target_from_json(item) for item in raw.get("targets", [])],
        workspace_dir=str(raw.get("workspace_dir", "workspace")),
        output_txt_path=str(raw.get("output_txt_path", "Task_1_Valiant_Aerotech_targets.txt")),
        session_json_path=str(raw.get("session_json_path", "task_one_target_localizer_session.json")),
    )
    session.normalize_output_paths()
    return session

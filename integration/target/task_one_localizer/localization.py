"""High-level wall-target localization services for the desktop UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PySide6.QtGui import QImage

from .geometry import (
    ApproximateEdgeMapping,
    ConfidenceLabel,
    MappedPoint,
    Point,
    WallMapping,
    average_points,
    build_wall_mapping_from_boundary_lines,
    build_wall_mapping_from_corners,
    point_in_convex_quad,
    round_decimetre,
)
from .models import (
    CalibrationMode,
    CircleAnnotation,
    ComputedWallLocation,
    DoorAnnotation,
    ScreenshotSession,
)
from .reporting import DoorHorizontalReference, generate_wall_location_sentence


@dataclass(slots=True)
class WallTargetDraft:
    generated_sentence: str
    location: ComputedWallLocation
    confidence: str
    warnings: list[str]
    door_reference: DoorHorizontalReference | None


def image_size_from_path(image_path: str) -> tuple[int, int] | None:
    image = QImage(str(Path(image_path)))
    if image.isNull():
        return None
    return image.width(), image.height()


def _line_tuple(line) -> tuple[Point, Point]:
    return line.start, line.end


def build_mapping_for_screenshot(screenshot: ScreenshotSession) -> WallMapping | ApproximateEdgeMapping:
    mode = screenshot.calibration_mode
    width_m = screenshot.wall_width_m
    height_m = screenshot.wall_height_m
    if width_m <= 0 or height_m <= 0:
        raise ValueError("Wall width and height must be entered before calculating targets.")

    image_size = image_size_from_path(screenshot.image_path)
    annotations = screenshot.calibration

    if mode == CalibrationMode.FULL_CORNERS.value:
        if len(annotations.corners_tl_tr_br_bl) != 4:
            raise ValueError("Full-wall mode requires four wall corners: TL, TR, BR, BL.")
        return build_wall_mapping_from_corners(
            annotations.corners_tl_tr_br_bl,
            width_m,
            height_m,
            image_size=image_size,
        )

    if mode == CalibrationMode.BOUNDARY_LINES.value:
        needed = {
            "top": annotations.top_boundary,
            "right": annotations.right_boundary,
            "bottom": annotations.bottom_boundary,
            "left": annotations.left_boundary,
        }
        missing = [name for name, value in needed.items() if value is None]
        if missing:
            raise ValueError(f"Boundary-line mode is missing: {', '.join(missing)}.")
        return build_wall_mapping_from_boundary_lines(
            top=_line_tuple(annotations.top_boundary),  # type: ignore[arg-type]
            right=_line_tuple(annotations.right_boundary),  # type: ignore[arg-type]
            bottom=_line_tuple(annotations.bottom_boundary),  # type: ignore[arg-type]
            left=_line_tuple(annotations.left_boundary),  # type: ignore[arg-type]
            wall_width_m=width_m,
            wall_height_m=height_m,
            image_size=image_size,
        )

    if mode == CalibrationMode.APPROXIMATE_EDGE.value:
        edge = annotations.approximate_reference_edge
        if edge is None:
            raise ValueError("Approximate mode requires one marked full-height reference wall edge.")
        # The UI asks the operator to draw from bottom to top, but normalize anyway by assuming
        # the lower image point is the ground-side endpoint in common upright captures.
        start, end = edge.start, edge.end
        edge_bottom, edge_top = (start, end) if start[1] >= end[1] else (end, start)
        return ApproximateEdgeMapping(
            edge_bottom=edge_bottom,
            edge_top=edge_top,
            reference_edge=annotations.approximate_reference_edge_side,
            wall_width_m=width_m,
            wall_height_m=height_m,
        )

    raise ValueError(f"Unknown calibration mode: {mode}")


def _map_points(
    mapping: WallMapping | ApproximateEdgeMapping, points: Sequence[Point]
) -> list[MappedPoint]:
    return [mapping.map_point(point) for point in points]


def _combine_warnings(*groups: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for warning in group:
            if warning not in seen:
                output.append(warning)
                seen.add(warning)
    return output


def _door_x_bounds_from_corners(
    mapping: WallMapping | ApproximateEdgeMapping, door: DoorAnnotation
) -> tuple[float, float, list[str]] | None:
    if len(door.corners_tl_tr_br_bl) != 4:
        return None
    mapped = _map_points(mapping, door.corners_tl_tr_br_bl)
    left_x = min(point.x_m for point in mapped)
    right_x = max(point.x_m for point in mapped)
    warnings = _combine_warnings(*(point.warnings for point in mapped))
    return left_x, right_x, warnings


def _door_edge_x(
    mapping: WallMapping | ApproximateEdgeMapping,
    edge,
) -> tuple[float, list[str]]:
    mapped = _map_points(mapping, [edge.start, edge.end])
    x_value = sum(point.x_m for point in mapped) / len(mapped)
    warnings = _combine_warnings(*(point.warnings for point in mapped))
    return x_value, warnings


def resolve_door_horizontal_reference(
    *,
    mapping: WallMapping | ApproximateEdgeMapping,
    door: DoorAnnotation,
    target_x_m: float,
    target_height_m: float,
    directly_above_tolerance_m: float = 0.05,
) -> DoorHorizontalReference | None:
    if not door.has_any_reference():
        return None

    corner_bounds = _door_x_bounds_from_corners(mapping, door)
    if corner_bounds is not None:
        left_x, right_x, warnings = corner_bounds
        warning = warnings[0] if warnings else None
        if left_x - directly_above_tolerance_m <= target_x_m <= right_x + directly_above_tolerance_m:
            extra = "Target is classified as directly above the door; confirm this wording before submission."
            if warning:
                extra = f"{warning} {extra}"
            return DoorHorizontalReference(relation="above", warning=extra)
        if target_x_m < left_x:
            return DoorHorizontalReference(
                relation="left",
                distance_m=max(0.0, left_x - target_x_m),
                warning=warning,
            )
        return DoorHorizontalReference(
            relation="right",
            distance_m=max(0.0, target_x_m - right_x),
            warning=warning,
        )

    left_x: float | None = None
    right_x: float | None = None
    warnings: list[str] = []
    if door.left_edge is not None:
        left_x, edge_warnings = _door_edge_x(mapping, door.left_edge)
        warnings.extend(edge_warnings)
    if door.right_edge is not None:
        right_x, edge_warnings = _door_edge_x(mapping, door.right_edge)
        warnings.extend(edge_warnings)

    warning = warnings[0] if warnings else None
    if left_x is not None and right_x is not None:
        low, high = sorted((left_x, right_x))
        if low - directly_above_tolerance_m <= target_x_m <= high + directly_above_tolerance_m:
            extra = "Target is classified as directly above the door; confirm this wording before submission."
            if warning:
                extra = f"{warning} {extra}"
            return DoorHorizontalReference(relation="above", warning=extra)
        if target_x_m < low:
            return DoorHorizontalReference(
                relation="left",
                distance_m=max(0.0, low - target_x_m),
                warning=warning,
            )
        return DoorHorizontalReference(
            relation="right",
            distance_m=max(0.0, target_x_m - high),
            warning=warning,
        )

    if left_x is not None:
        if target_x_m < left_x:
            return DoorHorizontalReference(
                relation="left",
                distance_m=max(0.0, left_x - target_x_m),
                warning=warning,
            )
        return DoorHorizontalReference(
            relation="ambiguous",
            warning=(
                "Only the left door edge is marked, and the target is not clearly left of it. "
                "Edit the door-relative wording manually before confirming."
            ),
        )

    if right_x is not None:
        if target_x_m > right_x:
            return DoorHorizontalReference(
                relation="right",
                distance_m=max(0.0, target_x_m - right_x),
                warning=warning,
            )
        return DoorHorizontalReference(
            relation="ambiguous",
            warning=(
                "Only the right door edge is marked, and the target is not clearly right of it. "
                "Edit the door-relative wording manually before confirming."
            ),
        )

    return DoorHorizontalReference(
        relation="ambiguous",
        warning="Door annotation exists but usable horizontal door bounds were not found.",
    )


def calculate_wall_target_draft(
    *, screenshot: ScreenshotSession, circle: CircleAnnotation, colour: str
) -> WallTargetDraft:
    mapping = build_mapping_for_screenshot(screenshot)
    mapped_center = mapping.map_point(circle.center)
    warnings = list(mapped_center.warnings)

    if isinstance(mapping, WallMapping) and not point_in_convex_quad(circle.center, mapping.source_quad):
        warnings.append(
            "Target circle centre lies outside the calibrated wall quadrilateral; confirm the screenshot geometry."
        )

    door_reference = resolve_door_horizontal_reference(
        mapping=mapping,
        door=screenshot.door,
        target_x_m=mapped_center.x_m,
        target_height_m=mapped_center.y_m,
    )
    generated, wording_warnings = generate_wall_location_sentence(
        face_direction=screenshot.face_direction,
        height_above_ground_m=mapped_center.y_m,
        x_from_left_m=mapped_center.x_m,
        wall_width_m=screenshot.wall_width_m,
        colour=colour,
        door_reference=door_reference,
    )
    warnings.extend(wording_warnings)
    confidence = mapped_center.confidence
    if warnings and confidence == ConfidenceLabel.HIGH:
        confidence = ConfidenceLabel.MEDIUM
    location = ComputedWallLocation(
        x_from_left_m=round_decimetre(mapped_center.x_m),
        height_above_ground_m=round_decimetre(mapped_center.y_m),
        confidence=confidence.value,
        warnings=warnings,
    )
    return WallTargetDraft(
        generated_sentence=generated,
        location=location,
        confidence=confidence.value,
        warnings=warnings,
        door_reference=door_reference,
    )


def target_circle_center(circle: CircleAnnotation) -> Point:
    return circle.center


def midpoint_for_line(start: Point, end: Point) -> Point:
    return average_points((start, end))

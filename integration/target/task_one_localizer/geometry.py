"""Geometry helpers for Task One image-based target localization.

The module intentionally separates high-confidence projective mappings from
lower-confidence partial-wall approximations.  The desktop UI can therefore stay
permissive while the report pipeline retains explicit quality labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import hypot
from typing import Iterable, Sequence

import numpy as np

Point = tuple[float, float]
Line = tuple[Point, Point]


class ConfidenceLabel(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    MANUAL = "Manual"


@dataclass(slots=True)
class MappedPoint:
    """A point mapped into wall-space metres."""

    x_m: float
    y_m: float
    confidence: ConfidenceLabel
    warnings: list[str]


@dataclass(slots=True)
class WallMapping:
    """A reusable image->wall mapping."""

    matrix: np.ndarray
    wall_width_m: float
    wall_height_m: float
    confidence: ConfidenceLabel
    warnings: list[str]
    source_quad: tuple[Point, Point, Point, Point]

    def map_point(self, point: Point) -> MappedPoint:
        mapped = apply_homography(self.matrix, point)
        warnings = list(self.warnings)
        x_m, y_m = mapped
        if x_m < -0.05 or x_m > self.wall_width_m + 0.05:
            warnings.append(
                "Mapped target is outside the horizontal wall span; review the annotation."
            )
        if y_m < -0.05 or y_m > self.wall_height_m + 0.05:
            warnings.append(
                "Mapped target is below ground or above the wall height; review the annotation."
            )
        confidence = self.confidence
        if warnings and confidence == ConfidenceLabel.HIGH:
            confidence = ConfidenceLabel.MEDIUM
        return MappedPoint(x_m=x_m, y_m=y_m, confidence=confidence, warnings=warnings)


@dataclass(slots=True)
class ApproximateEdgeMapping:
    """Low-confidence single-edge scale approximation.

    This mode intentionally reflects the user's request to support partial screenshots
    even when only one complete vertical wall edge is clearly available.  It assumes a
    local image scale derived from the wall's apparent pixel height and applies that
    same local scale to horizontal displacement from the marked edge.  This is *not* a
    projective correction and should remain visibly flagged in the UI.
    """

    edge_bottom: Point
    edge_top: Point
    reference_edge: str  # "left" or "right" as seen from outside the wall
    wall_width_m: float
    wall_height_m: float

    def __post_init__(self) -> None:
        if self.reference_edge not in {"left", "right"}:
            raise ValueError("reference_edge must be 'left' or 'right'.")
        length_px = distance(self.edge_bottom, self.edge_top)
        if length_px <= 1e-6:
            raise ValueError("Approximate reference edge is too short.")

    @property
    def metres_per_pixel(self) -> float:
        return self.wall_height_m / distance(self.edge_bottom, self.edge_top)

    @property
    def edge_unit(self) -> np.ndarray:
        vec = np.array(
            [self.edge_top[0] - self.edge_bottom[0], self.edge_top[1] - self.edge_bottom[1]],
            dtype=float,
        )
        return vec / np.linalg.norm(vec)

    @property
    def interior_unit(self) -> np.ndarray:
        vertical = self.edge_unit
        # For a bottom->top edge, rotate counter-clockwise to get image-right for a
        # conventional upright edge.  That corresponds to inward distance from a left
        # edge.  The opposite sign corresponds to inward distance from a right edge.
        left_edge_interior = np.array([-vertical[1], vertical[0]], dtype=float)
        return left_edge_interior if self.reference_edge == "left" else -left_edge_interior

    def map_point(self, point: Point) -> MappedPoint:
        base = np.array(self.edge_bottom, dtype=float)
        p = np.array(point, dtype=float)
        delta = p - base
        scale = self.metres_per_pixel
        y_m = float(np.dot(delta, self.edge_unit) * scale)
        x_from_reference_m = float(np.dot(delta, self.interior_unit) * scale)
        x_m = x_from_reference_m if self.reference_edge == "left" else self.wall_width_m - x_from_reference_m
        warnings = [
            "Approximate partial-wall mapping used; horizontal distance relies on a local scale assumption.",
        ]
        if x_m < -0.05 or x_m > self.wall_width_m + 0.05:
            warnings.append(
                "Estimated target is outside the horizontal wall span; review the screenshot or wording."
            )
        if y_m < -0.05 or y_m > self.wall_height_m + 0.05:
            warnings.append(
                "Estimated target is below ground or above the wall height; review the screenshot or wording."
            )
        return MappedPoint(
            x_m=x_m,
            y_m=y_m,
            confidence=ConfidenceLabel.LOW,
            warnings=warnings,
        )


def distance(a: Point, b: Point) -> float:
    return hypot(b[0] - a[0], b[1] - a[1])


def apply_homography(matrix: np.ndarray, point: Point) -> tuple[float, float]:
    vec = np.array([point[0], point[1], 1.0], dtype=float)
    result = matrix @ vec
    if abs(result[2]) <= 1e-12:
        raise ValueError("Homography produced a point at infinity.")
    return float(result[0] / result[2]), float(result[1] / result[2])


def solve_homography(src_points: Sequence[Point], dst_points: Sequence[Point]) -> np.ndarray:
    """Solve a 3x3 homography from four image/plane point pairs.

    The equation is solved using a standard DLT-style linear system with h33 fixed to 1.
    Four non-degenerate correspondences are sufficient for the wall calibration use case.
    """

    if len(src_points) != 4 or len(dst_points) != 4:
        raise ValueError("Exactly four source and four destination points are required.")

    a_rows: list[list[float]] = []
    b_vals: list[float] = []
    for (u, v), (x, y) in zip(src_points, dst_points, strict=True):
        a_rows.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v])
        b_vals.append(x)
        a_rows.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v])
        b_vals.append(y)

    a = np.array(a_rows, dtype=float)
    b = np.array(b_vals, dtype=float)
    try:
        h = np.linalg.solve(a, b)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Wall geometry is degenerate and cannot produce a stable transform.") from exc

    matrix = np.array(
        [
            [h[0], h[1], h[2]],
            [h[3], h[4], h[5]],
            [h[6], h[7], 1.0],
        ],
        dtype=float,
    )
    return matrix


def polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for idx, (x1, y1) in enumerate(points):
        x2, y2 = points[(idx + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return 0.5 * total


def point_in_convex_quad(point: Point, quad: Sequence[Point]) -> bool:
    if len(quad) != 4:
        raise ValueError("A quadrilateral must contain exactly four points.")
    signs: list[float] = []
    px, py = point
    for idx, (x1, y1) in enumerate(quad):
        x2, y2 = quad[(idx + 1) % 4]
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        signs.append(cross)
    positive = all(value >= -1e-9 for value in signs)
    negative = all(value <= 1e-9 for value in signs)
    return positive or negative


def line_intersection(line_a: Line, line_b: Line) -> Point:
    """Return the intersection of two infinite lines."""

    (x1, y1), (x2, y2) = line_a
    (x3, y3), (x4, y4) = line_b
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) <= 1e-12:
        raise ValueError("Selected boundary lines are parallel or nearly parallel.")
    det_a = x1 * y2 - y1 * x2
    det_b = x3 * y4 - y3 * x4
    px = (det_a * (x3 - x4) - (x1 - x2) * det_b) / denominator
    py = (det_a * (y3 - y4) - (y1 - y2) * det_b) / denominator
    return float(px), float(py)


def build_wall_mapping_from_corners(
    corners_tl_tr_br_bl: Sequence[Point],
    wall_width_m: float,
    wall_height_m: float,
    *,
    image_size: tuple[int, int] | None = None,
) -> WallMapping:
    if len(corners_tl_tr_br_bl) != 4:
        raise ValueError("Full-wall mode requires four wall corners in TL, TR, BR, BL order.")
    if wall_width_m <= 0 or wall_height_m <= 0:
        raise ValueError("Wall width and height must be positive.")

    quad = tuple(corners_tl_tr_br_bl)  # type: ignore[arg-type]
    area = abs(polygon_area(quad))
    warnings: list[str] = []
    confidence = ConfidenceLabel.HIGH
    if area <= 25.0:
        raise ValueError("Wall corner quadrilateral is too small or degenerate.")

    if image_size is not None:
        width_px, height_px = image_size
        if any(
            point[0] < -0.25 * width_px
            or point[0] > 1.25 * width_px
            or point[1] < -0.25 * height_px
            or point[1] > 1.25 * height_px
            for point in quad
        ):
            warnings.append(
                "One or more inferred wall corners are far outside the screenshot; review calibration."
            )
            confidence = ConfidenceLabel.MEDIUM

    dst = (
        (0.0, wall_height_m),
        (wall_width_m, wall_height_m),
        (wall_width_m, 0.0),
        (0.0, 0.0),
    )
    matrix = solve_homography(quad, dst)
    return WallMapping(
        matrix=matrix,
        wall_width_m=wall_width_m,
        wall_height_m=wall_height_m,
        confidence=confidence,
        warnings=warnings,
        source_quad=quad,
    )


def build_wall_mapping_from_boundary_lines(
    *,
    top: Line,
    right: Line,
    bottom: Line,
    left: Line,
    wall_width_m: float,
    wall_height_m: float,
    image_size: tuple[int, int] | None = None,
) -> WallMapping:
    tl = line_intersection(top, left)
    tr = line_intersection(top, right)
    br = line_intersection(bottom, right)
    bl = line_intersection(bottom, left)
    mapping = build_wall_mapping_from_corners(
        (tl, tr, br, bl),
        wall_width_m,
        wall_height_m,
        image_size=image_size,
    )
    warnings = list(mapping.warnings)
    if not warnings:
        warnings.append(
            "Boundary-line calibration inferred wall corners from extended lines; review if the wall is heavily cropped."
        )
        confidence = ConfidenceLabel.HIGH
    else:
        confidence = mapping.confidence
    return WallMapping(
        matrix=mapping.matrix,
        wall_width_m=mapping.wall_width_m,
        wall_height_m=mapping.wall_height_m,
        confidence=confidence,
        warnings=warnings,
        source_quad=mapping.source_quad,
    )


def estimate_quad_visibility(
    quad: Sequence[Point], image_size: tuple[int, int]
) -> ConfidenceLabel:
    width_px, height_px = image_size
    if all(0.0 <= x <= width_px and 0.0 <= y <= height_px for x, y in quad):
        return ConfidenceLabel.HIGH
    if all(
        -0.5 * width_px <= x <= 1.5 * width_px
        and -0.5 * height_px <= y <= 1.5 * height_px
        for x, y in quad
    ):
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.LOW


def round_decimetre(value: float) -> float:
    return round(value + 1e-9, 1)


def average_points(points: Iterable[Point]) -> Point:
    pts = list(points)
    if not pts:
        raise ValueError("At least one point is required.")
    return (
        sum(point[0] for point in pts) / len(pts),
        sum(point[1] for point in pts) / len(pts),
    )

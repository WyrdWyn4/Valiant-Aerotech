from __future__ import annotations

import math

from task_one_localizer.geometry import (
    ApproximateEdgeMapping,
    ConfidenceLabel,
    build_wall_mapping_from_boundary_lines,
    build_wall_mapping_from_corners,
)
from task_one_localizer.models import LineAnnotation


def test_full_corner_mapping_maps_rectangle_centres() -> None:
    mapping = build_wall_mapping_from_corners(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)],
        wall_width_m=10.0,
        wall_height_m=5.0,
        image_size=(100, 50),
    )
    center = mapping.map_point((50.0, 25.0))
    assert center.confidence == ConfidenceLabel.HIGH
    assert math.isclose(center.x_m, 5.0, abs_tol=1e-6)
    assert math.isclose(center.y_m, 2.5, abs_tol=1e-6)


def test_boundary_line_mapping_infers_corners() -> None:
    mapping = build_wall_mapping_from_boundary_lines(
        top=((0.0, 0.0), (100.0, 0.0)),
        right=((100.0, 0.0), (100.0, 50.0)),
        bottom=((100.0, 50.0), (0.0, 50.0)),
        left=((0.0, 50.0), (0.0, 0.0)),
        wall_width_m=10.0,
        wall_height_m=5.0,
        image_size=(100, 50),
    )
    point = mapping.map_point((25.0, 40.0))
    assert math.isclose(point.x_m, 2.5, abs_tol=1e-6)
    assert math.isclose(point.y_m, 1.0, abs_tol=1e-6)


def test_approximate_edge_mapping_scales_from_wall_height() -> None:
    mapping = ApproximateEdgeMapping(
        edge_bottom=(10.0, 100.0),
        edge_top=(10.0, 0.0),
        reference_edge="left",
        wall_width_m=20.0,
        wall_height_m=10.0,
    )
    point = mapping.map_point((40.0, 50.0))
    assert point.confidence == ConfidenceLabel.LOW
    assert math.isclose(point.x_m, 3.0, abs_tol=1e-6)
    assert math.isclose(point.y_m, 5.0, abs_tol=1e-6)
    assert point.warnings

"""
Geometry helpers for read-only Mission Planner / MAVLink monitoring.

All functions are data-processing only. They do not send commands to the aircraft.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from typing import Iterable, List, Optional, Sequence, Tuple

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two lat/lon points in metres."""
    lat1 = radians(a.lat)
    lat2 = radians(b.lat)
    dlat = radians(b.lat - a.lat)
    dlon = radians(b.lon - a.lon)
    x = sin(dlat / 2.0) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * atan2(sqrt(x), sqrt(1.0 - x))


def bearing_deg(a: GeoPoint, b: GeoPoint) -> float:
    """Initial bearing from point a to point b in degrees clockwise from north."""
    lat1 = radians(a.lat)
    lat2 = radians(b.lat)
    dlon = radians(b.lon - a.lon)
    y = sin(dlon) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (atan2(y, x) * 180.0 / 3.141592653589793 + 360.0) % 360.0


def local_xy_m(point: GeoPoint, origin: GeoPoint) -> Tuple[float, float]:
    """
    Convert lat/lon to approximate local tangent-plane x/y metres.

    x = east, y = north. Accurate enough for the competition-site scale.
    """
    lat0 = radians(origin.lat)
    x = radians(point.lon - origin.lon) * EARTH_RADIUS_M * cos(lat0)
    y = radians(point.lat - origin.lat) * EARTH_RADIUS_M
    return x, y


def _polygon_origin(poly: Sequence[GeoPoint]) -> GeoPoint:
    if not poly:
        raise ValueError("Polygon has no points")
    return GeoPoint(
        lat=sum(p.lat for p in poly) / len(poly),
        lon=sum(p.lon for p in poly) / len(poly),
    )


def point_in_polygon(point: GeoPoint, polygon: Sequence[GeoPoint]) -> bool:
    """
    Ray-casting point-in-polygon test for lat/lon polygon.

    Works for convex and non-convex polygons. The CONOPS states that boundaries may
    be non-convex, so this avoids convex-only assumptions.
    """
    if len(polygon) < 3:
        return True  # No usable polygon provided: do not generate false warnings.

    origin = _polygon_origin(polygon)
    x, y = local_xy_m(point, origin)
    poly_xy = [local_xy_m(p, origin) for p in polygon]

    inside = False
    j = len(poly_xy) - 1
    for i in range(len(poly_xy)):
        xi, yi = poly_xy[i]
        xj, yj = poly_xy[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _distance_point_to_segment_m(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-12:
        return sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    cx = ax + t * abx
    cy = ay + t * aby
    return sqrt((px - cx) ** 2 + (py - cy) ** 2)


def distance_to_polygon_edge_m(point: GeoPoint, polygon: Sequence[GeoPoint]) -> Optional[float]:
    """Minimum distance from a point to any polygon edge in metres."""
    if len(polygon) < 2:
        return None
    origin = _polygon_origin(polygon)
    px, py = local_xy_m(point, origin)
    poly_xy = [local_xy_m(p, origin) for p in polygon]
    distances: List[float] = []
    for i in range(len(poly_xy)):
        ax, ay = poly_xy[i]
        bx, by = poly_xy[(i + 1) % len(poly_xy)]
        distances.append(_distance_point_to_segment_m(px, py, ax, ay, bx, by))
    return min(distances) if distances else None

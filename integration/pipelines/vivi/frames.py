"""Coordinate-frame helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .vector import Vec3


@dataclass
class LocalFrame:
    """Small local tangent-plane converter from latitude/longitude to ENU.

    This is not high-accuracy geodesy over large distances. It is a practical
    local approximation for a small competition scene.

    The building GPS coordinate from the organizers should not be treated as a
    building centre or corner. It can be used to navigate to the building. Once
    the building is found, survey() establishes the local geometry.
    """

    lat0_deg: float
    lon0_deg: float
    alt0_m: float = 0.0

    def lla_to_enu(self, lat_deg: float, lon_deg: float, alt_m: float = 0.0) -> Vec3:
        earth_radius_m = 6378137.0
        lat0 = math.radians(self.lat0_deg)
        dlat = math.radians(lat_deg - self.lat0_deg)
        dlon = math.radians(lon_deg - self.lon0_deg)
        east = dlon * math.cos(lat0) * earth_radius_m
        north = dlat * earth_radius_m
        up = alt_m - self.alt0_m
        return Vec3(east, north, up)

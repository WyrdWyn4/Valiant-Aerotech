"""Minimal 3D vector math used by the field geometry code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import math

from .constants import EPS


@dataclass(frozen=True)
class Vec3:
    """Simple 3D vector in local ENU metres.

    A tiny vector class is used instead of numpy so this package can run on a
    field laptop with a minimal Python installation.
    """

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vec3":
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> "Vec3":
        if abs(scalar) < EPS:
            raise ZeroDivisionError("Cannot divide vector by zero.")
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def norm(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> "Vec3":
        n = self.norm()
        if n < EPS:
            raise ValueError("Cannot normalize a near-zero vector.")
        return self / n

    def horizontal(self) -> "Vec3":
        """Return this vector with z removed.

        Wall naming and ground distance calculations are horizontal calculations,
        so z should not influence them.
        """
        return Vec3(self.x, self.y, 0.0)

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


UP = Vec3(0.0, 0.0, 1.0)

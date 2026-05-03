"""Camera mode definitions for Vivi."""

from enum import IntEnum


class CameraMode(IntEnum):
    """Camera selector used by the operator/UI.

    The camera can only be front or down:
        FRONT = 1
        DOWN  = 0
    """

    DOWN = 0
    FRONT = 1

"""Small demo for testing the modular Vivi package without MAVLink/camera input."""

from __future__ import annotations

from pathlib import Path

from .detection import mark_target
from .modes import CameraMode
from .pose import Pose
from .report import parse
from .survey import setup
from .vector import Vec3


def demo(output_dir: str | Path = ".") -> Path:
    """Create a demo report using synthetic geometry.

    This is not flight code. It lets the team run `python run_demo.py` or
    `python -m vivi.demo` and verify the package/report format.
    """
    # Synthetic rectangular building:
    # A is the shared corner; B and C are adjacent to A.
    A = Vec3(0.0, 0.0, 0.0)
    B = Vec3(12.0, 0.0, 0.0)
    C = Vec3(0.0, 8.0, 0.0)

    # Synthetic door on one face. Any 3 of these 4 would work; we provide 3.
    door_pts = [
        Vec3(5.0, 0.0, 0.0),  # bottom-left
        Vec3(7.0, 0.0, 0.0),  # bottom-right
        Vec3(5.0, 0.0, 2.0),  # top-left
    ]

    model = setup(
        building_corners=[A, B, C],
        building_height_m=4.0,
        door_corners=door_pts,
        save_model_path=Path(output_dir) / "vivi_building_model_debug.json",
    )

    # Example front-camera target:
    # Drone is south of the building, facing north, camera centre hits south wall.
    front_pose = Pose(position=Vec3(6.8, -4.0, 1.6), yaw_deg=0.0, pitch_deg=0.0, roll_deg=0.0)
    front_event = mark_target("red", CameraMode.FRONT, front_pose, selected_face="south")

    # Example down-camera target on the ground near west face.
    down_pose = Pose(position=Vec3(-3.0, 2.5, 3.0), yaw_deg=0.0, pitch_deg=0.0, roll_deg=0.0)
    down_event = mark_target("blue", CameraMode.DOWN, down_pose)

    return parse([front_event, down_event], model, "Valiant_Aerotech", output_dir=output_dir)


if __name__ == "__main__":
    path = demo()
    print(f"Wrote demo report: {path}")

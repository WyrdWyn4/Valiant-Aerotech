"""Standalone orchestration file for Vivi Task One.

Run directly:

    python integration/pipelines/vivi/main.py

or as a module:

    python -m integration.pipelines.vivi.main

This file is intentionally the only file you run during field testing. Other
files such as survey.py, telemetry.py, detection.py, localization.py, and
report.py are library modules.
"""

from __future__ import annotations

# -----------------------------------------------------------------------------
# Standalone-file bootstrap
# -----------------------------------------------------------------------------
# This allows direct execution while preserving clean relative imports below.
# File location assumed:
#   <project_root>/integration/pipelines/vivi/main.py
# parents[3] = <project_root>
# -----------------------------------------------------------------------------
if __package__ is None or __package__ == "":
    import sys
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    __package__ = "integration.pipelines.vivi"

import argparse
import time
from pathlib import Path

from .detection import TargetEvent, detect, mark_target
from .modes import CameraMode
from .pose import CameraConfig, Pose
from .report import parse
from .survey import setup
from .telemetry import MavlinkTelemetry
from .vector import Vec3


# -----------------------------------------------------------------------------
# Detector placeholder
# -----------------------------------------------------------------------------
# The live CV package is not integrated here yet. For now, the operator types the
# colour after visually confirming the centred target. This still exercises the
# actual telemetry-driven coordinate pipeline.
# -----------------------------------------------------------------------------

def manual_detector(frame=None) -> str:
    return input("Detected target colour [black/white/red/yellow/blue/green]: ").strip().lower()


# -----------------------------------------------------------------------------
# Telemetry helpers
# -----------------------------------------------------------------------------

def get_current_pose(telemetry: MavlinkTelemetry) -> Pose:
    """Return the latest MAVLink-derived Pose.

    This replaces the earlier manual x/y/z/yaw/pitch/roll input. If it times out,
    it means MAVProxy/Mission Planner is not forwarding the required messages or
    the connection string is wrong.
    """
    return telemetry.wait_for_pose(timeout_s=3.0)


def capture_point(name: str, telemetry: MavlinkTelemetry) -> Vec3:
    """Capture one survey point from the current MAVLink pose.

    Field use:
        1. Operator places/aims Vivi at the desired corner/reference point.
        2. Programmer presses Enter.
        3. This function records the current automatic x/y/z from telemetry.
    """
    print(f"\nCapture point: {name}")
    print("Position Vivi at this point, then press Enter.")
    input("Ready to capture? ")
    pose = get_current_pose(telemetry)
    print(
        f"Captured {name}: "
        f"east={pose.position.x:.2f}, north={pose.position.y:.2f}, up={pose.position.z:.2f}, "
        f"yaw={pose.yaw_deg:.1f}, pitch={pose.pitch_deg:.1f}, roll={pose.roll_deg:.1f}"
    )
    return pose.position


# -----------------------------------------------------------------------------
# Setup/survey orchestration
# -----------------------------------------------------------------------------

def run_setup(telemetry: MavlinkTelemetry):
    """Run the scene survey using MAVLink-derived coordinates."""
    print("\n=== SETUP / SURVEY ===")
    print("Capture building corners in this order:")
    print("  A = shared corner")
    print("  B = adjacent corner along one wall")
    print("  C = adjacent corner along perpendicular wall")
    print("A, B, and C must not be collinear.")

    building_height_m = float(input("\nBuilding height [m]: "))

    A = capture_point("Building corner A, shared corner", telemetry)
    B = capture_point("Building corner B, adjacent to A", telemetry)
    C = capture_point("Building corner C, adjacent to A", telemetry)

    door_count_text = input("\nHow many door-frame corners will you capture? [3 or 4, default 3]: ").strip()
    door_count = int(door_count_text or "3")
    if door_count < 3:
        raise ValueError("At least 3 door-frame corners are required.")
    if door_count > 4:
        print("More than 4 was entered; capturing 4 door-frame corners.")
        door_count = 4

    door_points: list[Vec3] = []
    for i in range(door_count):
        door_points.append(capture_point(f"Door-frame corner {i + 1}", telemetry))

    model = setup(
        building_corners=[A, B, C],
        building_height_m=building_height_m,
        door_corners=door_points,
        save_model_path="vivi_building_model_debug.json",
    )

    print("\nSetup complete.")
    print("Detected wall faces:")
    for wall in model.walls:
        door_status = "with door" if wall.door is not None else "no door"
        print(f"  - {wall.name} face, heading {wall.heading_deg:.1f} deg, {door_status}")

    return model


# -----------------------------------------------------------------------------
# Target marking orchestration
# -----------------------------------------------------------------------------

def run_target_search(model, telemetry: MavlinkTelemetry) -> list[TargetEvent]:
    """Main operator loop for marking targets.

    Because detect() currently returns only colour, the target must be centred in
    the active camera before pressing M.
    """
    print("\n=== TARGET SEARCH ===")

    target_events: list[TargetEvent] = []
    camera_mode = CameraMode.FRONT

    while True:
        print("\nCommands:")
        print("  f = front camera mode")
        print("  d = down camera mode")
        print("  m = mark target using current MAVLink pose")
        print("  v = view latest MAVLink pose")
        print("  u = undo last target")
        print("  p = parse/write report")
        print("  q = quit without writing")
        print("")
        print(f"Current camera mode: {camera_mode.name}")
        print("Wall face selection: automatic for FRONT camera")
        print(f"Targets marked: {len(target_events)}")

        cmd = input("\nCommand: ").strip().lower()

        if cmd == "f":
            camera_mode = CameraMode.FRONT
            print("Camera mode set to FRONT.")

        elif cmd == "d":
            camera_mode = CameraMode.DOWN
            print("Camera mode set to DOWN.")

        elif cmd == "v":
            telemetry.print_pose()

        elif cmd == "m":
            print("\nBefore marking:")
            print("1. Confirm correct camera mode.")
            print("2. Centre the coloured circle in the camera view.")
            print("3. FRONT mode will automatically choose the wall using Vivi heading and wall-plane intersections.")
            input("Press Enter when target is centred... ")

            # Replace frame=None with the real camera frame when CV is integrated.
            frame = None
            colour = detect(frame, detector=manual_detector)
            pose = get_current_pose(telemetry)

            event = mark_target(
                colour=colour,
                camera_mode=camera_mode,
                pose=pose,
                selected_face=None,  # wall face is selected automatically during localization
            )
            target_events.append(event)

            print(
                f"Marked target {len(target_events)}: {colour}, {camera_mode.name}, "
                f"east={pose.position.x:.2f}, north={pose.position.y:.2f}, up={pose.position.z:.2f}, "
                f"yaw={pose.yaw_deg:.1f}"
            )

        elif cmd == "u":
            if target_events:
                removed = target_events.pop()
                print(f"Removed last target: {removed.colour}, {removed.camera_mode.name}")
            else:
                print("No targets to undo.")

        elif cmd == "p":
            return target_events

        elif cmd == "q":
            raise SystemExit("Quit without writing report.")

        else:
            print("Unknown command.")


# -----------------------------------------------------------------------------
# Main orchestration
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Vivi Task 1 target localization orchestrator")
    parser.add_argument("--connection", default="udpin:127.0.0.1:14550", help="MAVLink connection string")
    parser.add_argument("--team", default=None, help="Team name for output file")
    parser.add_argument("--camera-offset-cm", type=float, default=None, help="Camera vertical offset below GPS/autopilot origin")
    args = parser.parse_args()

    print("Vivi Task 1 Target Localization Orchestrator")

    team_name = args.team or input("Team name for output file: ").strip() or "Valiant_Aerotech"
    if args.camera_offset_cm is None:
        camera_offset_cm = float(input("Camera vertical offset below GPS/autopilot [cm]: ") or "10")
    else:
        camera_offset_cm = args.camera_offset_cm

    camera = CameraConfig(offset_body_m=Vec3(0.0, 0.0, -camera_offset_cm / 100.0))

    telemetry = MavlinkTelemetry(args.connection)
    telemetry.connect(wait_heartbeat=True)
    telemetry.start()

    print("Waiting for first complete pose...")
    first_pose = telemetry.wait_for_pose(timeout_s=10.0)
    print(
        "Telemetry pose ready: "
        f"east={first_pose.position.x:.2f}, north={first_pose.position.y:.2f}, up={first_pose.position.z:.2f}, "
        f"yaw={first_pose.yaw_deg:.1f}, pitch={first_pose.pitch_deg:.1f}, roll={first_pose.roll_deg:.1f}"
    )

    try:
        model = run_setup(telemetry)
        target_events = run_target_search(model, telemetry)

        output_path = parse(
            events=target_events,
            model=model,
            team_name=team_name,
            output_dir=Path("."),
            camera=camera,
            include_debug_comments=True,
        )

        print("\nReport written:")
        print(output_path)
        print("\nOpen this file, review it, then upload it before the flight window ends.")
    finally:
        telemetry.stop()


if __name__ == "__main__":
    main()

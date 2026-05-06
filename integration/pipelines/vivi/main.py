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

    THIS_FILE = Path(__file__).resolve()
    PROJECT_ROOT = THIS_FILE.parents[3]

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    __package__ = ".".join(THIS_FILE.parent.relative_to(PROJECT_ROOT).parts)

import argparse
from pathlib import Path
from typing import Optional

from .constants import ALLOWED_COLOURS
from .detection import TargetEvent, detect, mark_target
from .modes import CameraMode
from .pose import CameraConfig, Pose
from .report import parse
from .survey import setup
from .telemetry import MavlinkTelemetry
from .vector import Vec3


# -----------------------------------------------------------------------------
# Input helpers: field script should not crash on bad operator input
# -----------------------------------------------------------------------------

def prompt_text(prompt: str, *, default: Optional[str] = None, allow_empty: bool = False) -> str:
    """Prompt until a usable string is entered."""
    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        if default is not None:
            return default
        if allow_empty:
            return ""
        print("Input cannot be empty. Please enter a value.")


def prompt_float(prompt: str, *, default: Optional[float] = None, min_value: Optional[float] = None) -> float:
    """Prompt until a valid float is entered."""
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number, for example 3 or 3.0.")
            continue
        if min_value is not None and value < min_value:
            print(f"Please enter a value greater than or equal to {min_value}.")
            continue
        return value


def prompt_yes_no(prompt: str, *, default: bool = True) -> bool:
    """Prompt for y/n without raising on invalid input."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        raw = input(prompt + suffix).strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please answer y or n.")


def prompt_colour() -> str:
    """Prompt until the target colour is one of the allowed Task 1 colours."""
    allowed = "/".join(sorted(ALLOWED_COLOURS))
    while True:
        colour = input(f"Detected target colour [{allowed}]: ").strip().lower()
        if colour in ALLOWED_COLOURS:
            return colour
        print(f"Invalid colour. Allowed colours: {', '.join(sorted(ALLOWED_COLOURS))}.")

def prompt_target_face(model, pose: Pose) -> Optional[str]:
    """Ask for an optional wall-face override for FRONT mode."""
    available = {wall.name for wall in model.walls}
    closest = model.nearest_wall_to_ground_point(pose.position).name

    while True:
        raw = input(
            f"Target wall face [Enter/auto = closest ({closest}), "
            "or north/east/south/west]: "
        ).strip().lower()

        if raw in {"", "a", "auto"}:
            return None

        if raw in available:
            return raw

        print(f"Invalid face. Available faces: {', '.join(sorted(available))}, or auto.")


def prompt_front_target_height(model, pose: Pose, camera: CameraConfig) -> Optional[float]:
    """Ask for a wall-target height when current altitude is not usable.

    Return None to use the current camera height. Return a float to store a
    manual height above ground in the target event notes.
    """
    current_height = pose.position.z + camera.offset_body_m.z - model.ground_z
    current_ok = -0.2 <= current_height <= model.height_m + 0.5

    while True:
        if current_ok:
            raw = input(
                f"Target height above ground [m, Enter = current {current_height:.1f} m]: "
            ).strip()
            if not raw:
                return None
        else:
            raw = input(
                f"Target height above ground [m, required because current height "
                f"{current_height:.1f} m is outside 0.0-{model.height_m:.1f} m]: "
            ).strip()
            if not raw:
                print("Please enter the target height above ground for this wall target.")
                continue

        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number, for example 3 or 3.0.")
            continue

        if value < 0.0 or value > model.height_m:
            print(f"Please enter a height from 0.0 to {model.height_m:.1f} m.")
            continue

        return value


# -----------------------------------------------------------------------------
# Detector placeholder
# -----------------------------------------------------------------------------
# The live CV package is not integrated here yet. For now, the operator types the
# colour after visually confirming the centred target. This still exercises the
# actual telemetry-driven coordinate pipeline.
# -----------------------------------------------------------------------------

def manual_detector(frame=None) -> str:
    return prompt_colour()


# -----------------------------------------------------------------------------
# Telemetry helpers
# -----------------------------------------------------------------------------

def get_current_pose(telemetry: MavlinkTelemetry) -> Pose:
    """Return the latest MAVLink-derived Pose, retrying instead of crashing."""
    while True:
        try:
            return telemetry.wait_for_pose(timeout_s=3.0)
        except Exception as exc:
            print(f"Telemetry pose is not ready: {exc}")
            print("Check Mission Planner/MAVProxy forwarding and the connection string.")
            input("Press Enter to retry pose capture...")


def capture_point(name: str, telemetry: MavlinkTelemetry) -> Vec3:
    """Capture one survey point from the current MAVLink pose.

    Field use:
        1. Operator places/aims Vivi at the desired corner/reference point.
        2. Programmer presses Enter.
        3. This function records the current automatic x/y/z from telemetry.
    """
    while True:
        print(f"\nCapture point: {name}")
        print("Position Vivi at this point, then press Enter.")
        input("Ready to capture? ")
        pose = get_current_pose(telemetry)
        print(
            f"Captured {name}: "
            f"east={pose.position.x:.2f}, north={pose.position.y:.2f}, up={pose.position.z:.2f}, "
            f"yaw={pose.yaw_deg:.1f}, pitch={pose.pitch_deg:.1f}, roll={pose.roll_deg:.1f}"
        )
        if prompt_yes_no("Keep this point?", default=True):
            return pose.position
        print("Point rejected. Capture it again.")


# -----------------------------------------------------------------------------
# Setup/survey orchestration
# -----------------------------------------------------------------------------

def run_setup(telemetry: MavlinkTelemetry):
    """Run the scene survey using MAVLink-derived coordinates."""
    while True:
        print("\n=== SETUP / SURVEY ===")
        print("Capture building corners in this order:")
        print("  A = shared corner")
        print("  B = adjacent corner along one wall")
        print("  C = adjacent corner along perpendicular wall")
        print("A, B, and C must not be collinear.")
        print("")
        print("Door workflow:")
        print("  Capture only the TOP TWO door-frame corners.")
        print("  The bottom two door corners are assumed to be on the ground.")

        building_height_m = prompt_float("\nBuilding height [m]: ", min_value=0.1)

        A = capture_point("Building corner A, shared corner", telemetry)
        B = capture_point("Building corner B, adjacent to A", telemetry)
        C = capture_point("Building corner C, adjacent to A", telemetry)

        door_points: list[Vec3] = []
        if prompt_yes_no("Capture a door reference for this building?", default=True):
            door_points.append(capture_point("Door TOP corner 1", telemetry))
            door_points.append(capture_point("Door TOP corner 2", telemetry))

        try:
            model = setup(
                building_corners=[A, B, C],
                building_height_m=building_height_m,
                door_top_corners=door_points or None,
                save_model_path="vivi_building_model_debug.json",
            )
        except Exception as exc:
            print(f"Setup could not build a valid model: {exc}")
            print("Please re-capture the setup points.")
            continue

        print("\nSetup complete.")
        print("Detected wall faces:")
        for wall in model.walls:
            door_status = "with door" if wall.door is not None else "no door"
            print(f"  - {wall.name} face, outward heading {wall.heading_deg:.1f} deg, {door_status}")
            if wall.door is not None:
                print(
                    f"      door: top={wall.door.top_z:.2f} m above ground, "
                    f"width={abs(wall.door.right_u - wall.door.left_u):.2f} m"
                )

        if prompt_yes_no("Keep this setup model?", default=True):
            return model
        print("Setup rejected. Starting setup again.")


# -----------------------------------------------------------------------------
# Target marking orchestration
# -----------------------------------------------------------------------------

def run_target_search(model, telemetry: MavlinkTelemetry, camera: CameraConfig) -> Optional[list[TargetEvent]]:
    """Main operator loop for marking targets.

    FRONT mode uses current-position projection onto the selected/closest wall.
    DOWN mode still uses the down-camera ray to project to ground.
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
        print("FRONT mode: position projection onto selected/closest wall")
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
            if camera_mode == CameraMode.FRONT:
                print("2. Move Vivi horizontally in line with the wall target.")
                print("3. Facing/yaw does not matter; FRONT mode projects current position onto the wall.")
                print("4. Stay clearly in front of the intended face, or manually choose the face after capture.")
                input("Press Enter when Vivi is aligned with the target position... ")
            else:
                print("2. Centre the ground target under the down camera.")
                input("Press Enter when target is centred... ")

            try:
                # Capture pose immediately after Enter so later typing does not
                # change the geometry point being recorded.
                pose = get_current_pose(telemetry)

                # Replace frame=None with the real camera frame when CV is integrated.
                frame = None
                colour = detect(frame, detector=manual_detector)

                selected_face = None
                notes = ""

                if camera_mode == CameraMode.FRONT:
                    selected_face = prompt_target_face(model, pose)
                    target_height_m = prompt_front_target_height(model, pose, camera)
                    if target_height_m is not None:
                        notes = f"target_height_m={target_height_m:.3f}"

                event = mark_target(
                    colour=colour,
                    camera_mode=camera_mode,
                    pose=pose,
                    selected_face=selected_face,
                    notes=notes,
                )
            except Exception as exc:
                print(f"Target was not marked: {exc}")
                print("Please correct the input and try marking the target again.")
                continue

            target_events.append(event)

            face_text = f", face={event.selected_face or 'auto'}" if camera_mode == CameraMode.FRONT else ""
            print(
                f"Marked target {len(target_events)}: {colour}, {camera_mode.name}{face_text}, "
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
            print("Quit selected. No report will be written.")
            return None

        else:
            print("Unknown command. Please enter f, d, m, v, u, p, or q.")


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

    team_name = args.team or prompt_text("Team name for output file: ", default="Valiant_Aerotech")
    if args.camera_offset_cm is None:
        camera_offset_cm = prompt_float("Camera vertical offset below GPS/autopilot [cm, default 10]: ", default=10.0, min_value=0.0)
    else:
        camera_offset_cm = args.camera_offset_cm

    camera = CameraConfig(offset_body_m=Vec3(0.0, 0.0, -camera_offset_cm / 100.0))

    telemetry = MavlinkTelemetry(args.connection)
    try:
        telemetry.connect(wait_heartbeat=True)
        telemetry.start()
    except Exception as exc:
        print(f"Could not start MAVLink telemetry: {exc}")
        print("Fix the connection or dependency issue, then run the script again.")
        return

    try:
        print("Waiting for first complete pose...")
        first_pose = get_current_pose(telemetry)
        print(
            "Telemetry pose ready: "
            f"east={first_pose.position.x:.2f}, north={first_pose.position.y:.2f}, up={first_pose.position.z:.2f}, "
            f"yaw={first_pose.yaw_deg:.1f}, pitch={first_pose.pitch_deg:.1f}, roll={first_pose.roll_deg:.1f}"
        )

        model = run_setup(telemetry)
        target_events = run_target_search(model, telemetry, camera)
        if target_events is None:
            return

        while True:
            try:
                output_path = parse(
                    events=target_events,
                    model=model,
                    team_name=team_name,
                    output_dir=Path("."),
                    camera=camera,
                    include_debug_comments=True,
                )
                break
            except Exception as exc:
                print(f"Report could not be written: {exc}")
                team_name = prompt_text("Re-enter team name for output file: ", default="Valiant_Aerotech")

        print("\nReport written:")
        print(output_path)
        print("\nOpen this file, review it, then upload it before the flight window ends.")
    finally:
        telemetry.stop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by operator. No report was written.")

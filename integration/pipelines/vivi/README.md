# Vivi Task 1 Pipeline

This folder contains the Vivi target-localization and reporting pipeline for AEAC Task 1.

Vivi uses MAVLink telemetry, a surveyed building model, camera mode, and target colour detection to generate the required `Task_1_<team_name>_targets.txt` report.

---

## Files

```text
integration/pipelines/vivi/
├── __init__.py
├── constants.py       # allowed target colours and shared constants
├── demo.py            # synthetic demo without MAVLink
├── detection.py       # detect() and mark_target()
├── frames.py          # local GPS-to-ENU helper
├── geometry.py        # yaw/pitch/roll and camera-ray geometry
├── localization.py    # target projection onto wall/ground
├── main.py            # run this file for field operation
├── model.py           # BuildingModel, WallPlane, DoorReference
├── modes.py           # CameraMode enum
├── pose.py            # Pose and CameraConfig
├── report.py          # parse() report writer
├── survey.py          # setup()/survey() model creation
├── telemetry.py       # MAVLink telemetry reader
└── vector.py          # Vec3 helper
```

---

## Run

From the project root:

```powershell
cd C:\Users\walee\OneDrive\Desktop\Projects\Valiant-Aerotech
& c:\python314\python.exe .\integration\pipelines\vivi\main.py
```

With options:

```powershell
& c:\python314\python.exe .\integration\pipelines\vivi\main.py --connection udpin:127.0.0.1:14550 --team "Valiant Aerotech" --camera-offset-cm 10
```

---

## MAVLink input

Default connection:

```text
udpin:127.0.0.1:14550
```

Messages used:

```text
LOCAL_POSITION_NED  -> position
ATTITUDE            -> yaw, pitch, roll
GLOBAL_POSITION_INT -> fallback position
VFR_HUD             -> fallback heading
```

Internal coordinate frame:

```text
x = east
y = north
z = up
```

MAVLink NED is converted as:

```text
east  = y_ned
north = x_ned
up    = -z_ned
```

---

## Field steps

1. Start Mission Planner/MAVProxy and confirm Vivi telemetry is being forwarded.
2. Run `main.py`.
3. Enter team name, camera offset, and building height.
4. Capture building corners:

```text
A = shared corner
B = adjacent corner along one wall
C = adjacent corner along perpendicular wall
```

5. Capture any 3 or 4 door-frame corners.
6. Enter target-search mode.
7. Select camera mode:

```text
f = front camera
d = down camera
```

8. Centre the target in the selected camera view.
9. Press:

```text
m
```

10. Enter or allow detection of target colour.
11. Repeat for all targets.
12. Press:

```text
p
```

13. Review the generated file in:

```text
logs/Task_1_<team_name>_targets.txt
```

---

## Operator commands

```text
f = front camera mode
d = down camera mode
m = mark target using current MAVLink pose
v = view latest MAVLink pose
u = undo last target
p = parse/write report
q = quit without writing
```

Wall face selection for the front camera is automatic. The system chooses the wall by intersecting the front-camera ray with the surveyed wall planes.

---

## Important operating rule

`detect()` currently returns only colour. Therefore, before pressing `m`, the operator must centre the target in the camera view.

If `detect()` later returns a target pixel centre, this requirement can be relaxed.

---

## Output

The final report is written to:

```text
logs/Task_1_<team_name>_targets.txt
```

Example:

```text
logs/Task_1_Valiant_Aerotech_targets.txt
```

The report uses landmark-based language and avoids raw GPS or coordinate triples.

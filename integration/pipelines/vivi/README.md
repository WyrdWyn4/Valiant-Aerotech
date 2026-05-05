# Vivi Task 1 Pipeline

## Quick Version

Vivi turns live MAVLink pose data and a quick building survey into the required Task 1 target-location report.

Run it from the repo root:

```powershell
python .\integration\pipelines\vivi\main.py --connection udpin:127.0.0.1:14550 --team "Valiant Aerotech"
```

During setup, capture:

1. Three adjacent building corners: `A`, `B`, `C`
2. The top two door-frame corners, if a useful door is visible
3. Each target after centring it in the active camera view

The output is:

```text
Task_1_<team_name>_targets.txt
```

Review the file before uploading it to Google Drive at the end of the flight window.

## Details

### What The Pipeline Does

Vivi creates a local model of the building, names the four wall faces, projects each marked target onto a wall or the ground, and writes firefighter-readable descriptions.

The report should describe targets using landmarks such as walls, corners, ground distance, and the door. It should not use GPS coordinates or raw local coordinate triples.

### Field Workflow

1. Start Mission Planner or MAVProxy.
2. Forward MAVLink to `udpin:127.0.0.1:14550`.
3. Run `main.py`.
4. Enter team name, camera offset, and building height.
5. Capture the three building corners in order:

```text
A = shared corner
B = adjacent corner along one wall
C = adjacent corner along the perpendicular wall
```

6. Capture the top two door corners. The bottom of the door is assumed to be on the ground.
7. Use `f` or `d` to set front/down camera mode.
8. Centre the target in the camera view.
9. Press `m` and enter the target colour.
10. Press `p` to write the report.

### Operator Commands

```text
f = front camera mode
d = down camera mode
m = mark target using current MAVLink pose
v = view latest MAVLink pose
u = undo last target
p = parse/write report
q = quit without writing
```

### MAVLink Data Used

```text
LOCAL_POSITION_NED  -> horizontal position
GLOBAL_POSITION_INT -> preferred relative altitude
VFR_HUD             -> backup relative altitude and heading
ATTITUDE            -> yaw, pitch, roll
```

Internal coordinates are ENU:

```text
x = east
y = north
z = up
```

### ConOps Rules To Remember

- Task 1 targets are coloured circles: black, white, red, yellow, blue, or green.
- Locations must be clear in 3D space.
- Distances should only imply decimetre accuracy.
- GPS and raw coordinate triples are not acceptable in the final report.
- The building GPS point is only a locator, not a corner, centre, or wall reference.

### File Map

```text
main.py          field operator script
telemetry.py     MAVLink reader and altitude fallback logic
survey.py        building and door survey setup
model.py         wall, door, and building model objects
localization.py  target projection onto wall/ground
report.py        Task 1 text report writer
detection.py     detector hook and manual colour fallback
demo.py          synthetic demo without MAVLink
```

### Important Limitations

- `detect()` currently only returns a colour, so the target must be centred before pressing `m`.
- The trained YOLO `.pt` model still needs a small adapter before automatic detection is complete.
- Debug or review lines should be removed before official upload if they appear in the generated report.

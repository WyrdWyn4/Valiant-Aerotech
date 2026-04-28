# Valiant Aerotech Task 1 Read-Only MAVLink Scripts

These scripts are for **data processing only**. They do not control flight operations.

They never send MAVLink commands. They do not arm, disarm, change modes, upload missions, set waypoints, override RC, move servos, trigger payload release, or command takeoff/landing. They only receive MAVLink telemetry, log messages, compute derived state, count Vulcan lap progress, ingest Vivi computer-vision detections, and generate operator-reviewed logs/reports.

## Files

```text
vulcan_monitor.py                 Vulcan telemetry, lap, boundary, and delivery-event monitor
vivi_monitor.py                   Vivi telemetry, CV-detection, and target-report monitor
common/base_monitor.py            Shared read-only MAVLink receive/log/alert loop
common/mavlink_state.py           MAVLink message field extraction
common/geometry.py                Boundary, distance, and lap-gate geometry helpers
common/logging_utils.py           CSV logging helpers
configs/vulcan_config.example.json
configs/vivi_config.example.json
requirements.txt
```

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell/CMD
# source .venv/bin/activate      # macOS/Linux
pip install -r requirements.txt
```

## Mission Planner / MAVProxy connection idea

Use one UDP endpoint per vehicle. For example:

- Vulcan monitor: `udpin:127.0.0.1:14550`
- Vivi monitor: `udpin:127.0.0.1:14560`

The exact forwarding setup depends on your Mission Planner / MAVProxy layout. The scripts only need a MAVLink UDP stream like this reference pattern:

```python
from pymavlink import mavutil
master = mavutil.mavlink_connection('udpin:127.0.0.1:14550')
master.wait_heartbeat()
while True:
    msg = master.recv_match(blocking=True)
```

## Before the real Task 1 run

Copy the example configs and replace placeholders with the actual data released by the organizers:

```bash
copy configs\vulcan_config.example.json configs\vulcan_config.json
copy configs\vivi_config.example.json configs\vivi_config.json
```

Update:

- `mavlink_connection`
- `altitude_limit_m`
- `soft_boundary`
- `hard_boundary`
- Vulcan `lap_waypoints`
- Vulcan `fire_scene`
- Vulcan `staging_pads`, if you have pad estimates
- Vivi `cv_detection_jsonl`, if the CV package writes detections to a file

## Run

In separate terminals:

```bash
python vulcan_monitor.py --config configs/vulcan_config.json
python vivi_monitor.py --config configs/vivi_config.json
```

Or override the connection from the command line:

```bash
python vulcan_monitor.py --config configs/vulcan_config.json --connect udpin:127.0.0.1:14550
python vivi_monitor.py --config configs/vivi_config.json --connect udpin:127.0.0.1:14560
```

## Vulcan terminal commands

Commands are event markers only. They do not control the aircraft.

```text
event <name> [details]
phase laps|transit|delivery|return|landed [notes]
vivi stable_for_launch|launched|clear [notes]
attempt <radio|oxygen|ladder> <pad_id> [notes]
touch <radio|oxygen|ladder> <pad_id> [notes]
release <radio|oxygen|ladder> <pad_id> [notes]
confirm <radio|oxygen|ladder> <pad_id> [notes]
pads
status
quit
```

Example:

```text
phase laps outbound scoring started
vivi stable_for_launch stable low hover near pads
attempt radio A over pad A
touch radio A payload touching ground
release radio A released after ground contact
confirm radio A fully detached
phase return equipment delivery complete
```

## Vivi terminal commands

Commands are event markers/report inputs only. They do not control the aircraft.

```text
event <name> [details]
phase mounted|launched|search|return|landed [notes]
launched [notes]
clear [notes]
detect <target_id> <colour> [confidence] [frame/image ref]
target <target_id> <colour> <landmark-based 3D description>
report
status
quit
```

Example:

```text
launched clean takeoff from Vulcan stand
clear 5 m horizontal separation from Vulcan
detect T01 red 0.91 frame_01042.jpg
target T01 red On the east face of the building, approximately 1.2 m above ground and 0.8 m left of the southeast corner when facing the wall from outside.
report
```

## CV JSONL format for Vivi

If the standalone CV package writes to `cv_detections.jsonl`, use one JSON object per line:

```json
{"target_id":"T01","colour":"red","confidence":0.91,"frame_ref":"frame_01042.jpg","image_ref":"target_T01.jpg","operator_description":"On the east face of the building, approximately 1.2 m above ground and 0.8 m left of the southeast corner when facing the wall from outside."}
```

`operator_description` is optional. If missing, the operator can add the final landmark-based description from the Vivi terminal using the `target` command.

## Output files

Each run creates a timestamped folder under `logs/`, such as:

```text
logs/Vulcan_20260428_180000_UTC/
logs/Vivi_20260428_180000_UTC/
```

Common logs:

- `mavlink_messages.csv` — all received MAVLink messages, fields stored as JSON
- `telemetry_slim.csv` — reduced state table for plotting/review
- `events.csv` — operator-marked mission timeline
- `alerts.csv` — boundary, altitude, GPS, battery, comms, and vibration awareness alerts

Vulcan-only logs:

- `lap_progress.csv`
- `delivery_events.csv`

Vivi-only logs:

- `cv_detections.csv`
- `target_reviews.csv`
- `Task_1_ValiantAerotech_targets.txt`

## Notes

- The example boundary coordinates are the CONOPS example only. Replace them with the actual Task 1 boundaries once released.
- The final target report must be reviewed by the operator. The script warns if a description appears to use GPS/numeric-coordinate wording, but it cannot guarantee compliance by itself.
- The lap counter is based on passing sequential waypoint gates within `lap_gate_radius_m`. Adjust the radius after testing with SITL or field data.

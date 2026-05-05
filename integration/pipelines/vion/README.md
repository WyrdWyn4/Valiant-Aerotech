# Vion Task 2 Photo Capture

## Quick Version

Vion saves proof photos for Task 2 extinguished targets.

Run it from the repo root:

```powershell
python .\integration\pipelines\vion\main.py
```

Press `ENTER` in the camera window to save a photo. Press `q` to quit.

Photos are saved as:

```text
Task_2_<team_name>_target_<target#>.jpg
```

## Details

### What The Tool Does

The script opens an OpenCV camera feed, shows the next target number, saves each confirmed frame as a JPEG, and records the capture in a CSV log.

The ConOps requires proof photos for extinguished targets. For autonomy scoring, image capture and upload need to be autonomous and real-time. This script is currently a manual capture tool.

### Outputs

Default output folder:

```text
task2_photos/
```

Default log file:

```text
task2_photos/task2_photo_log.csv
```

### Current Limitations

- Google Drive upload is not wired into this branch.
- Camera selection is fixed in code unless the script is edited.
- If the camera cannot open, the current script exits with an error.

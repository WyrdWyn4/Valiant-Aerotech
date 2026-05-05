# Valiant Aerotech Codebase

## Summary

This repo holds the software used for the AEAC 2026 flight tasks.

The active competition code is mainly in:

- `integration/pipelines/vivi`: Task 1 target localization report
- `integration/pipelines/vion`: Task 2 extinguished-target photo capture
- `_tools`: field utilities, including Vivi camera-servo calibration
- `actuation`: ArduPilot and mission-planner support files
- `planning`: mission notes, templates, and research material

For field testing, start with the README inside the pipeline you are using.

## Current Field Priorities

1. Verify the Vivi telemetry stream before flight.
2. Re-check the camera servo calibration on the real transmitter/receiver pair.
3. Use Vivi to generate `Task_1_<team_name>_targets.txt`.
4. Use Vion to capture Task 2 proof photos.
5. Review every generated file before upload.

## Team

Valiant Aerotech is built by students across software, electrical, and mechanical systems.

### Executive

| <img src="./_media/_img/_people/Mohammed%20Awad.png" height="120"><br>Mohammed Awad<br>President |
|:---:|

### Leads

| <img src="./_media/_img/_people/Waleed%20Mannan%20Khan%20Sherwani.png" height="120"><br>Waleed Mannan Khan Sherwani<br>Software Team Lead | <img src="./_media/_img/_people/Mirza%20Taimur%20Ali%20Baig.jpg" height="120"><br>Mirza Taimur Ali Baig<br>Electrical Team Lead |
|:---:|:---:|

### Software Team

| <img src="./_media/_img/_people/Rohan%20Torul.png" height="120"><br>Rohan Torul<br>Senior Member | <img src="./_media/_img/_people/Devansh%20Dalal.jpg" height="120"><br>Devansh Dalal<br>Senior Member | <img src="./_media/_img/_people/Mohammad%20Rakin.jpg" height="120"><br>Mohammad Rakin Kibria<br>Senior Member |
|:---:|:---:|:---:|

## Details

### Task 1: Vivi Reconnaissance

Vivi builds a local 3D model of the fire building, marks targets using MAVLink pose data, and writes the required Task 1 text report.

The report must be landmark-relative, not raw GPS or coordinate triples. The ConOps only allows decimetre-level precision, so the code rounds reported distances to 0.1 m.

### Task 2: Vion Extinguishing

Vion is the support tool for saving photos of extinguished targets. The ConOps requires photos to be submitted to the team Google Drive folder with names like:

```text
Task_2_<team_name>_target_<target#>.jpg
```

### Repository Map

```text
_docs/                 project documentation
_media/                images and competition documents
_missions/             shared mission files
_tools/                utility scripts for field setup
actuation/             vehicle-side scripts and Mission Planner notes
integration/configs/   local configuration templates
integration/data/      input data captured or collected by tools
integration/exports/   generated outputs ready for review/upload
integration/pipelines/ runnable task pipelines
planning/              mission planning and research
```

### Notes For Future Work

- The YOLO detector adapter still needs to be connected to Vivi's `detect(frame, detector=...)` hook.
- Google Drive upload support is not present in this branch.
- Do not rely on the building GPS point as a wall, centre, or corner. The ConOps says it is only a locator for finding the building.

# Task One Target Localization Desktop App

Local Python desktop tool for Valiant Aerotech's AEAC Task One target-report workflow.

The app replaces telemetry-based target localization with a screenshot-based operator workflow:

1. Vivi produces a wall view in Google Meet.
2. The operator copies a screenshot to the clipboard or loads an image file.
3. The operator annotates wall geometry, optional door geometry, and target circles.
4. The app estimates target position on the wall, generates a CONOPS-style draft sentence, and allows editing.
5. Confirmed targets are stored in a session JSON file and rendered into:

```text
Task_1_Valiant_Aerotech_targets.txt
```

The text file is regenerated from the JSON session after every change, rather than blindly appended, so edits and target deletions remain consistent.

## Current implementation status

Implemented:

- Local PySide6 desktop application
- Clipboard screenshot paste
- Image-file import
- Multiple screenshot sessions
- Building length, width, height setup
- Explicit North/South face-span mapping control to avoid silently assuming whether length or width applies to those faces
- Per-screenshot manual face direction
- Per-screenshot wall width/height auto-fill with manual override
- Three calibration modes:
  - Full wall corners: draggable TL → TR → BR → BL handles
  - Partial wall boundary lines: top, right, bottom, left
  - Approximate single-edge partial-wall mode
- Door annotation:
  - Four draggable door corner handles
  - Door left edge line
  - Door right edge line
- Target circles drawn on the screenshot, then draggable for refinement
- Wall-target calculations with confidence labels
- Automatic draft recalculation when wall/door corner handles or the draft target circle are moved
- Door-relative description generation when a door reference is available
- “Directly above the door” wording plus warning when applicable
- Structured manual ground/off-wall target workflow
- Live final report preview
- Session JSON persistence
- Target text revision and deletion after confirmation

Deliberately not implemented in this first pass:

- Direct browser/screen capture from Google Meet without using the clipboard
- Automatic colour detection
- Automatic off-wall / ground target geometry from image perspective
- Packaged `.exe` build

## Calibration modes

### 1. Full wall corners

Preferred mode. Press **Place Wall Corner Handles**, then drag the four handles onto the visible wall corners:

1. Top-left
2. Top-right
3. Bottom-right
4. Bottom-left

The older click-sequence tool is still available, but the intended operator workflow is now direct manipulation with draggable handles. The app computes a projective wall mapping from the image plane to metres on the wall face and automatically refreshes the draft target metrics when those handles move.

### 2. Partial wall boundary lines

Use this when the screenshot is cropped but the wall's boundary lines are still visible or inferable.

Draw:

- top wall boundary line
- right wall boundary line
- bottom wall boundary line
- left wall boundary line

The app extends the lines to infer the four wall corners, then applies the same projective mapping as full-corner mode.

### 3. Approximate single-edge partial wall

Use this only when a stronger calibration cannot be marked.

Draw one full-height reference wall edge and specify whether it is the screenshot-left or screenshot-right wall edge. The app:

- uses the wall height to infer local metres-per-pixel scale,
- estimates target height above ground,
- approximates horizontal distance from the marked edge using the same local scale.

This mode is intentionally labelled low confidence because it does **not** correct full projective distortion.

## Report generation logic

Wall targets produce sentences in the style of:

```text
On the north face of the building, approximately 2.4 m above ground and 0.8 m left of the door when facing it from outside. The colour is red.
```

If a door is not marked, the app falls back to a cardinal-side wall reference, such as:

```text
On the north face of the building, approximately 2.4 m above ground and 1.6 m from the western wall. The colour is red.
```

If a target is horizontally aligned with the marked door span, the app uses:

```text
... directly above the door when facing it from outside.
```

and raises a warning so the operator reviews the wording before confirming.

Distances are rounded to one decimal place.

## Running the app

### Windows quick start

```powershell
cd task_one_target_localizer_desktop
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

Or, after dependencies are installed, double-click:

```text
run_app.bat
```

## Suggested operational sequence at competition

1. Open the app before the flight window and enter the building dimensions.
2. Set whether North/South face width comes from the building length or width.
3. When Vivi has a useful wall view in Google Meet, copy a screenshot to the clipboard.
4. Paste it into the app.
5. Select the wall face direction manually.
6. Calibrate the wall using the strongest available mode.
7. Mark a door if visible and relevant; **Place Door Corner Handles** gives a draggable four-corner door set.
8. Draw a target circle, drag it if needed, and let the app recalculate the draft automatically.
9. Edit/confirm each generated description.
10. Review the live final `.txt` preview before upload.

## Output files

Default workspace folder:

```text
workspace/
```

Expected outputs:

```text
workspace/task_one_target_localizer_session.json
workspace/Task_1_Valiant_Aerotech_targets.txt
workspace/screenshots/*.png
```

## Notes on face-span mapping

The app does not blindly assume whether the provided building `length` or `width` is the span of a North/South wall. The setup panel contains:

```text
North/South face span uses: length | width
```

This selection determines the default wall-face width filled into each screenshot session. The operator can still override the per-screenshot wall width manually.

## Known operator-review conditions

Review warnings appear when:

- approximate single-edge mapping is used,
- a mapped target falls outside the calibrated wall span,
- a mapped target falls below ground or above the entered wall height,
- a target circle centre lies outside the calibrated projective wall quadrilateral,
- only a partial door reference is marked and a door-relative sentence cannot be safely inferred,
- the app chooses “directly above the door” wording.

These warnings are stored in the session JSON and shown in the app. They are not automatically inserted into the final competition `.txt` report.

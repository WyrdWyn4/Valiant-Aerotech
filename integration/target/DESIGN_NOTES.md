# Design Notes: Task One Screenshot-Based Target Localizer

## Why the implementation moves away from telemetry-based localization

The previous Task One approach attempted to infer wall-target locations from drone pose/telemetry. That is vulnerable to:

- GPS/local-position error at short wall-scale distances,
- uncertain camera pose and pitch/yaw under manual flight,
- camera offset assumptions,
- ray-wall intersection failures,
- high operational review burden when fallback projections are used.

The revised implementation treats the camera screenshot itself as the primary localization artifact. Known wall dimensions provide the metric scale, and the operator provides stable landmark correspondences through manual annotation.

## Geometry architecture

The code deliberately separates three localization tiers.

### Tier 1: Projective mapping from four wall corners

Used when the full wall corners are visible. The app solves a 3×3 homography mapping image coordinates onto a wall rectangle expressed in metres.

This is the primary and most defensible calculation mode.

### Tier 2: Projective mapping from partial boundary lines

Used when a screenshot is cropped but the top, bottom, left, and right wall boundaries can be marked. The intersections of the extended lines infer the missing corners, then the same homography method is applied.

This is still a projective mapping, but it can be more sensitive to operator line placement when inferred corners lie far outside the screenshot.

### Tier 3: Approximate single-edge mapping

This exists because the requested operator workflow explicitly allows one-edge/two-edge partial screenshots. In this mode:

- a full-height vertical wall edge is marked,
- the real wall height establishes a local image scale,
- target height is measured along that edge direction,
- horizontal displacement is estimated from the marked edge using the same local scale.

This is not equivalent to a homography. It assumes local apparent scale is sufficiently representative. The app therefore labels this mode low confidence and displays warnings before the target is confirmed.

## Report language architecture

The final `.txt` report is regenerated from structured target records. Each target record stores:

- target number,
- colour,
- final edited sentence,
- generated draft sentence,
- confidence label,
- warnings,
- screenshot linkage where applicable,
- raw circle annotation,
- computed wall-space values for wall targets.

This supports:

- safe revisions after confirmation,
- deletion without numbering drift,
- auditability during pre-upload review.

## Door-relative wording

When a door reference is available, the app prefers door-relative output.

The implementation supports:

- full four-corner door spans,
- paired left/right door edges,
- single partial edge with a warning when the side relationship is ambiguous.

If the target x-position falls within the mapped door horizontal span, the app drafts “directly above the door” and warns the operator to review the wording.

## Confidence labels

The current implementation uses:

- `High`: strong projective mapping with no major geometry warning,
- `Medium`: projective mapping that produced a geometry/review warning,
- `Low`: approximate single-edge mapping,
- `Manual`: structured ground/off-wall descriptions entered by the operator.

Confidence labels stay in the desktop app and JSON session. They are not written into the competition `.txt` report.

## Intentional non-goals of the first implementation

The first version does not attempt to solve:

- screen-capture permissions or direct browser-tab capture,
- off-wall 3D reconstruction,
- ground-target image geometry,
- target colour classification,
- fully automated target detection.

These are intentionally excluded so the first field-usable desktop version remains reviewable and operationally reliable.

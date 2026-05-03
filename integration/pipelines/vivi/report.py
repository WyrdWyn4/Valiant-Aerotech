"""Task One target-report writer."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from .detection import TargetEvent
from .localization import LocalizedTarget, TargetLocalizer
from .model import BuildingModel
from .pose import CameraConfig


def _default_logs_dir() -> Path:
    """Return the project-level logs directory.

    report.py is located at:

        Valiant-Aerotech/integration/pipelines/vivi/report.py

    Therefore:
        parents[0] = vivi
        parents[1] = pipelines
        parents[2] = integration
        parents[3] = Valiant-Aerotech

    The report should be written to:

        Valiant-Aerotech/logs
    """
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "logs"


def parse(
    events: Sequence[TargetEvent],
    model: BuildingModel,
    team_name: str,
    *,
    output_dir: str | Path | None = None,
    camera: Optional[CameraConfig] = None,
    include_debug_comments: bool = True,
) -> Path:
    """Generate the required Task One target .txt file.

    Important design choices:
    - The final text contains landmark-relative descriptions.
    - The final text does not contain raw GPS coordinates or internal [x,y,z]
      coordinates.
    - Optional warnings are included as comments only so the team can decide if
      manual review is needed before upload.

    If output_dir is not provided, the report is written to the project-level
    logs folder:

        Valiant-Aerotech/logs
    """
    if not team_name.strip():
        raise ValueError("team_name cannot be empty.")

    safe_team_name = "".join(
        ch if ch.isalnum() or ch in "_-" else "_"
        for ch in team_name.strip()
    )

    if output_dir is None:
        output_dir_path = _default_logs_dir()
    else:
        output_dir_path = Path(output_dir)

    output_dir_path.mkdir(parents=True, exist_ok=True)

    output_path = output_dir_path / f"Task_1_{safe_team_name}_targets.txt"

    localizer = TargetLocalizer(model, camera=camera)

    localized: List[LocalizedTarget] = []
    for i, event in enumerate(events, start=1):
        localized.append(localizer.localize_event(event, target_id=i))

    lines: List[str] = []
    lines.append(f"Task 1 Target Localization Report - {team_name}")
    lines.append("")

    if not localized:
        lines.append("No targets were confirmed.")
    else:
        for target in localized:
            lines.append(f"Target {target.target_id}:")
            lines.append(f"Colour: {target.colour}")
            lines.append(f"Location: {target.location_text}")

            # Useful during test flights. Before official upload, run with
            # include_debug_comments=False or remove any warning lines after review.
            if include_debug_comments and target.warnings:
                for warning in target.warnings:
                    lines.append(f"# REVIEW: {warning}")

            lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path
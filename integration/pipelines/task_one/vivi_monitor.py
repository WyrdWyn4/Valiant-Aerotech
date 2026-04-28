"""
Vivi read-only Task 1 monitor.

Vivi role in Task 1:
- Ride on Vulcan until arrival at the fire scene.
- Launch from Vulcan after the operator confirms the safe separation sequence.
- Run target detection using a separate computer-vision package.
- Convert detections into operator-reviewed, landmark-based target descriptions.
- Return and land.

This script DOES NOT control any flight operation. It only receives telemetry,
logs MAVLink, tails optional CV detection output, and generates a draft target
report from reviewed target descriptions.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "configs" / "vivi_config.json"
DEFAULT_CV_DETECTIONS = ROOT / "cv_detections.jsonl"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.base_monitor import ReadOnlyMavlinkMonitor
from common.logging_utils import CsvAppendLogger, json_dumps
from common.mavlink_state import utc_now


DETECTION_FIELDS = [
    "utc_iso",
    "elapsed_s",
    "vehicle",
    "target_id",
    "colour",
    "confidence",
    "source",
    "frame_ref",
    "image_ref",
    "operator_description",
    "raw_detection_json",
    "lat",
    "lon",
    "rel_alt_m",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
]

TARGET_REVIEW_FIELDS = [
    "utc_iso",
    "elapsed_s",
    "vehicle",
    "target_id",
    "colour",
    "description",
    "status",
]


class JsonlTailer:
    """Very small JSONL tailer for CV package output."""

    def __init__(self, path: Optional[str]) -> None:
        self.path = Path(path) if path else None
        self._fh = None
        self._position = 0

    def read_new(self) -> List[Dict[str, Any]]:
        if self.path is None:
            return []
        if not self.path.exists():
            return []
        if self._fh is None:
            self._fh = self.path.open("r", encoding="utf-8")
            self._fh.seek(0, 2)  # Start at end; only ingest new detections during this run.
            self._position = self._fh.tell()
        detections: List[Dict[str, Any]] = []
        while True:
            line = self._fh.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                detections.append(json.loads(line))
            except json.JSONDecodeError as exc:
                detections.append({"parse_error": str(exc), "raw_line": line})
        return detections


class ViviMonitor(ReadOnlyMavlinkMonitor):
    def __init__(self, config_path: str, connect_override: Optional[str] = None) -> None:
        super().__init__(config_path, connect_override)

        # Hardcoded/default CV input path. If config contains cv_detection_jsonl,
        # relative paths are resolved from this task_one folder.
        cv_file = self.cfg.get("cv_detection_jsonl")
        if cv_file:
            cv_path = Path(str(cv_file))
            self.cv_file = str(cv_path if cv_path.is_absolute() else ROOT / cv_path)
        else:
            self.cv_file = str(DEFAULT_CV_DETECTIONS)
        self.cv_tailer = JsonlTailer(self.cv_file)
        self.detection_logger = CsvAppendLogger(self.run_dir / "cv_detections.csv", DETECTION_FIELDS)
        self.target_review_logger = CsvAppendLogger(self.run_dir / "target_reviews.csv", TARGET_REVIEW_FIELDS)
        self.targets: Dict[str, Dict[str, str]] = {}
        self.team_name = str(self.cfg.get("team_name", "ValiantAerotech"))
        self.report_filename = f"Task_1_{self.team_name}_targets.txt"

    def on_periodic(self, now: float) -> None:
        for detection in self.cv_tailer.read_new():
            self.handle_cv_detection(detection)

    def handle_cv_detection(self, detection: Dict[str, Any]) -> None:
        # Accepted CV JSONL example:
        # {"target_id":"T01","colour":"red","confidence":0.87,
        #  "frame_ref":"frame_00123.jpg", "image_ref":"target_01.jpg",
        #  "operator_description":"On the east face ..."}
        target_id = str(detection.get("target_id") or detection.get("id") or f"auto_{int(time.time())}")
        colour = str(detection.get("colour") or detection.get("color") or "unknown")
        confidence = detection.get("confidence", "")
        description = str(detection.get("operator_description") or detection.get("description") or "")

        row = {
            "utc_iso": utc_now().isoformat(),
            "elapsed_s": round(self.elapsed_s(), 3),
            "vehicle": self.vehicle_name,
            "target_id": target_id,
            "colour": colour,
            "confidence": confidence,
            "source": "cv_jsonl",
            "frame_ref": detection.get("frame_ref", ""),
            "image_ref": detection.get("image_ref", ""),
            "operator_description": description,
            "raw_detection_json": json_dumps(detection),
            "lat": self.state.lat,
            "lon": self.state.lon,
            "rel_alt_m": self.state.rel_alt_m,
            "roll_deg": self.state.roll_deg,
            "pitch_deg": self.state.pitch_deg,
            "yaw_deg": self.state.yaw_deg,
        }
        self.detection_logger.write(row)
        self.log_event("target_detected", f"target_id={target_id}, colour={colour}, confidence={confidence}")

        if description:
            self.targets[target_id] = {"colour": colour, "description": description, "status": "cv_supplied"}
            self._log_target_review(target_id, colour, description, "cv_supplied")

    def process_vehicle_command(self, cmd: str, rest: str) -> bool:
        if cmd == "phase":
            self.log_event("phase_change", rest)
            return True

        if cmd == "launched":
            self.log_event("vivi_launched", rest)
            return True

        if cmd == "clear":
            self.log_event("vivi_clear_of_vulcan", rest)
            return True

        if cmd == "detect":
            # Manual detection note if CV integration is unavailable:
            # detect T01 red 0.85 frame_0123
            self._manual_detection(rest)
            return True

        if cmd == "target":
            # target T01 red On the east face, 1.2 m above ground...
            self._target_review(rest)
            return True

        if cmd == "report":
            self.write_target_report()
            return True

        return False

    def _manual_detection(self, rest: str) -> None:
        parts = rest.split(maxsplit=3)
        if len(parts) < 2:
            print("Usage: detect <target_id> <colour> [confidence] [frame/image ref]")
            return
        target_id = parts[0]
        colour = parts[1]
        confidence = parts[2] if len(parts) >= 3 else ""
        frame_ref = parts[3] if len(parts) >= 4 else ""
        detection = {
            "target_id": target_id,
            "colour": colour,
            "confidence": confidence,
            "frame_ref": frame_ref,
            "source": "manual_command",
        }
        row = {
            "utc_iso": utc_now().isoformat(),
            "elapsed_s": round(self.elapsed_s(), 3),
            "vehicle": self.vehicle_name,
            "target_id": target_id,
            "colour": colour,
            "confidence": confidence,
            "source": "manual_command",
            "frame_ref": frame_ref,
            "image_ref": "",
            "operator_description": "",
            "raw_detection_json": json_dumps(detection),
            "lat": self.state.lat,
            "lon": self.state.lon,
            "rel_alt_m": self.state.rel_alt_m,
            "roll_deg": self.state.roll_deg,
            "pitch_deg": self.state.pitch_deg,
            "yaw_deg": self.state.yaw_deg,
        }
        self.detection_logger.write(row)
        self.log_event("target_detected_manual", f"target_id={target_id}, colour={colour}, confidence={confidence}")

    def _target_review(self, rest: str) -> None:
        parts = rest.split(maxsplit=2)
        if len(parts) < 3:
            print("Usage: target <target_id> <colour> <landmark-based description>")
            return
        target_id, colour, description = parts
        if self._looks_like_forbidden_numeric_coordinate(description):
            print("WARNING: Description appears to contain GPS/numeric-coordinate style text. Rewrite using landmarks.")
            self.alert("WARNING", "target_description_may_violate_rules", f"target_id={target_id}")
        self.targets[target_id] = {"colour": colour, "description": description, "status": "operator_reviewed"}
        self._log_target_review(target_id, colour, description, "operator_reviewed")
        self.log_event("target_description_confirmed", f"target_id={target_id}, colour={colour}")

    def _log_target_review(self, target_id: str, colour: str, description: str, status: str) -> None:
        self.target_review_logger.write(
            {
                "utc_iso": utc_now().isoformat(),
                "elapsed_s": round(self.elapsed_s(), 3),
                "vehicle": self.vehicle_name,
                "target_id": target_id,
                "colour": colour,
                "description": description,
                "status": status,
            }
        )

    def write_target_report(self) -> None:
        path = self.run_dir / self.report_filename
        lines: List[str] = []
        lines.append(f"Task 1 Target Report - {self.team_name}")
        lines.append("Generated by Vivi read-only monitor")
        lines.append("Location descriptions are operator-reviewed and landmark-based.")
        lines.append("")
        if not self.targets:
            lines.append("No operator-reviewed targets recorded yet.")
        else:
            for idx, target_id in enumerate(sorted(self.targets.keys()), start=1):
                target = self.targets[target_id]
                lines.append(f"Target {idx} ({target_id}):")
                lines.append(f"Colour: {target['colour']}")
                lines.append(f"Location: {target['description']}")
                lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        self.log_event("target_file_generated", f"path={path}")
        print(f"[{self.vehicle_name}] Draft target report written: {path}")

    @staticmethod
    def _looks_like_forbidden_numeric_coordinate(description: str) -> bool:
        lowered = description.lower()
        bad_tokens = ["gps", "latitude", "longitude", " lat ", " lon ", "utm", "coordinate", "origin", "["]
        return any(token in lowered for token in bad_tokens)

    def print_help(self) -> None:
        super().print_help()
        print(
            "Vivi logging commands:\n"
            "  phase mounted|launched|search|return|landed [notes]\n"
            "  launched [notes]                 Mark Vivi launch from Vulcan\n"
            "  clear [notes]                    Mark safe separation from Vulcan\n"
            "  detect <id> <colour> [conf] [frame/image ref]\n"
            "  target <id> <colour> <landmark-based 3D description>\n"
            "  report                           Generate Task_1_<team>_targets.txt draft\n"
            "\nCV JSONL input format, one JSON object per line:\n"
            "  {\"target_id\":\"T01\",\"colour\":\"red\",\"confidence\":0.87,\n"
            "   \"frame_ref\":\"frame_0123.jpg\",\"operator_description\":\"On the east face...\"}\n"
        )

    def close_logs(self) -> None:
        self.write_target_report()
        self.detection_logger.close()
        self.target_review_logger.close()
        super().close_logs()


def main() -> None:
    parser = ReadOnlyMavlinkMonitor.build_arg_parser("Vivi read-only Task 1 monitor")
    args = parser.parse_args()

    # Hardcoded default config path. You can still override it with --config if needed.
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG
    if not config_path.exists():
        raise SystemExit(f"Missing Vivi config file: {config_path}")

    monitor = ViviMonitor(str(config_path), args.connect)
    monitor.run()


if __name__ == "__main__":
    main()

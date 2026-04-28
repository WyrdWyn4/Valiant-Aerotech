"""CSV and text logging helpers for read-only mission monitoring."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional


class CsvAppendLogger:
    def __init__(self, path: Path, fieldnames: Iterable[str]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fieldnames = list(fieldnames)
        file_exists = self.path.exists() and self.path.stat().st_size > 0
        self._fh = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=self.fieldnames, extrasaction="ignore")
        if not file_exists:
            self._writer.writeheader()
            self._fh.flush()

    def write(self, row: Dict[str, object]) -> None:
        self._writer.writerow(row)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def make_run_dir(base_dir: str, vehicle_name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    run_dir = Path(base_dir) / f"{vehicle_name}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


MAVLINK_LOG_FIELDS = [
    "utc_iso",
    "elapsed_s",
    "vehicle",
    "source_system",
    "source_component",
    "msg_type",
    "fields_json",
    "raw_repr",
]

SLIM_TELEMETRY_FIELDS = [
    "utc_iso",
    "elapsed_s",
    "vehicle",
    "last_message_type",
    "lat",
    "lon",
    "alt_msl_m",
    "rel_alt_m",
    "hdg_deg",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
    "airspeed_mps",
    "groundspeed_mps",
    "climb_mps",
    "throttle_pct",
    "gps_fix_type",
    "satellites_visible",
    "gps_h_acc_m",
    "battery_voltage_v",
    "battery_current_a",
    "battery_remaining_pct",
    "current_consumed_mah",
    "armed",
    "custom_mode",
    "system_status",
    "errors_comm",
    "drop_rate_comm",
    "ekf_flags",
    "vibration_x",
    "vibration_y",
    "vibration_z",
    "clipping_0",
    "clipping_1",
    "clipping_2",
    "wp_dist_m",
    "alt_error_m",
    "xtrack_error_m",
    "mission_seq",
    "mission_total",
]

EVENT_FIELDS = [
    "utc_iso",
    "elapsed_s",
    "vehicle",
    "event",
    "details",
    "lat",
    "lon",
    "rel_alt_m",
    "battery_remaining_pct",
    "gps_fix_type",
]

ALERT_FIELDS = [
    "utc_iso",
    "elapsed_s",
    "vehicle",
    "severity",
    "alert",
    "details",
    "lat",
    "lon",
    "rel_alt_m",
]

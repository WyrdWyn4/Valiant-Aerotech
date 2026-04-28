"""
Base read-only MAVLink monitor.

Important safety property:
- This monitor never sends MAVLink commands.
- It never arms, changes mode, uploads missions, moves servos, overrides RC,
  commands payload release, or controls flight.
- It only receives MAVLink messages, logs them, computes derived state, and prints alerts.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Set dialect before importing pymavlink. This helps decode ArduPilot-specific messages.
os.environ.setdefault("MAVLINK_DIALECT", "ardupilotmega")

from pymavlink import mavutil  # type: ignore

from .command_input import CommandInput
from .config import get_float, get_int, load_config, points_from_config
from .geometry import GeoPoint, distance_to_polygon_edge_m, point_in_polygon
from .logging_utils import (
    ALERT_FIELDS,
    EVENT_FIELDS,
    MAVLINK_LOG_FIELDS,
    SLIM_TELEMETRY_FIELDS,
    CsvAppendLogger,
    json_dumps,
    make_run_dir,
)
from .mavlink_state import VehicleState, msg_to_plain_dict, utc_now


class ReadOnlyMavlinkMonitor:
    """Common monitor for Vulcan and Vivi."""

    def __init__(self, config_path: str, connect_override: Optional[str] = None) -> None:
        self.config_path = config_path
        self.cfg = load_config(config_path)
        self.vehicle_name = str(self.cfg.get("vehicle_name", "vehicle"))
        self.connect_string = connect_override or str(self.cfg.get("mavlink_connection", "udpin:127.0.0.1:14550"))
        self.output_base_dir = str(self.cfg.get("output_dir", "logs"))
        self.run_dir = make_run_dir(self.output_base_dir, self.vehicle_name)

        self.state = VehicleState(vehicle_name=self.vehicle_name)
        self.command_input = CommandInput()
        self.start_monotonic = time.monotonic()
        self.last_slim_log = 0.0
        self.last_status_print = 0.0
        self.last_alert_times: Dict[str, float] = {}
        self.quit_requested = False

        self.slim_log_hz = get_float(self.cfg, "slim_log_hz", 2.0)
        self.status_print_hz = get_float(self.cfg, "status_print_hz", 1.0)
        self.alert_repeat_s = get_float(self.cfg, "alert_repeat_s", 5.0)
        self.altitude_limit_m = get_float(self.cfg, "altitude_limit_m", 120.0)
        self.altitude_warn_margin_m = get_float(self.cfg, "altitude_warn_margin_m", 5.0)
        self.min_gps_fix_type = get_int(self.cfg, "min_gps_fix_type", 3)
        self.low_battery_warn_pct = get_float(self.cfg, "low_battery_warn_pct", 25.0)
        self.low_battery_critical_pct = get_float(self.cfg, "low_battery_critical_pct", 15.0)

        self.soft_boundary = points_from_config(self.cfg.get("soft_boundary"))
        self.hard_boundary = points_from_config(self.cfg.get("hard_boundary"))

        self.raw_logger = CsvAppendLogger(self.run_dir / "mavlink_messages.csv", MAVLINK_LOG_FIELDS)
        self.slim_logger = CsvAppendLogger(self.run_dir / "telemetry_slim.csv", SLIM_TELEMETRY_FIELDS)
        self.event_logger = CsvAppendLogger(self.run_dir / "events.csv", EVENT_FIELDS)
        self.alert_logger = CsvAppendLogger(self.run_dir / "alerts.csv", ALERT_FIELDS)

    @staticmethod
    def build_arg_parser(description: str) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=description)
        parser.add_argument("--config", default=None, help="Path to JSON mission/vehicle config. If omitted, the monitor uses its hardcoded default config path.")
        parser.add_argument("--connect", default=None, help="Override MAVLink connection string.")
        return parser

    def elapsed_s(self) -> float:
        return time.monotonic() - self.start_monotonic

    def connect(self) -> Any:
        print(f"[{self.vehicle_name}] Read-only MAVLink monitor starting")
        print(f"[{self.vehicle_name}] Config: {self.config_path}")
        print(f"[{self.vehicle_name}] Connect: {self.connect_string}")
        print(f"[{self.vehicle_name}] Output: {self.run_dir}")
        print(f"[{self.vehicle_name}] Waiting for heartbeat...")
        master = mavutil.mavlink_connection(self.connect_string)
        master.wait_heartbeat()
        print(
            f"[{self.vehicle_name}] Connected: system={master.target_system}, "
            f"component={master.target_component}"
        )
        self.log_event("monitor_connected", f"connect={self.connect_string}")
        return master

    def run(self) -> None:
        master = self.connect()
        self.print_help()
        try:
            while not self.quit_requested:
                msg = master.recv_match(blocking=True, timeout=0.5)
                now = time.monotonic()
                if msg is not None:
                    self.handle_msg(msg, now)
                self.handle_commands()
                self.periodic(now)
        except KeyboardInterrupt:
            print(f"\n[{self.vehicle_name}] Stopped by keyboard interrupt")
            self.log_event("monitor_stopped", "KeyboardInterrupt")
        finally:
            self.close_logs()

    def handle_msg(self, msg: Any, now: float) -> None:
        msg_type = msg.get_type()
        if msg_type == "BAD_DATA":
            return
        self.state.update_from_msg(msg, wall_time=now)

        now_utc = utc_now()
        self.raw_logger.write(
            {
                "utc_iso": now_utc.isoformat(),
                "elapsed_s": round(self.elapsed_s(), 3),
                "vehicle": self.vehicle_name,
                "source_system": self.state.source_system,
                "source_component": self.state.source_component,
                "msg_type": msg_type,
                "fields_json": json_dumps(msg_to_plain_dict(msg)),
                "raw_repr": repr(msg),
            }
        )
        self.on_message(msg, now)

    def on_message(self, msg: Any, now: float) -> None:
        """Subclass hook."""
        return

    def periodic(self, now: float) -> None:
        elapsed = self.elapsed_s()
        if elapsed - self.last_slim_log >= 1.0 / max(self.slim_log_hz, 0.1):
            self.last_slim_log = elapsed
            self.slim_logger.write(self.state.slim_row(utc_now(), elapsed))

        if elapsed - self.last_status_print >= 1.0 / max(self.status_print_hz, 0.1):
            self.last_status_print = elapsed
            self.print_status_line()

        self.check_safety_awareness()
        self.on_periodic(now)

    def on_periodic(self, now: float) -> None:
        """Subclass hook."""
        return

    def check_safety_awareness(self) -> None:
        position = self.state.position
        rel_alt = self.state.rel_alt_m

        if position is not None:
            if self.soft_boundary and not point_in_polygon(position, self.soft_boundary):
                dist = distance_to_polygon_edge_m(position, self.soft_boundary)
                self.alert("WARNING", "outside_soft_boundary", f"distance_to_edge_m={dist}")
            if self.hard_boundary and not point_in_polygon(position, self.hard_boundary):
                dist = distance_to_polygon_edge_m(position, self.hard_boundary)
                self.alert("CRITICAL", "outside_hard_boundary", f"distance_to_edge_m={dist}")

        if rel_alt is not None:
            if rel_alt > self.altitude_limit_m:
                self.alert("CRITICAL", "above_altitude_limit", f"rel_alt_m={rel_alt:.1f}, limit_m={self.altitude_limit_m:.1f}")
            elif rel_alt > self.altitude_limit_m - self.altitude_warn_margin_m:
                self.alert("WARNING", "near_altitude_limit", f"rel_alt_m={rel_alt:.1f}, limit_m={self.altitude_limit_m:.1f}")

        if self.state.gps_fix_type is not None and self.state.gps_fix_type < self.min_gps_fix_type:
            self.alert("WARNING", "gps_fix_below_minimum", f"fix_type={self.state.gps_fix_type}, min={self.min_gps_fix_type}")

        if self.state.battery_remaining_pct is not None:
            pct = self.state.battery_remaining_pct
            if pct <= self.low_battery_critical_pct:
                self.alert("CRITICAL", "battery_critical", f"battery_remaining_pct={pct:.1f}")
            elif pct <= self.low_battery_warn_pct:
                self.alert("WARNING", "battery_low", f"battery_remaining_pct={pct:.1f}")

        if self.state.errors_comm not in (None, 0):
            self.alert("WARNING", "communication_errors", f"errors_comm={self.state.errors_comm}")

        if any(c not in (None, 0) for c in [self.state.clipping_0, self.state.clipping_1, self.state.clipping_2]):
            self.alert(
                "WARNING",
                "imu_clipping_detected",
                f"clipping=({self.state.clipping_0},{self.state.clipping_1},{self.state.clipping_2})",
            )

    def alert(self, severity: str, alert_name: str, details: str) -> None:
        elapsed = self.elapsed_s()
        last = self.last_alert_times.get(alert_name, -1e9)
        if elapsed - last < self.alert_repeat_s:
            return
        self.last_alert_times[alert_name] = elapsed
        row = {
            "utc_iso": utc_now().isoformat(),
            "elapsed_s": round(elapsed, 3),
            "vehicle": self.vehicle_name,
            "severity": severity,
            "alert": alert_name,
            "details": details,
            "lat": self.state.lat,
            "lon": self.state.lon,
            "rel_alt_m": self.state.rel_alt_m,
        }
        self.alert_logger.write(row)
        print(f"[{self.vehicle_name}] {severity}: {alert_name} | {details}")

    def log_event(self, event: str, details: str = "") -> None:
        elapsed = self.elapsed_s()
        row = {
            "utc_iso": utc_now().isoformat(),
            "elapsed_s": round(elapsed, 3),
            "vehicle": self.vehicle_name,
            "event": event,
            "details": details,
            "lat": self.state.lat,
            "lon": self.state.lon,
            "rel_alt_m": self.state.rel_alt_m,
            "battery_remaining_pct": self.state.battery_remaining_pct,
            "gps_fix_type": self.state.gps_fix_type,
        }
        self.event_logger.write(row)
        print(f"[{self.vehicle_name}] EVENT: {event} | {details}")

    def handle_commands(self) -> None:
        while True:
            line = self.command_input.get_nowait()
            if line is None:
                break
            self.process_command(line)

    def process_command(self, line: str) -> None:
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if cmd in {"q", "quit", "exit"}:
            self.log_event("monitor_quit_requested", "operator command")
            self.quit_requested = True
        elif cmd in {"h", "help"}:
            self.print_help()
        elif cmd in {"event", "mark"}:
            if not rest:
                print("Usage: event <event_name> [details]")
                return
            evt_parts = rest.split(maxsplit=1)
            event_name = evt_parts[0]
            details = evt_parts[1] if len(evt_parts) > 1 else ""
            self.log_event(event_name, details)
        elif cmd == "status":
            self.print_status_line(force=True)
        else:
            handled = self.process_vehicle_command(cmd, rest)
            if not handled:
                print(f"Unknown command: {line}")
                self.print_help()

    def process_vehicle_command(self, cmd: str, rest: str) -> bool:
        """Subclass command hook. Return True if handled."""
        return False

    def print_help(self) -> None:
        print(
            f"\n[{self.vehicle_name}] Commands are for logging only. They do not control the aircraft.\n"
            "  event <name> [details]   Mark a mission event\n"
            "  status                   Print current state\n"
            "  help                     Show help\n"
            "  quit                     Stop this monitor\n"
        )

    def print_status_line(self, force: bool = False) -> None:
        lat = f"{self.state.lat:.7f}" if self.state.lat is not None else "None"
        lon = f"{self.state.lon:.7f}" if self.state.lon is not None else "None"
        alt = f"{self.state.rel_alt_m:.1f}m" if self.state.rel_alt_m is not None else "None"
        gs = f"{self.state.groundspeed_mps:.1f}m/s" if self.state.groundspeed_mps is not None else "None"
        batt = f"{self.state.battery_remaining_pct:.0f}%" if self.state.battery_remaining_pct is not None else "None"
        gps = self.state.gps_fix_type if self.state.gps_fix_type is not None else "None"
        print(
            f"[{self.vehicle_name}] t={self.elapsed_s():.1f}s "
            f"lat={lat} lon={lon} rel_alt={alt} gs={gs} batt={batt} gps_fix={gps}"
        )

    def close_logs(self) -> None:
        self.raw_logger.close()
        self.slim_logger.close()
        self.event_logger.close()
        self.alert_logger.close()

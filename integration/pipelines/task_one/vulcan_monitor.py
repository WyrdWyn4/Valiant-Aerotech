"""
Vulcan read-only Task 1 monitor.

Vulcan role in Task 1:
- Carry Vivi and all three equipment items.
- Complete outbound laps for distance scoring.
- Fly to the fire scene and staging pads.
- Deliver radio, oxygen tank, and ladder manually/operationally.
- Return and land.

This script DOES NOT control any flight operation. It only receives telemetry,
counts lap progress, logs operator-marked delivery events, and prints awareness
alerts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

# Allow running directly from this folder without installing a package.
ROOT = Path(__file__).resolve().parent
DEFAULT_CONNECT = "udpin:127.0.0.1:14550"
DEFAULT_CONFIG = ROOT / "configs" / "vulcan_config.json"

ROOT = Path(__file__).resolve().parent

from common.base_monitor import ReadOnlyMavlinkMonitor
from common.geometry import GeoPoint, haversine_m
from common.mavlink_state import utc_now

class VulcanMonitor(ReadOnlyMavlinkMonitor):
    def __init__(self, config_path: str, connect_override: Optional[str] = None) -> None:
        super().__init__(config_path, connect_override)
        self.lap_done_rc_channel = int(self.cfg.get("lap_done_rc_channel", 7))
        self.lap_done_pwm_threshold = int(self.cfg.get("lap_done_pwm_threshold", 1700))

        if not 1 <= self.lap_done_rc_channel <= 18:
            raise ValueError("lap_done_rc_channel must be between 1 and 18")

        self.laps_done_triggered = False
        self.last_lap_done_pwm = None
        self.fire_scene_center = None
        fire_scene = self.cfg.get("fire_scene") or {}
        if "lat" in fire_scene and "lon" in fire_scene:
            self.fire_scene_center = GeoPoint(float(fire_scene["lat"]), float(fire_scene["lon"]))
        self.fire_scene_radius_m = float(fire_scene.get("radius_m", 30.0)) if fire_scene else 30.0
        self.entered_fire_scene = False
        self.staging_pads = self.cfg.get("staging_pads") or []

    def on_message(self, msg: Any, now: float) -> None:
        msg_type = msg.get_type()

        # Read-only RC trigger for "laps done".
        # Mission Planner handles the actual lap waypoint mission.
        if msg_type == "RC_CHANNELS":
            self._check_laps_done_trigger(msg)

        # Fire-scene entry detection is still useful, so keep it.
        if msg_type == "GLOBAL_POSITION_INT":
            if self.fire_scene_center and self.state.position and not self.entered_fire_scene:
                dist = haversine_m(self.state.position, self.fire_scene_center)
                if dist <= self.fire_scene_radius_m:
                    self.entered_fire_scene = True
                    self.log_event("entered_fire_scene", f"distance_to_scene_center_m={dist:.1f}")

    def process_vehicle_command(self, cmd: str, rest: str) -> bool:
        if cmd == "phase":
            self.log_event("phase_change", rest)
            return True

        if cmd in {"attempt", "touch", "release", "confirm", "delivery"}:
            self._handle_delivery_command(cmd, rest)
            return True

        if cmd == "vivi":
            # Example: vivi stable_for_launch, vivi launched, vivi clear
            self.log_event(f"vivi_{rest.split()[0] if rest else 'event'}", rest)
            return True

        return False

    def _handle_delivery_command(self, cmd: str, rest: str) -> None:
        # Commands are operator event marks only:
        #   attempt radio A
        #   touch radio A
        #   release radio A
        #   confirm radio A
        parts = rest.split(maxsplit=2)
        payload = parts[0] if len(parts) >= 1 else "unspecified"
        pad = parts[1] if len(parts) >= 2 else "unspecified"
        details = parts[2] if len(parts) >= 3 else ""
        event_map = {
            "attempt": "delivery_attempt",
            "touch": "payload_touched_ground",
            "release": "payload_released",
            "confirm": "delivery_confirmed",
            "delivery": "delivery_note",
        }
        event = event_map.get(cmd, cmd)
        row = {
            "utc_iso": utc_now().isoformat(),
            "elapsed_s": round(self.elapsed_s(), 3),
            "vehicle": self.vehicle_name,
            "payload": payload,
            "pad": pad,
            "event": event,
            "details": details,
            "lat": self.state.lat,
            "lon": self.state.lon,
            "rel_alt_m": self.state.rel_alt_m,
        }
        self.delivery_logger.write(row)
        self.log_event(event, f"payload={payload}, pad={pad}, {details}".strip())

    def print_help(self) -> None:
        super().print_help()
        print(
            "Vulcan logging commands:\n"
            "  phase laps|transit|delivery|return|landed [notes]\n"
            "  RC lap trigger: flip configured RC switch/button to mark laps done\n"
            "  vivi stable_for_launch|launched|clear [notes]\n"
            "  attempt <radio|oxygen|ladder> <pad_id> [notes]\n"
            "  touch <radio|oxygen|ladder> <pad_id> [notes]\n"
            "  release <radio|oxygen|ladder> <pad_id> [notes]\n"
            "  confirm <radio|oxygen|ladder> <pad_id> [notes]\n"
            "  pads    Show nearest configured staging pad\n"
        )

    def print_status_line(self, force: bool = False) -> None:
        super().print_status_line(force=force)
        pwm_txt = self.last_lap_done_pwm if self.last_lap_done_pwm is not None else "None"
        print(
            f"[{self.vehicle_name}] lap_done_switch=RC{self.lap_done_rc_channel} "
            f"pwm={pwm_txt} triggered={self.laps_done_triggered}"
        )

    def close_logs(self) -> None:
        super().close_logs()

    def _check_laps_done_trigger(self, msg: Any) -> None:
        channel_field = f"chan{self.lap_done_rc_channel}_raw"
        pwm = getattr(msg, channel_field, None)

        if pwm in (None, 0):
            return

        self.last_lap_done_pwm = pwm

        if pwm >= self.lap_done_pwm_threshold and not self.laps_done_triggered:
            self.laps_done_triggered = True

            details = f"RC{self.lap_done_rc_channel}={pwm}, threshold={self.lap_done_pwm_threshold}"

            self.log_event("laps_done", details)
            self.log_event("phase_change", "transit_to_fire_scene after RC lap trigger")

            print(f"[{self.vehicle_name}] LAPS DONE: {details}")


def main() -> None:
    monitor = VulcanMonitor(str(DEFAULT_CONFIG), DEFAULT_CONNECT)
    monitor.run()


if __name__ == "__main__":
    main()

"""
Read-only MAVLink state extraction.

This module only converts received MAVLink messages into Python state and loggable
fields. It does not send MAVLink commands.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .geometry import GeoPoint


@dataclass
class VehicleState:
    vehicle_name: str
    first_wall_time: Optional[float] = None
    last_msg_time: Optional[float] = None

    # Vehicle identity / mode
    source_system: Optional[int] = None
    source_component: Optional[int] = None
    mav_type: Optional[int] = None
    autopilot: Optional[int] = None
    base_mode: Optional[int] = None
    custom_mode: Optional[int] = None
    system_status: Optional[int] = None
    armed: Optional[bool] = None

    # Position
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_msl_m: Optional[float] = None
    rel_alt_m: Optional[float] = None
    vx_mps: Optional[float] = None
    vy_mps: Optional[float] = None
    vz_mps: Optional[float] = None
    hdg_deg: Optional[float] = None

    # GPS
    gps_fix_type: Optional[int] = None
    satellites_visible: Optional[int] = None
    gps_vel_mps: Optional[float] = None
    gps_h_acc_m: Optional[float] = None
    gps_v_acc_m: Optional[float] = None

    # Attitude / HUD
    roll_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None
    rollspeed_dps: Optional[float] = None
    pitchspeed_dps: Optional[float] = None
    yawspeed_dps: Optional[float] = None
    airspeed_mps: Optional[float] = None
    groundspeed_mps: Optional[float] = None
    throttle_pct: Optional[float] = None
    climb_mps: Optional[float] = None

    # Power / health
    voltage_battery_v: Optional[float] = None
    current_battery_a: Optional[float] = None
    battery_remaining_pct: Optional[float] = None
    current_consumed_mah: Optional[float] = None
    drop_rate_comm: Optional[int] = None
    errors_comm: Optional[int] = None
    onboard_control_sensors_health: Optional[int] = None

    # Estimator / vibration
    ekf_flags: Optional[int] = None
    velocity_variance: Optional[float] = None
    pos_horiz_variance: Optional[float] = None
    pos_vert_variance: Optional[float] = None
    compass_variance: Optional[float] = None
    vibration_x: Optional[float] = None
    vibration_y: Optional[float] = None
    vibration_z: Optional[float] = None
    clipping_0: Optional[int] = None
    clipping_1: Optional[int] = None
    clipping_2: Optional[int] = None

    # Navigation / mission
    wp_dist_m: Optional[float] = None
    alt_error_m: Optional[float] = None
    aspd_error_mps: Optional[float] = None
    xtrack_error_m: Optional[float] = None
    mission_seq: Optional[int] = None
    mission_total: Optional[int] = None

    last_message_type: Optional[str] = None
    message_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def position(self) -> Optional[GeoPoint]:
        if self.lat is None or self.lon is None:
            return None
        return GeoPoint(self.lat, self.lon)

    def update_from_msg(self, msg: Any, wall_time: float) -> None:
        msg_type = msg.get_type()
        self.last_message_type = msg_type
        self.last_msg_time = wall_time
        if self.first_wall_time is None:
            self.first_wall_time = wall_time
        self.message_counts[msg_type] = self.message_counts.get(msg_type, 0) + 1

        try:
            self.source_system = msg.get_srcSystem()
            self.source_component = msg.get_srcComponent()
        except Exception:
            pass

        if msg_type == "HEARTBEAT":
            self.mav_type = getattr(msg, "type", None)
            self.autopilot = getattr(msg, "autopilot", None)
            self.base_mode = getattr(msg, "base_mode", None)
            self.custom_mode = getattr(msg, "custom_mode", None)
            self.system_status = getattr(msg, "system_status", None)
            # MAV_MODE_FLAG_SAFETY_ARMED = 128
            self.armed = bool((self.base_mode or 0) & 128)

        elif msg_type == "GLOBAL_POSITION_INT":
            self.lat = _scaled(getattr(msg, "lat", None), 1e7)
            self.lon = _scaled(getattr(msg, "lon", None), 1e7)
            self.alt_msl_m = _scaled(getattr(msg, "alt", None), 1000.0)
            self.rel_alt_m = _scaled(getattr(msg, "relative_alt", None), 1000.0)
            self.vx_mps = _scaled(getattr(msg, "vx", None), 100.0)
            self.vy_mps = _scaled(getattr(msg, "vy", None), 100.0)
            self.vz_mps = _scaled(getattr(msg, "vz", None), 100.0)
            hdg_cdeg = getattr(msg, "hdg", None)
            if hdg_cdeg is not None and hdg_cdeg != 65535:
                self.hdg_deg = hdg_cdeg / 100.0

        elif msg_type == "GPS_RAW_INT":
            self.gps_fix_type = getattr(msg, "fix_type", None)
            self.satellites_visible = getattr(msg, "satellites_visible", None)
            self.gps_vel_mps = _scaled(getattr(msg, "vel", None), 100.0)
            self.gps_h_acc_m = _scaled(getattr(msg, "h_acc", None), 1000.0)
            self.gps_v_acc_m = _scaled(getattr(msg, "v_acc", None), 1000.0)

        elif msg_type == "ATTITUDE":
            self.roll_deg = _rad_to_deg(getattr(msg, "roll", None))
            self.pitch_deg = _rad_to_deg(getattr(msg, "pitch", None))
            self.yaw_deg = _normalize_deg(_rad_to_deg(getattr(msg, "yaw", None)))
            self.rollspeed_dps = _rad_to_deg(getattr(msg, "rollspeed", None))
            self.pitchspeed_dps = _rad_to_deg(getattr(msg, "pitchspeed", None))
            self.yawspeed_dps = _rad_to_deg(getattr(msg, "yawspeed", None))

        elif msg_type == "VFR_HUD":
            self.airspeed_mps = _float_or_none(getattr(msg, "airspeed", None))
            self.groundspeed_mps = _float_or_none(getattr(msg, "groundspeed", None))
            self.hdg_deg = _float_or_none(getattr(msg, "heading", None))
            self.throttle_pct = _float_or_none(getattr(msg, "throttle", None))
            self.alt_msl_m = _float_or_none(getattr(msg, "alt", None))
            self.climb_mps = _float_or_none(getattr(msg, "climb", None))

        elif msg_type == "SYS_STATUS":
            self.voltage_battery_v = _scaled(getattr(msg, "voltage_battery", None), 1000.0)
            self.current_battery_a = _scaled(getattr(msg, "current_battery", None), 100.0)
            self.battery_remaining_pct = _float_or_none(getattr(msg, "battery_remaining", None))
            self.drop_rate_comm = getattr(msg, "drop_rate_comm", None)
            self.errors_comm = getattr(msg, "errors_comm", None)
            self.onboard_control_sensors_health = getattr(msg, "onboard_control_sensors_health", None)

        elif msg_type == "BATTERY_STATUS":
            current_battery = getattr(msg, "current_battery", None)
            if current_battery not in (None, -1):
                self.current_battery_a = current_battery / 100.0
            current_consumed = getattr(msg, "current_consumed", None)
            if current_consumed not in (None, -1):
                self.current_consumed_mah = float(current_consumed)
            battery_remaining = getattr(msg, "battery_remaining", None)
            if battery_remaining not in (None, -1):
                self.battery_remaining_pct = float(battery_remaining)
            voltages = getattr(msg, "voltages", None)
            if voltages and voltages[0] != 65535:
                self.voltage_battery_v = voltages[0] / 1000.0

        elif msg_type == "EKF_STATUS_REPORT":
            self.ekf_flags = getattr(msg, "flags", None)
            self.velocity_variance = _float_or_none(getattr(msg, "velocity_variance", None))
            self.pos_horiz_variance = _float_or_none(getattr(msg, "pos_horiz_variance", None))
            self.pos_vert_variance = _float_or_none(getattr(msg, "pos_vert_variance", None))
            self.compass_variance = _float_or_none(getattr(msg, "compass_variance", None))

        elif msg_type == "VIBRATION":
            self.vibration_x = _float_or_none(getattr(msg, "vibration_x", None))
            self.vibration_y = _float_or_none(getattr(msg, "vibration_y", None))
            self.vibration_z = _float_or_none(getattr(msg, "vibration_z", None))
            self.clipping_0 = getattr(msg, "clipping_0", None)
            self.clipping_1 = getattr(msg, "clipping_1", None)
            self.clipping_2 = getattr(msg, "clipping_2", None)

        elif msg_type == "NAV_CONTROLLER_OUTPUT":
            self.wp_dist_m = _float_or_none(getattr(msg, "wp_dist", None))
            self.alt_error_m = _float_or_none(getattr(msg, "alt_error", None))
            self.aspd_error_mps = _float_or_none(getattr(msg, "aspd_error", None))
            self.xtrack_error_m = _float_or_none(getattr(msg, "xtrack_error", None))

        elif msg_type == "MISSION_CURRENT":
            self.mission_seq = getattr(msg, "seq", None)
            self.mission_total = getattr(msg, "total", None)

    def slim_row(self, now_utc: datetime, elapsed_s: float) -> Dict[str, object]:
        return {
            "utc_iso": now_utc.isoformat(),
            "elapsed_s": round(elapsed_s, 3),
            "vehicle": self.vehicle_name,
            "last_message_type": self.last_message_type,
            "lat": self.lat,
            "lon": self.lon,
            "alt_msl_m": self.alt_msl_m,
            "rel_alt_m": self.rel_alt_m,
            "hdg_deg": self.hdg_deg,
            "roll_deg": self.roll_deg,
            "pitch_deg": self.pitch_deg,
            "yaw_deg": self.yaw_deg,
            "airspeed_mps": self.airspeed_mps,
            "groundspeed_mps": self.groundspeed_mps,
            "climb_mps": self.climb_mps,
            "throttle_pct": self.throttle_pct,
            "gps_fix_type": self.gps_fix_type,
            "satellites_visible": self.satellites_visible,
            "gps_h_acc_m": self.gps_h_acc_m,
            "battery_voltage_v": self.voltage_battery_v,
            "battery_current_a": self.current_battery_a,
            "battery_remaining_pct": self.battery_remaining_pct,
            "current_consumed_mah": self.current_consumed_mah,
            "armed": self.armed,
            "custom_mode": self.custom_mode,
            "system_status": self.system_status,
            "errors_comm": self.errors_comm,
            "drop_rate_comm": self.drop_rate_comm,
            "ekf_flags": self.ekf_flags,
            "vibration_x": self.vibration_x,
            "vibration_y": self.vibration_y,
            "vibration_z": self.vibration_z,
            "clipping_0": self.clipping_0,
            "clipping_1": self.clipping_1,
            "clipping_2": self.clipping_2,
            "wp_dist_m": self.wp_dist_m,
            "alt_error_m": self.alt_error_m,
            "xtrack_error_m": self.xtrack_error_m,
            "mission_seq": self.mission_seq,
            "mission_total": self.mission_total,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def msg_to_plain_dict(msg: Any) -> Dict[str, Any]:
    """Convert a MAVLink message to JSON-safe primitives where possible."""
    try:
        data = msg.to_dict()
    except Exception:
        data = {"repr": repr(msg)}
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if key == "mavpackettype":
            continue
        out[key] = _json_safe(value)
    return out


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return repr(value)


def _scaled(value: Any, scale: float) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value) / scale
    except Exception:
        return None


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _rad_to_deg(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return math.degrees(float(value))
    except Exception:
        return None


def _normalize_deg(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return (value + 360.0) % 360.0

from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Optional


@dataclass
class TelemetryState:
    history_limit: int

    lock: Lock = field(default_factory=Lock, init=False, repr=False)

    connected: bool = False
    system_id: Optional[int] = None
    component_id: Optional[int] = None
    last_message_time: Optional[float] = None
    last_error: Optional[str] = None

    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_m: Optional[float] = None

    roll_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None

    groundspeed_mps: Optional[float] = None
    battery_remaining: Optional[int] = None

    flight_mode: Optional[str] = None
    armed: Optional[bool] = None

    gps_fix_type: Optional[int] = None
    satellites_visible: Optional[int] = None

    message_counts: Counter = field(default_factory=Counter)
    latest_messages: dict[str, dict[str, Any]] = field(default_factory=dict)

    altitude_history: deque = field(init=False)
    speed_history: deque = field(init=False)

    rel_alt_m: Optional[float] = None
    msl_alt_m: Optional[float] = None

    def __post_init__(self) -> None:
        self.altitude_history = deque(maxlen=self.history_limit)
        self.speed_history = deque(maxlen=self.history_limit)

    def set_connected(self, system_id: int, component_id: int) -> None:
        with self.lock:
            self.connected = True
            self.system_id = system_id
            self.component_id = component_id
            self.last_error = None

    def set_disconnected(self, error: Optional[str] = None) -> None:
        with self.lock:
            self.connected = False
            if error:
                self.last_error = error

    def record_message(self, msg_type: str, payload: dict[str, Any], timestamp: float) -> None:
        with self.lock:
            self.last_message_time = timestamp
            self.message_counts[msg_type] += 1
            self.latest_messages[msg_type] = payload

    def update_position(
        self,
        timestamp: float,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        alt_m: Optional[float] = None,
        groundspeed_mps: Optional[float] = None,
    ) -> None:
        with self.lock:
            if lat is not None:
                self.lat = lat
            if lon is not None:
                self.lon = lon
            if alt_m is not None:
                self.alt_m = alt_m
                self.altitude_history.append({"time": timestamp, "alt_m": alt_m})
            if groundspeed_mps is not None:
                self.groundspeed_mps = groundspeed_mps
                self.speed_history.append({"time": timestamp, "groundspeed_mps": groundspeed_mps})

    def update_attitude(
        self,
        roll_deg: Optional[float] = None,
        pitch_deg: Optional[float] = None,
        yaw_deg: Optional[float] = None,
    ) -> None:
        with self.lock:
            if roll_deg is not None:
                self.roll_deg = roll_deg
            if pitch_deg is not None:
                self.pitch_deg = pitch_deg
            if yaw_deg is not None:
                self.yaw_deg = yaw_deg

    def update_status(
        self,
        battery_remaining: Optional[int] = None,
        flight_mode: Optional[str] = None,
        armed: Optional[bool] = None,
        gps_fix_type: Optional[int] = None,
        satellites_visible: Optional[int] = None,
    ) -> None:
        with self.lock:
            if battery_remaining is not None:
                self.battery_remaining = battery_remaining
            if flight_mode is not None:
                self.flight_mode = flight_mode
            if armed is not None:
                self.armed = armed
            if gps_fix_type is not None:
                self.gps_fix_type = gps_fix_type
            if satellites_visible is not None:
                self.satellites_visible = satellites_visible

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "connected": self.connected,
                "system_id": self.system_id,
                "component_id": self.component_id,
                "last_message_time": self.last_message_time,
                "last_error": self.last_error,
                "lat": self.lat,
                "lon": self.lon,
                "alt_m": self.alt_m,
                "roll_deg": self.roll_deg,
                "pitch_deg": self.pitch_deg,
                "yaw_deg": self.yaw_deg,
                "groundspeed_mps": self.groundspeed_mps,
                "battery_remaining": self.battery_remaining,
                "flight_mode": self.flight_mode,
                "armed": self.armed,
                "gps_fix_type": self.gps_fix_type,
                "satellites_visible": self.satellites_visible,
                "message_counts": dict(self.message_counts),
                "latest_messages": deepcopy(self.latest_messages),
                "altitude_history": list(self.altitude_history),
                "speed_history": list(self.speed_history),
            }
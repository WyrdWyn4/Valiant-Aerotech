import math
import time

from pymavlink import mavutil


class MessageProcessor:
    def __init__(self, state) -> None:
        self.state = state

    def process(self, msg) -> None:
        now = time.time()
        msg_type = msg.get_type()
        payload = msg.to_dict()

        self.state.record_message(msg_type, payload, now)

        if msg_type == "HEARTBEAT":
            self._handle_heartbeat(msg)

        elif msg_type == "GLOBAL_POSITION_INT":
            self._handle_global_position_int(payload, now)

        elif msg_type == "ATTITUDE":
            self._handle_attitude(payload)

        elif msg_type == "SYS_STATUS":
            self._handle_sys_status(payload)

        elif msg_type == "GPS_RAW_INT":
            self._handle_gps_raw_int(payload)

        elif msg_type == "VFR_HUD":
            self._handle_vfr_hud(payload, now)

    def _handle_heartbeat(self, msg) -> None:
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        flight_mode = mavutil.mode_string_v10(msg)
        self.state.update_status(flight_mode=flight_mode, armed=armed)

    def _handle_global_position_int(self, payload: dict, timestamp: float) -> None:
        lat = payload.get("lat")
        lon = payload.get("lon")
        alt = payload.get("alt")
        relative_alt = payload.get("relative_alt")
        vx = payload.get("vx")
        vy = payload.get("vy")

        lat_deg = lat / 1e7 if lat is not None else None
        lon_deg = lon / 1e7 if lon is not None else None
        msl_alt_m = alt / 1000.0 if alt is not None else None
        rel_alt_m = relative_alt / 1000.0 if relative_alt is not None else None

        groundspeed_mps = None
        if vx is not None and vy is not None:
            groundspeed_mps = math.sqrt(vx * vx + vy * vy) / 100.0

        self.state.update_position(
            timestamp=timestamp,
            lat=lat_deg,
            lon=lon_deg,
            alt_m=rel_alt_m,
            groundspeed_mps=groundspeed_mps,
        )

        with self.state.lock:
            self.state.msl_alt_m = msl_alt_m
            self.state.rel_alt_m = rel_alt_m

    def _handle_attitude(self, payload: dict) -> None:
        roll = payload.get("roll")
        pitch = payload.get("pitch")
        yaw = payload.get("yaw")

        self.state.update_attitude(
            roll_deg=math.degrees(roll) if roll is not None else None,
            pitch_deg=math.degrees(pitch) if pitch is not None else None,
            yaw_deg=math.degrees(yaw) if yaw is not None else None,
        )

    def _handle_sys_status(self, payload: dict) -> None:
        self.state.update_status(
            battery_remaining=payload.get("battery_remaining"),
        )

    def _handle_gps_raw_int(self, payload: dict) -> None:
        self.state.update_status(
            gps_fix_type=payload.get("fix_type"),
            satellites_visible=payload.get("satellites_visible"),
        )

    def _handle_vfr_hud(self, payload: dict, timestamp: float) -> None:
        groundspeed = payload.get("groundspeed")
        self.state.update_position(timestamp=timestamp, groundspeed_mps=groundspeed)
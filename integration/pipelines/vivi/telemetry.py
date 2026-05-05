"""MAVLink telemetry helpers for Vivi target localization.

The localization pipeline needs the vehicle pose at the instant a target is
marked. This module listens to the forwarded MAVLink stream and keeps the latest
usable pose ready for main.py.

Coordinate conventions
----------------------
The rest of the Vivi geometry code uses local ENU metres:
    x = east
    y = north
    z = up

MAVLink LOCAL_POSITION_NED uses NED metres:
    x = north
    y = east
    z = down

Therefore we convert:
    east  = y_ned
    north = x_ned
    up    = -z_ned

For height, real tests showed that LOCAL_POSITION_NED.z can remain zero on some
setups. To avoid all target heights becoming zero, this module now combines the
best available horizontal source with the best available vertical source:
    1. GLOBAL_POSITION_INT.relative_alt when available;
    2. VFR_HUD.alt relative to its first observed value;
    3. LOCAL_POSITION_NED.z only as a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Optional
import math
import time

from .frames import LocalFrame
from .pose import Pose
from .vector import Vec3


@dataclass
class TelemetrySnapshot:
    """Latest decoded telemetry values."""

    position_enu: Optional[Vec3] = None
    yaw_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    roll_deg: Optional[float] = None
    timestamp: float = 0.0
    position_source: str = "none"
    altitude_source: str = "none"
    attitude_source: str = "none"
    lat_deg: Optional[float] = None
    lon_deg: Optional[float] = None
    alt_m: Optional[float] = None
    rel_alt_m: Optional[float] = None
    vfr_alt_m: Optional[float] = None
    vfr_rel_alt_m: Optional[float] = None
    local_up_m: Optional[float] = None

    def has_pose(self) -> bool:
        return (
            self.position_enu is not None
            and self.yaw_deg is not None
            and self.pitch_deg is not None
            and self.roll_deg is not None
        )

    def to_pose(self) -> Pose:
        if not self.has_pose():
            raise RuntimeError("Telemetry does not yet contain a complete pose.")
        return Pose(
            position=self.position_enu,  # type: ignore[arg-type]
            yaw_deg=float(self.yaw_deg),
            pitch_deg=float(self.pitch_deg),
            roll_deg=float(self.roll_deg),
            timestamp=self.timestamp or time.time(),
        )


class MavlinkTelemetry:
    """Background MAVLink reader that maintains the latest vehicle pose."""

    def __init__(self, connection_string: str = "udpin:127.0.0.1:14550"):
        self.connection_string = connection_string
        self.master = None
        self._snapshot = TelemetrySnapshot()
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._gps_frame: Optional[LocalFrame] = None
        self._vfr_alt0_m: Optional[float] = None

    def connect(self, wait_heartbeat: bool = True, timeout_s: int = 30) -> None:
        """Open MAVLink connection and optionally wait for heartbeat."""
        try:
            from pymavlink import mavutil
        except ImportError as exc:
            raise RuntimeError(
                "pymavlink is not installed. Install it with: pip install pymavlink"
            ) from exc

        self.master = mavutil.mavlink_connection(self.connection_string)

        if wait_heartbeat:
            print("Waiting for Vivi MAVLink heartbeat...")
            self.master.wait_heartbeat(timeout=timeout_s)
            print(
                "Connected to MAVLink "
                f"system={self.master.target_system}, component={self.master.target_component}"
            )

    def start(self) -> None:
        """Start background reader thread."""
        if self.master is None:
            raise RuntimeError("Call connect() before start().")
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._reader_loop, name="ViviMavlinkReader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background reader thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_snapshot(self) -> TelemetrySnapshot:
        """Return a copy of the latest telemetry snapshot."""
        with self._lock:
            return TelemetrySnapshot(**self._snapshot.__dict__)

    def get_pose(self) -> Pose:
        """Return the latest complete pose or raise if not ready."""
        return self.get_snapshot().to_pose()

    def wait_for_pose(self, timeout_s: float = 5.0) -> Pose:
        """Block until a complete pose is available."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            snapshot = self.get_snapshot()
            if snapshot.has_pose():
                return snapshot.to_pose()
            time.sleep(0.02)
        snapshot = self.get_snapshot()
        raise TimeoutError(
            "Timed out waiting for complete telemetry pose. "
            f"position_source={snapshot.position_source}, altitude_source={snapshot.altitude_source}, "
            f"attitude_source={snapshot.attitude_source}"
        )

    def print_pose(self) -> None:
        """Print the latest pose in the same terms used by setup/localization."""
        snapshot = self.get_snapshot()
        if not snapshot.has_pose():
            print(
                "Pose not ready: "
                f"position_source={snapshot.position_source}, altitude_source={snapshot.altitude_source}, "
                f"attitude_source={snapshot.attitude_source}"
            )
            return
        pose = snapshot.to_pose()
        print(
            "Pose: "
            f"east={pose.position.x:.2f} m, "
            f"north={pose.position.y:.2f} m, "
            f"up={pose.position.z:.2f} m, "
            f"yaw={pose.yaw_deg:.1f} deg, "
            f"pitch={pose.pitch_deg:.1f} deg, "
            f"roll={pose.roll_deg:.1f} deg "
            f"[xy={snapshot.position_source}, z={snapshot.altitude_source}, attitude={snapshot.attitude_source}]"
        )

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg = self.master.recv_match(blocking=True, timeout=0.5)  # type: ignore[union-attr]
            except Exception as exc:  # keep field loop alive but visible
                print(f"MAVLink receive error: {exc}")
                continue
            if msg is None:
                continue
            self._handle_message(msg)

    def _handle_message(self, msg) -> None:
        msg_type = msg.get_type()

        if msg_type == "ATTITUDE":
            self._update_attitude(msg)
        elif msg_type == "LOCAL_POSITION_NED":
            self._update_local_position_ned(msg)
        elif msg_type == "GLOBAL_POSITION_INT":
            self._update_global_position_int(msg)
        elif msg_type == "VFR_HUD":
            self._update_vfr_hud(msg)

    def _best_up_locked(self, local_up: Optional[float] = None) -> tuple[float, str]:
        """Return the best current vertical value and its source."""
        if self._snapshot.rel_alt_m is not None:
            return float(self._snapshot.rel_alt_m), "GLOBAL_POSITION_INT.relative_alt"
        if self._snapshot.vfr_rel_alt_m is not None:
            return float(self._snapshot.vfr_rel_alt_m), "VFR_HUD.alt_relative"
        if local_up is not None:
            return float(local_up), "LOCAL_POSITION_NED.z"
        if self._snapshot.local_up_m is not None:
            return float(self._snapshot.local_up_m), "LOCAL_POSITION_NED.z"
        return 0.0, "unknown_zero_fallback"

    def _replace_position_z_locked(self) -> None:
        """Refresh only z if a better altitude source arrived after xy."""
        if self._snapshot.position_enu is None:
            return
        up, altitude_source = self._best_up_locked()
        pos = self._snapshot.position_enu
        self._snapshot.position_enu = Vec3(pos.x, pos.y, up)
        self._snapshot.altitude_source = altitude_source
        self._snapshot.timestamp = time.time()

    def _update_attitude(self, msg) -> None:
        # MAVLink ATTITUDE angles are radians.
        yaw_deg = math.degrees(float(msg.yaw)) % 360.0
        pitch_deg = math.degrees(float(msg.pitch))
        roll_deg = math.degrees(float(msg.roll))

        with self._lock:
            self._snapshot.yaw_deg = yaw_deg
            self._snapshot.pitch_deg = pitch_deg
            self._snapshot.roll_deg = roll_deg
            self._snapshot.timestamp = time.time()
            self._snapshot.attitude_source = "ATTITUDE"

    def _update_local_position_ned(self, msg) -> None:
        # LOCAL_POSITION_NED: x=north, y=east, z=down.
        east = float(msg.y)
        north = float(msg.x)
        local_up = -float(msg.z)
        with self._lock:
            self._snapshot.local_up_m = local_up
            up, altitude_source = self._best_up_locked(local_up=local_up)
            self._snapshot.position_enu = Vec3(east, north, up)
            self._snapshot.timestamp = time.time()
            self._snapshot.position_source = "LOCAL_POSITION_NED"
            self._snapshot.altitude_source = altitude_source

    def _update_global_position_int(self, msg) -> None:
        # GLOBAL_POSITION_INT: lat/lon are degE7, alt/relative_alt are millimetres.
        lat_deg = float(msg.lat) / 1e7
        lon_deg = float(msg.lon) / 1e7
        alt_m = float(msg.alt) / 1000.0
        rel_alt_m = float(msg.relative_alt) / 1000.0

        with self._lock:
            self._snapshot.lat_deg = lat_deg
            self._snapshot.lon_deg = lon_deg
            self._snapshot.alt_m = alt_m
            self._snapshot.rel_alt_m = rel_alt_m

            if self._gps_frame is None:
                self._gps_frame = LocalFrame(lat0_deg=lat_deg, lon0_deg=lon_deg, alt0_m=alt_m)

            # If LOCAL_POSITION_NED already provides good xy, only replace z.
            # This is the key fix for real tests where LOCAL_POSITION_NED.z stayed
            # at zero but GLOBAL_POSITION_INT.relative_alt changed correctly.
            if self._snapshot.position_source == "LOCAL_POSITION_NED" and self._snapshot.position_enu is not None:
                self._replace_position_z_locked()
                return

            pos = self._gps_frame.lla_to_enu(lat_deg, lon_deg, alt_m)
            self._snapshot.position_enu = Vec3(pos.x, pos.y, rel_alt_m)
            self._snapshot.timestamp = time.time()
            self._snapshot.position_source = "GLOBAL_POSITION_INT"
            self._snapshot.altitude_source = "GLOBAL_POSITION_INT.relative_alt"

    def _update_vfr_hud(self, msg) -> None:
        # VFR_HUD.heading is degrees. Use only if ATTITUDE has not arrived.
        alt_m = float(msg.alt)
        if self._vfr_alt0_m is None:
            self._vfr_alt0_m = alt_m
        vfr_rel_alt_m = alt_m - self._vfr_alt0_m

        with self._lock:
            self._snapshot.vfr_alt_m = alt_m
            self._snapshot.vfr_rel_alt_m = vfr_rel_alt_m

            # Use VFR altitude as a backup only when GLOBAL relative altitude has
            # not arrived. Keep LOCAL/GPS xy unchanged.
            if self._snapshot.rel_alt_m is None:
                self._replace_position_z_locked()

            if self._snapshot.attitude_source != "ATTITUDE":
                self._snapshot.yaw_deg = float(msg.heading) % 360.0
                self._snapshot.pitch_deg = self._snapshot.pitch_deg if self._snapshot.pitch_deg is not None else 0.0
                self._snapshot.roll_deg = self._snapshot.roll_deg if self._snapshot.roll_deg is not None else 0.0
                self._snapshot.timestamp = time.time()
                self._snapshot.attitude_source = "VFR_HUD_HEADING_FALLBACK"

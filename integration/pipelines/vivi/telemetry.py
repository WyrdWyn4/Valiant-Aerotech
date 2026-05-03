"""MAVLink telemetry reader for Vivi.

This module converts live MAVLink messages into the Pose object used by the
survey, localization, and reporting pipeline.

Why this exists
---------------
The operator should not manually type x, y, z, yaw, pitch, and roll during the
mission. Mission Planner / MAVProxy already receives those values from the
vehicle. This module listens to the forwarded MAVLink stream and keeps the
latest usable pose ready for main.py.

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

MAVLink ATTITUDE uses radians. We convert:
    yaw   -> heading degrees clockwise from north
    pitch -> degrees, nose-up positive
    roll  -> degrees, positive right-side-down/right-bank
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
    """Latest decoded telemetry values.

    position_enu:
        Vehicle position in the same local ENU frame used by the geometry code.
    yaw_deg/pitch_deg/roll_deg:
        Vehicle attitude in degrees.
    source:
        The message source used for position, usually LOCAL_POSITION_NED or GPS.
    """

    position_enu: Optional[Vec3] = None
    yaw_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    roll_deg: Optional[float] = None
    timestamp: float = 0.0
    position_source: str = "none"
    attitude_source: str = "none"
    lat_deg: Optional[float] = None
    lon_deg: Optional[float] = None
    alt_m: Optional[float] = None
    rel_alt_m: Optional[float] = None

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
    """Background MAVLink reader that maintains the latest vehicle pose.

    The class is intentionally small and dependency-light. It only requires
    pymavlink and the existing Vivi geometry classes.

    Typical use in main.py:

        telemetry = MavlinkTelemetry("udpin:127.0.0.1:14550")
        telemetry.connect()
        telemetry.start()
        pose = telemetry.wait_for_pose(timeout_s=10)

    The capture-point and target-marking code can then call get_pose() instead
    of asking the operator to manually type coordinates.
    """

    def __init__(self, connection_string: str = "udpin:127.0.0.1:14550"):
        self.connection_string = connection_string
        self.master = None
        self._snapshot = TelemetrySnapshot()
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._gps_frame: Optional[LocalFrame] = None

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
            f"position_source={snapshot.position_source}, attitude_source={snapshot.attitude_source}"
        )

    def print_pose(self) -> None:
        """Print the latest pose in the same terms used by setup/localization."""
        snapshot = self.get_snapshot()
        if not snapshot.has_pose():
            print(
                "Pose not ready: "
                f"position_source={snapshot.position_source}, attitude_source={snapshot.attitude_source}"
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
            f"[{snapshot.position_source}, {snapshot.attitude_source}]"
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
            # Fallback position if LOCAL_POSITION_NED is not available.
            self._update_global_position_int(msg)
        elif msg_type == "VFR_HUD":
            # Fallback yaw only. ATTITUDE is preferred.
            self._update_vfr_hud(msg)

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
        up = -float(msg.z)
        with self._lock:
            self._snapshot.position_enu = Vec3(east, north, up)
            self._snapshot.timestamp = time.time()
            self._snapshot.position_source = "LOCAL_POSITION_NED"

    def _update_global_position_int(self, msg) -> None:
        # GLOBAL_POSITION_INT: lat/lon are degE7, alt/relative_alt are millimetres.
        lat_deg = float(msg.lat) / 1e7
        lon_deg = float(msg.lon) / 1e7
        alt_m = float(msg.alt) / 1000.0
        rel_alt_m = float(msg.relative_alt) / 1000.0

        # If LOCAL_POSITION_NED is already available, keep it as the primary
        # position source. GPS fallback is mainly for vehicles/configurations that
        # do not stream LOCAL_POSITION_NED.
        with self._lock:
            self._snapshot.lat_deg = lat_deg
            self._snapshot.lon_deg = lon_deg
            self._snapshot.alt_m = alt_m
            self._snapshot.rel_alt_m = rel_alt_m

            if self._snapshot.position_source == "LOCAL_POSITION_NED":
                return

            if self._gps_frame is None:
                self._gps_frame = LocalFrame(lat0_deg=lat_deg, lon0_deg=lon_deg, alt0_m=alt_m)

            pos = self._gps_frame.lla_to_enu(lat_deg, lon_deg, alt_m)
            # Prefer relative_alt for up if available because it is more intuitive
            # for local mission geometry than MSL altitude.
            pos = Vec3(pos.x, pos.y, rel_alt_m)
            self._snapshot.position_enu = pos
            self._snapshot.timestamp = time.time()
            self._snapshot.position_source = "GLOBAL_POSITION_INT"

    def _update_vfr_hud(self, msg) -> None:
        # VFR_HUD.heading is degrees. Use only if ATTITUDE has not arrived.
        with self._lock:
            if self._snapshot.attitude_source != "ATTITUDE":
                self._snapshot.yaw_deg = float(msg.heading) % 360.0
                self._snapshot.pitch_deg = self._snapshot.pitch_deg if self._snapshot.pitch_deg is not None else 0.0
                self._snapshot.roll_deg = self._snapshot.roll_deg if self._snapshot.roll_deg is not None else 0.0
                self._snapshot.timestamp = time.time()
                self._snapshot.attitude_source = "VFR_HUD_HEADING_FALLBACK"

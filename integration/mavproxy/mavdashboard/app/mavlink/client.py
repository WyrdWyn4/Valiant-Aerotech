import threading
import time

from pymavlink import mavutil


class MavlinkClient:
    def __init__(
        self,
        endpoint: str,
        heartbeat_timeout: int,
        reconnect_delay_seconds: float,
        state,
        processor,
        logger=None,
    ) -> None:
        self.endpoint = endpoint
        self.heartbeat_timeout = heartbeat_timeout
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self.state = state
        self.processor = processor
        self.logger = logger

        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            connection = None

            try:
                connection = mavutil.mavlink_connection(self.endpoint)
                connection.wait_heartbeat(timeout=self.heartbeat_timeout)

                self.state.set_connected(
                    system_id=connection.target_system,
                    component_id=connection.target_component,
                )

                while not self._stop_event.is_set():
                    msg = connection.recv_match(blocking=True, timeout=1)

                    if msg is None:
                        continue

                    if msg.get_type() == "BAD_DATA":
                        continue

                    timestamp = time.time()
                    self.processor.process(msg)

                    if self.logger is not None:
                        self.logger.log(timestamp, msg)

            except Exception as exc:
                self.state.set_disconnected(error=str(exc))
                time.sleep(self.reconnect_delay_seconds)

            finally:
                if connection is not None:
                    self.state.set_disconnected()
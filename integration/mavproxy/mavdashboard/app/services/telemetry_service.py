from app.core.config import Config
from app.core.telemetry_state import TelemetryState
from app.mavlink.client import MavlinkClient
from app.mavlink.processor import MessageProcessor
from app.storage.csv_logger import CsvLogger


class TelemetryService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = TelemetryState(history_limit=config.history_limit)
        self.processor = MessageProcessor(self.state)

        self.logger = None
        if config.log_enabled:
            self.logger = CsvLogger(config.log_file)

        self.client = MavlinkClient(
            endpoint=config.udp_endpoint,
            heartbeat_timeout=config.heartbeat_timeout,
            reconnect_delay_seconds=config.reconnect_delay_seconds,
            state=self.state,
            processor=self.processor,
            logger=self.logger,
        )

    def start(self) -> None:
        self.client.start()

    def stop(self) -> None:
        self.client.stop()

    def snapshot(self) -> dict:
        return self.state.snapshot()
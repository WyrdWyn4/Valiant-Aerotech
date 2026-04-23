from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    udp_endpoint: str = "udpin:127.0.0.1:14550"
    heartbeat_timeout: int = 30
    reconnect_delay_seconds: float = 2.0
    history_limit: int = 300
    ui_refresh_ms: int = 1000
    log_enabled: bool = True
    log_file: Path = Path("logs/raw_messages.csv")
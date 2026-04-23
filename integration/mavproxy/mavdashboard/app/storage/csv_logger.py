import csv
import json
from pathlib import Path
from threading import Lock


class CsvLogger:
    FIELDNAMES = [
        "timestamp",
        "message_type",
        "src_system",
        "src_component",
        "payload_json",
    ]

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

        if not self.filepath.exists():
            with self.filepath.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()

    def log(self, timestamp: float, msg) -> None:
        row = {
            "timestamp": timestamp,
            "message_type": msg.get_type(),
            "src_system": msg.get_srcSystem(),
            "src_component": msg.get_srcComponent(),
            "payload_json": json.dumps(msg.to_dict(), default=str),
        }

        with self._lock:
            with self.filepath.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writerow(row)
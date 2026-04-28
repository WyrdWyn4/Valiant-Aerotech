"""Non-blocking terminal command input for mission event marking."""
from __future__ import annotations

import queue
import threading
from typing import Optional


class CommandInput:
    def __init__(self) -> None:
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        while True:
            try:
                line = input().strip()
            except EOFError:
                return
            if line:
                self._queue.put(line)

    def get_nowait(self) -> Optional[str]:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

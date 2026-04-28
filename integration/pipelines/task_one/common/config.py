"""Config loading and validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .geometry import GeoPoint


def load_config(path: str) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    return cfg


def points_from_config(items: Optional[List[Dict[str, Any]]]) -> List[GeoPoint]:
    if not items:
        return []
    return [GeoPoint(float(p["lat"]), float(p["lon"])) for p in items]


def get_float(cfg: Dict[str, Any], key: str, default: float) -> float:
    value = cfg.get(key, default)
    try:
        return float(value)
    except Exception:
        return default


def get_int(cfg: Dict[str, Any], key: str, default: int) -> int:
    value = cfg.get(key, default)
    try:
        return int(value)
    except Exception:
        return default

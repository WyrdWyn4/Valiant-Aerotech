"""JSON and report-file persistence for the Task One desktop localizer."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copy2
from typing import Any

from .models import ProjectSession, dataclass_to_dict, project_from_json
from .reporting import render_report


def ensure_workspace(session: ProjectSession) -> Path:
    workspace = Path(session.workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "screenshots").mkdir(parents=True, exist_ok=True)
    return workspace


def resolve_path(path_str: str, *, base_dir: Path | None = None) -> Path:
    path = Path(path_str)
    if path.is_absolute() or base_dir is None:
        return path
    return base_dir / path


def save_session(session: ProjectSession, *, base_dir: Path | None = None) -> Path:
    session.normalize_output_paths()
    workspace = ensure_workspace(session)
    session_path = resolve_path(session.session_json_path, base_dir=base_dir)
    if not session_path.is_absolute() and base_dir is None:
        session_path = workspace / session_path.name
    session_path.parent.mkdir(parents=True, exist_ok=True)
    with session_path.open("w", encoding="utf-8") as handle:
        json.dump(dataclass_to_dict(session), handle, indent=2)
    return session_path


def load_session(path: str | Path) -> ProjectSession:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = json.load(handle)
    session = project_from_json(raw)
    session.session_json_path = str(path)
    return session


def write_report(session: ProjectSession, *, base_dir: Path | None = None) -> Path:
    session.normalize_output_paths()
    workspace = ensure_workspace(session)
    output_path = resolve_path(session.output_txt_path, base_dir=base_dir)
    if not output_path.is_absolute() and base_dir is None:
        output_path = workspace / output_path.name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(session), encoding="utf-8")
    return output_path


def copy_image_into_workspace(session: ProjectSession, source_path: str | Path) -> Path:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Image file does not exist: {source}")
    workspace = ensure_workspace(session)
    destination = workspace / "screenshots" / source.name
    if destination.exists():
        stem = source.stem
        suffix = source.suffix
        counter = 2
        while True:
            candidate = workspace / "screenshots" / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                destination = candidate
                break
            counter += 1
    copy2(source, destination)
    return destination

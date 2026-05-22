from __future__ import annotations

from task_one_localizer.models import ProjectSession
from task_one_localizer.persistence import save_session, write_report


def test_repeated_writes_do_not_nest_workspace(tmp_path) -> None:
    session = ProjectSession(workspace_dir=str(tmp_path / "workspace"))
    first_report = write_report(session)
    first_session = save_session(session)
    second_report = write_report(session)
    second_session = save_session(session)

    assert first_report == second_report
    assert first_session == second_session
    assert first_report.parent.name == "workspace"
    assert first_session.parent.name == "workspace"

from __future__ import annotations

from task_one_localizer.models import ProjectSession, SurfaceType, TargetRecord
from task_one_localizer.reporting import (
    DoorHorizontalReference,
    generate_ground_location_sentence,
    generate_wall_location_sentence,
    render_report,
)


def test_wall_sentence_prefers_door_relative_wording() -> None:
    sentence, warnings = generate_wall_location_sentence(
        face_direction="North",
        height_above_ground_m=2.34,
        x_from_left_m=4.0,
        wall_width_m=10.0,
        colour="Red",
        door_reference=DoorHorizontalReference(relation="left", distance_m=0.82),
    )
    assert "north face" in sentence
    assert "2.3 m above ground" in sentence
    assert "0.8 m left of the door" in sentence
    assert "colour is red" in sentence
    assert warnings == []


def test_directly_above_door_warning_propagates() -> None:
    sentence, warnings = generate_wall_location_sentence(
        face_direction="South",
        height_above_ground_m=3.0,
        x_from_left_m=4.0,
        wall_width_m=10.0,
        colour="Blue",
        door_reference=DoorHorizontalReference(
            relation="above",
            warning="Target is classified as directly above the door; confirm this wording before submission.",
        ),
    )
    assert "directly above the door" in sentence
    assert warnings


def test_ground_sentence_matches_expected_structure() -> None:
    sentence = generate_ground_location_sentence(
        reference_face="West",
        distance_from_face_m=5.22,
        colour="Green",
        door_relation="right",
        door_offset_m=0.19,
    )
    assert "On the ground" in sentence
    assert "5.2 m away from the west face" in sentence
    assert "0.2 m right of the door" in sentence


def test_report_rendering_uses_target_blocks() -> None:
    session = ProjectSession(team_name="Valiant_Aerotech")
    session.targets.append(
        TargetRecord(
            number=1,
            surface_type=SurfaceType.WALL.value,
            colour="Yellow",
            description_text="On the south face of the building, approximately 1.2 m above ground. The colour is yellow.",
            generated_text="",
            confidence="High",
        )
    )
    report = render_report(session)
    assert report.startswith("Task 1 Target Localization Report - Valiant Aerotech")
    assert "Target 1:" in report
    assert "Colour: Yellow" in report

"""CONOPS-style sentence generation and Task One text-file rendering."""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import round_decimetre
from .models import ProjectSession, TargetRecord


@dataclass(slots=True)
class DoorHorizontalReference:
    relation: str  # left, right, above, ambiguous
    distance_m: float | None = None
    warning: str | None = None


EDGE_REFERENCE_BY_FACE = {
    "North": {"left": "eastern", "right": "western"},
    "South": {"left": "western", "right": "eastern"},
    "East": {"left": "southern", "right": "northern"},
    "West": {"left": "northern", "right": "southern"},
}


def sentence_case_colour(colour: str) -> str:
    return colour.strip().lower()


def format_m(value: float) -> str:
    return f"{round_decimetre(value):.1f} m"


def choose_nearest_cardinal_side(
    *, face_direction: str, x_from_left_m: float, wall_width_m: float
) -> tuple[str, float]:
    left_distance = x_from_left_m
    right_distance = wall_width_m - x_from_left_m
    edge_side = "left" if left_distance <= right_distance else "right"
    cardinal_word = EDGE_REFERENCE_BY_FACE.get(face_direction, EDGE_REFERENCE_BY_FACE["North"])[edge_side]
    distance_m = left_distance if edge_side == "left" else right_distance
    return cardinal_word, max(0.0, distance_m)


def generate_wall_location_sentence(
    *,
    face_direction: str,
    height_above_ground_m: float,
    x_from_left_m: float,
    wall_width_m: float,
    colour: str,
    door_reference: DoorHorizontalReference | None = None,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    face = face_direction.lower()
    height_text = format_m(max(0.0, height_above_ground_m))

    if door_reference is not None:
        if door_reference.warning:
            warnings.append(door_reference.warning)
        if door_reference.relation == "above":
            location = (
                f"On the {face} face of the building, approximately {height_text} above ground "
                "and directly above the door when facing it from outside."
            )
        elif door_reference.relation in {"left", "right"} and door_reference.distance_m is not None:
            location = (
                f"On the {face} face of the building, approximately {height_text} above ground "
                f"and {format_m(max(0.0, door_reference.distance_m))} {door_reference.relation} of the door "
                "when facing it from outside."
            )
        else:
            location = (
                f"On the {face} face of the building, approximately {height_text} above ground "
                "and near the marked door reference when facing it from outside."
            )
            warnings.append(
                "Door-relative wording could not be resolved automatically; edit the sentence before confirming."
            )
    else:
        cardinal_word, side_distance_m = choose_nearest_cardinal_side(
            face_direction=face_direction,
            x_from_left_m=x_from_left_m,
            wall_width_m=wall_width_m,
        )
        location = (
            f"On the {face} face of the building, approximately {height_text} above ground "
            f"and {format_m(side_distance_m)} from the {cardinal_word} wall."
        )

    sentence = f"{location} The colour is {sentence_case_colour(colour)}."
    return sentence, warnings


def generate_ground_location_sentence(
    *,
    reference_face: str,
    distance_from_face_m: float,
    colour: str,
    door_relation: str | None = None,
    door_offset_m: float | None = None,
    freeform_tail: str | None = None,
) -> str:
    face = reference_face.lower()
    sentence = (
        f"On the ground, approximately {format_m(max(0.0, distance_from_face_m))} away from the {face} face of the building"
    )
    if door_relation in {"left", "right"} and door_offset_m is not None:
        sentence += (
            f" and {format_m(max(0.0, door_offset_m))} {door_relation} of the door when facing it from outside"
        )
    elif door_relation == "aligned":
        sentence += " and aligned with the door when facing it from outside"
    if freeform_tail:
        sentence += f", {freeform_tail.strip()}"
    sentence += f". The colour is {sentence_case_colour(colour)}."
    return sentence


def render_target_block(target: TargetRecord) -> str:
    description = target.description_text.strip()
    return (
        f"Target {target.number}:\n"
        f"Colour: {target.colour}\n"
        f"Location: {description}\n"
    )


def render_report(session: ProjectSession) -> str:
    title_team = session.team_name.replace("_", " ")
    lines = [f"Task 1 Target Localization Report - {title_team}", ""]
    for target in sorted(session.targets, key=lambda item: item.number):
        lines.append(render_target_block(target).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

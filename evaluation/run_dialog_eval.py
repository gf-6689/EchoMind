"""Shared dataset loading and validation for dialog evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .intent_metrics import INTENT_LABELS


_CASE_FIELDS = {
    "case_id",
    "category",
    "description",
    "context",
    "turns",
    "expected_routing",
}
_TURN_FIELDS = {"user_message", "reference_answer", "required_points"}
_ROUTING_FIELDS = {"intent", "agent_type"}
_AGENT_TYPES = {"general", "technical", "billing", "escalation"}


def _require_exact_fields(value: object, fields: set[str], location: str) -> Dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{location}: must be an object")
    actual_fields = set(value)
    missing = fields - actual_fields
    extra = actual_fields - fields
    if missing:
        raise ValueError(f"{location}: missing fields {sorted(missing)}")
    if extra:
        raise ValueError(f"{location}: unexpected fields {sorted(extra)}")
    return value


def _require_string(value: object, location: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{location}: must be a string")
    if nonempty and not value.strip():
        raise ValueError(f"{location}: must be non-empty")
    return value


def validate_cases(cases: object, expected_count: Optional[int] = None) -> None:
    """Validate the fixed dialog-case schema used by all evaluation runners."""
    if not isinstance(cases, list):
        raise ValueError("dialog cases: top level must be a list")
    if expected_count is not None and len(cases) != expected_count:
        raise ValueError(f"expected {expected_count} cases, found {len(cases)}")

    seen_case_ids = set()
    for case_number, raw_case in enumerate(cases, 1):
        location = f"case {case_number}"
        case = _require_exact_fields(raw_case, _CASE_FIELDS, location)
        case_id = _require_string(case["case_id"], f"{location}.case_id", nonempty=True)
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)

        _require_string(case["category"], f"{location}.category", nonempty=True)
        _require_string(case["description"], f"{location}.description", nonempty=True)
        _require_string(case["context"], f"{location}.context")

        turns = case["turns"]
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"{location}.turns: must be a non-empty list")
        for turn_number, raw_turn in enumerate(turns, 1):
            turn_location = f"{location}.turns[{turn_number}]"
            turn = _require_exact_fields(raw_turn, _TURN_FIELDS, turn_location)
            _require_string(turn["user_message"], f"{turn_location}.user_message", nonempty=True)
            _require_string(turn["reference_answer"], f"{turn_location}.reference_answer", nonempty=True)
            required_points = turn["required_points"]
            if not isinstance(required_points, list) or not required_points:
                raise ValueError(f"{turn_location}.required_points: must be a non-empty list")
            for point_number, point in enumerate(required_points, 1):
                _require_string(
                    point,
                    f"{turn_location}.required_points[{point_number}]",
                    nonempty=True,
                )

        routing = _require_exact_fields(
            case["expected_routing"], _ROUTING_FIELDS, f"{location}.expected_routing"
        )
        intent = _require_string(routing["intent"], f"{location}.expected_routing.intent")
        if intent not in INTENT_LABELS:
            raise ValueError(f"{location}.expected_routing.intent: unknown intent {intent!r}")
        agent_type = _require_string(
            routing["agent_type"], f"{location}.expected_routing.agent_type"
        )
        if agent_type not in _AGENT_TYPES:
            raise ValueError(
                f"{location}.expected_routing.agent_type: unknown agent type {agent_type!r}"
            )


def load_and_validate(
    path: Path, expected_count: Optional[int] = None
) -> List[Dict[str, object]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    validate_cases(cases, expected_count=expected_count)
    return cases

"""Shared dataset loading and validation for dialog evaluation."""

from __future__ import annotations

import json
from uuid import uuid4
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from agents.agent_orchestrator import Request
from evaluation.dialog_judge import sanitize_error
from evaluation.dialog_metrics import aggregate_case_scores
from .intent_metrics import INTENT_LABELS


PASS_THRESHOLD = 0.75


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


def build_controlled_context(context: object) -> str:
    """Return only the case-supplied evaluation context."""
    return str(context)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def routing_audit(expected: Mapping[str, object], first_turn: Mapping[str, object]) -> Dict[str, bool]:
    return {
        "intent_match": first_turn.get("intent") == expected.get("intent"),
        "agent_match": first_turn.get("primary_agent") == expected.get("agent_type"),
    }


async def evaluate_case(
    case: Mapping[str, object],
    orchestrator: object,
    judge: object,
    user_id: str = "eval-user",
) -> Dict[str, object]:
    """Run and independently judge every turn in one validated dialog case."""
    conv_id = str(uuid4())
    history: List[Dict[str, str]] = []
    turn_results = []
    prior_agent_failure = False
    for turn_index, turn in enumerate(case["turns"], 1):
        if prior_agent_failure:
            turn_results.append({
                "turn_id": turn_index,
                "user_message": turn["user_message"],
                "agent_response": None,
                "intent": None,
                "primary_agent": None,
                "supporting_agents": [],
                "routing_reason": None,
                "routing_confidence": None,
                "escalated": None,
                "agent_latency_ms": None,
                "agent_failed": False,
                "agent_error": "skipped after prior agent failure",
                "judge_failed": False,
                "judge_error": None,
                "judge_skipped": True,
                "judge_attempts": 0,
                "judge": None,
            })
            continue
        request = Request(
            message=turn["user_message"],
            user_id=user_id,
            conv_id=conv_id,
            context=build_controlled_context(case["context"]),
            history=list(history[-5:]),
        )
        try:
            result = await orchestrator.run(request)
        except Exception as exc:
            turn_results.append({
                "turn_id": turn_index,
                "user_message": turn["user_message"],
                "agent_response": None,
                "intent": None,
                "primary_agent": None,
                "supporting_agents": [],
                "routing_reason": None,
                "routing_confidence": None,
                "escalated": None,
                "agent_latency_ms": None,
                "agent_failed": True,
                "agent_error": sanitize_error(exc),
                "judge_failed": False,
                "judge_error": None,
                "judge_skipped": True,
                "judge_attempts": 0,
                "judge": None,
            })
            prior_agent_failure = True
            continue
        primary_agent = result.primary_agent or result.agent_type
        turn_result = {
            "turn_id": turn_index,
            "user_message": turn["user_message"],
            "agent_response": result.response,
            "intent": _enum_value(result.intent),
            "primary_agent": _enum_value(primary_agent),
            "supporting_agents": [_enum_value(item) for item in result.supporting_agents],
            "routing_reason": result.routing_reason,
            "routing_confidence": result.routing_confidence,
            "escalated": result.escalated,
            "agent_latency_ms": result.latency_ms,
            "agent_failed": False,
            "agent_error": None,
        }
        judge_result = dict(await judge.judge_turn(
            question=turn["user_message"],
            response=result.response,
            context=request.context,
            reference_answer=turn["reference_answer"],
            required_points=turn["required_points"],
            history=list(history),
        ))
        if judge_result.get("judge_error") is not None:
            judge_result["judge_error"] = sanitize_error(
                RuntimeError(str(judge_result["judge_error"]))
            )
        turn_result.update(judge_result)
        turn_results.append(turn_result)
        history.extend((
            {"role": "user", "content": turn["user_message"]},
            {"role": "assistant", "content": result.response},
        ))

    case_scores = aggregate_case_scores(turn_results)
    expected_routing = dict(case["expected_routing"])
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "description": case["description"],
        "conv_id": conv_id,
        "expected_routing": expected_routing,
        "turns": turn_results,
        "agent_failed": any(turn["agent_failed"] for turn in turn_results),
        "judge_failed": any(
            turn["judge_failed"] for turn in turn_results if not turn["judge_skipped"]
        ),
        "judge_skipped": any(turn["judge_skipped"] for turn in turn_results),
        "case_scores": case_scores,
        "passed": case_scores["overall"] >= PASS_THRESHOLD if case_scores is not None else None,
        "routing_audit": routing_audit(expected_routing, turn_results[0]),
    }

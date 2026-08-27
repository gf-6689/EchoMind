"""Deterministic scoring and pass policy for dialog judge v5.

This module is the only producer of final dimension scores, overall,
turn pass, case pass and pass rate.  It is deliberately free of network
access, environment variables, time and randomness.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Sequence

PASS_RULE_VERSION = "dialog_pass_v5"
DIMENSION_PASS_FLOOR = 0.75
OVERALL_PASS_THRESHOLD = 0.75
COMPLETENESS_POLICY_VERSION = "required_point_coverage_equal_weight_v1"
VIOLATION_POLICY_VERSION = "dialog_violation_caps_v1"

COVERAGE_VALUES = {
    "covered": 1.0,
    "partial": 0.5,
    "missing": 0.0,
}

VIOLATION_CAPS = {
    "unsupported_operation": {"accuracy": 0.75, "helpfulness": 0.75},
    "false_completed_action": {"accuracy": 0.50, "helpfulness": 0.50},
    "unsupported_process_or_requirement": {"accuracy": 0.75},
    "misleading_unsupported_content": {"helpfulness": 0.85},
    "sensitive_request_without_safety": {"accuracy": 0.75, "helpfulness": 0.50},
    "context_contradiction": {"accuracy": 0.50},
    "core_fact_reversed": {"accuracy": 0.25},
    "severe_readability_defect": {"helpfulness": 0.75},
}

FINAL_DIMENSIONS = ("relevance", "accuracy", "completeness", "helpfulness")


def compute_completeness(coverage: Sequence[Mapping[str, object]]) -> float:
    """Derive completeness as the unrounded equal-weight mean of coverage status values."""
    if not coverage:
        raise ValueError("required_point_coverage must not be empty")
    values = []
    for entry in coverage:
        status = entry["status"]
        if status not in COVERAGE_VALUES:
            raise ValueError(f"unknown coverage status: {status!r}")
        values.append(COVERAGE_VALUES[status])
    return math.fsum(values) / len(values)


def compute_strictest_caps(codes: Sequence[str]) -> Dict[str, float]:
    """Return per-dimension strictest caps; only dimensions capped below 1.0 appear."""
    caps = {"accuracy": 1.0, "helpfulness": 1.0}
    for code in codes:
        rule = VIOLATION_CAPS.get(code)
        if rule is None:
            raise ValueError(f"unknown violation code: {code!r}")
        for dimension, value in rule.items():
            caps[dimension] = min(caps[dimension], value)
    return {name: value for name, value in caps.items() if value < 1.0}


def score_assessment(assessment: Mapping[str, object]) -> Dict[str, object]:
    """Return {'applied_caps': ..., 'final_scores': ...} for a validated assessment."""
    base_scores = assessment["base_scores"]
    coverage = assessment["required_point_coverage"]
    codes = [violation["code"] for violation in assessment.get("violations", [])]
    applied_caps = compute_strictest_caps(codes)
    final_relevance = float(base_scores["relevance"])
    final_accuracy = min(float(base_scores["accuracy"]), applied_caps.get("accuracy", 1.0))
    final_completeness = compute_completeness(coverage)
    final_helpfulness = min(float(base_scores["helpfulness"]), applied_caps.get("helpfulness", 1.0))
    final_overall = (
        final_relevance + final_accuracy + final_completeness + final_helpfulness
    ) / 4.0
    return {
        "applied_caps": dict(applied_caps),
        "final_scores": {
            "relevance": final_relevance,
            "accuracy": final_accuracy,
            "completeness": final_completeness,
            "helpfulness": final_helpfulness,
            "overall": final_overall,
        },
    }


def compute_turn_pass(
    final_scores: Mapping[str, float],
    *,
    agent_failed: bool,
    judge_failed: bool,
    judge_skipped: bool,
) -> bool:
    """A turn passes only when no failure flag is set and every threshold holds."""
    if agent_failed or judge_failed or judge_skipped:
        return False
    for name in FINAL_DIMENSIONS:
        if final_scores[name] < DIMENSION_PASS_FLOOR:
            return False
    return final_scores["overall"] >= OVERALL_PASS_THRESHOLD


def compute_case_pass(turn_passes: Sequence[bool]) -> bool:
    """A case passes only when every turn passes."""
    if not turn_passes:
        raise ValueError("turn_passes must not be empty")
    return all(turn_passes)

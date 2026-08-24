"""Deterministic quality and latency metrics for dialog evaluation."""

import math

from evaluation.intent_metrics import compute_latency_metrics


DIMENSIONS = ("relevance", "accuracy", "completeness", "helpfulness")


def compute_turn_scores(judge_scores):
    values = {name: float(judge_scores[name]) for name in DIMENSIONS}
    values["overall"] = round(math.fsum(values.values()) / len(DIMENSIONS), 12)
    return values


def aggregate_case_scores(turns):
    if not turns or any(t.get("agent_failed") or t.get("judge_failed") or t.get("judge_skipped") for t in turns):
        return None
    per_turn = [compute_turn_scores(t["judge"]) for t in turns]
    result = {name: round(math.fsum(t[name] for t in per_turn) / len(per_turn), 12) for name in DIMENSIONS}
    result["overall"] = round(math.fsum(result.values()) / len(DIMENSIONS), 12)
    return result


def compute_dialog_metrics(cases, pass_threshold=0.75):
    total = len(cases)
    valid = [c for c in cases if not c["agent_failed"] and not c["judge_failed"] and c.get("case_scores") is not None]
    result = {
        "total_cases": total,
        "valid_judged_cases": len(valid),
        "agent_failed_count": sum(bool(c["agent_failed"]) for c in cases),
        "judge_failed_count": sum(bool(c["judge_failed"]) for c in cases),
    }
    result["agent_failed_rate"] = result["agent_failed_count"] / total if total else 0.0
    result["judge_failed_rate"] = result["judge_failed_count"] / total if total else 0.0
    for name in DIMENSIONS + ("overall",):
        result[f"{name}_mean"] = sum(c["case_scores"][name] for c in valid) / len(valid) if valid else None
    result["pass_rate"] = sum(c["case_scores"]["overall"] >= pass_threshold for c in valid) / len(valid) if valid else None
    result["agent_latency"] = compute_latency_metrics([t["agent_latency_ms"] for c in cases for t in c["turns"] if t.get("agent_latency_ms") is not None])
    result["judge_latency"] = compute_latency_metrics([t["judge"]["latency_ms"] for c in cases for t in c["turns"] if t.get("judge") and t["judge"].get("latency_ms") is not None])
    return result

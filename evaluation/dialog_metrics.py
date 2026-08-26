"""Deterministic quality and latency metrics for dialog evaluation."""

import math

from evaluation.intent_metrics import compute_latency_metrics


DIMENSIONS = ("relevance", "accuracy", "completeness", "helpfulness")


def compute_turn_scores(judge_scores):
    values = {name: float(judge_scores[name]) for name in DIMENSIONS}
    values["overall"] = math.fsum(values.values()) / len(DIMENSIONS)
    return values


def aggregate_case_scores(turns):
    if not turns or any(t.get("agent_failed") or t.get("judge_failed") or t.get("judge_skipped") for t in turns):
        return None
    per_turn = [t["judge"]["final_scores"] for t in turns]
    result = {name: math.fsum(t[name] for t in per_turn) / len(per_turn) for name in DIMENSIONS}
    result["overall"] = math.fsum(result.values()) / len(DIMENSIONS)
    return result


def _latency_fields(prefix, latencies):
    summary = compute_latency_metrics(latencies)
    count = summary["count"]
    return {
        f"{prefix}_latency_count": count,
        f"{prefix}_latency_mean_ms": summary["mean_ms"] if count else None,
        f"{prefix}_latency_p50_ms": summary["p50_ms"] if count else None,
        f"{prefix}_latency_p95_ms": summary["p95_ms"] if count else None,
    }


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
    result.update(_latency_fields(
        "agent",
        [
            turn["agent_latency_ms"]
            for case in cases
            for turn in case["turns"]
            if turn.get("agent_latency_ms") is not None
        ],
    ))
    result.update(_latency_fields(
        "judge",
        [
            turn["judge"]["latency_ms"]
            for case in cases
            for turn in case["turns"]
            if turn.get("judge") and turn["judge"].get("latency_ms") is not None
        ],
    ))
    return result

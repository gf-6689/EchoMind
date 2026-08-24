import pytest

from evaluation.dialog_metrics import aggregate_case_scores, compute_dialog_metrics, compute_turn_scores


def test_turn_overall_is_unweighted_arithmetic_mean():
    result = compute_turn_scores({
        "relevance": 1.0,
        "accuracy": 0.8,
        "completeness": 0.6,
        "helpfulness": 0.4,
    })
    assert result["overall"] == 0.7


def test_case_scores_average_turns_before_overall():
    turns = [
        {"judge_failed": False, "judge": {"relevance": 1.0, "accuracy": 0.8, "completeness": 0.6, "helpfulness": 0.4}},
        {"judge_failed": False, "judge": {"relevance": 0.6, "accuracy": 0.4, "completeness": 0.2, "helpfulness": 0.0}},
    ]
    assert aggregate_case_scores(turns) == {
        "relevance": 0.8,
        "accuracy": pytest.approx(0.6),
        "completeness": 0.4,
        "helpfulness": 0.2,
        "overall": 0.5,
    }


def test_global_metrics_exclude_failed_cases_from_quality_only():
    cases = [
        {"agent_failed": False, "judge_failed": False, "case_scores": {"relevance": .8, "accuracy": .8, "completeness": .8, "helpfulness": .8, "overall": .8}, "turns": [{"agent_latency_ms": 10.0, "judge": {"latency_ms": 30.0}}]},
        {"agent_failed": False, "judge_failed": True, "case_scores": None, "turns": [{"agent_latency_ms": 20.0, "judge_failed": True, "judge": {"latency_ms": 90.0}}]},
        {"agent_failed": True, "judge_failed": False, "case_scores": None, "turns": [{"agent_latency_ms": 40.0, "judge_skipped": True, "judge": None}]},
    ]
    result = compute_dialog_metrics(cases)
    assert result["total_cases"] == 3
    assert result["valid_judged_cases"] == 1
    assert result["overall_mean"] == .8
    assert result["pass_rate"] == 1.0
    assert result["agent_failed_rate"] == 1 / 3
    assert result["judge_failed_rate"] == 1 / 3
    assert result["agent_latency"]["count"] == 3
    assert result["judge_latency"]["count"] == 2


def test_no_valid_judged_cases_returns_null_quality_metrics():
    result = compute_dialog_metrics([{"agent_failed": True, "judge_failed": False, "case_scores": None, "turns": []}])
    for key in ("relevance_mean", "accuracy_mean", "completeness_mean", "helpfulness_mean", "overall_mean", "pass_rate"):
        assert result[key] is None


def test_overall_below_threshold_is_not_rounded_up_or_passed():
    case_scores = aggregate_case_scores([{
        "judge_failed": False,
        "judge": {
            "relevance": 0.75,
            "accuracy": 0.75,
            "completeness": 0.75,
            "helpfulness": 0.7499999999998,
        },
    }])

    assert case_scores["overall"] < 0.75
    result = compute_dialog_metrics([{
        "agent_failed": False,
        "judge_failed": False,
        "case_scores": case_scores,
        "turns": [],
    }])
    assert result["pass_rate"] == 0.0

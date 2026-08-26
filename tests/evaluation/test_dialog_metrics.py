import pytest

from evaluation.dialog_metrics import aggregate_case_scores, compute_dialog_metrics, compute_turn_scores


def make_case(case_pass=True, *, valid=True, judge_failed=False, agent_failed=False, skipped=False, case_id="case-x"):
    return {
        "case_id": case_id,
        "agent_failed": agent_failed,
        "judge_failed": judge_failed,
        "judge_skipped": skipped,
        "case_pass": case_pass,
        "case_scores": {
            name: 0.8
            for name in ("relevance", "accuracy", "completeness", "helpfulness", "overall")
        } if valid else None,
        "turns": [{"agent_latency_ms": 10.0, "judge": {"latency_ms": 30.0}}],
    }


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
        {"judge_failed": False, "judge": {"final_scores": {"relevance": 1.0, "accuracy": 0.8, "completeness": 0.6, "helpfulness": 0.4, "overall": 0.7}}},
        {"judge_failed": False, "judge": {"final_scores": {"relevance": 0.6, "accuracy": 0.4, "completeness": 0.2, "helpfulness": 0.0, "overall": 0.3}}},
    ]
    assert aggregate_case_scores(turns) == {
        "relevance": 0.8,
        "accuracy": pytest.approx(0.6),
        "completeness": 0.4,
        "helpfulness": 0.2,
        "overall": 0.5,
    }


def test_pass_rate_uses_all_cases_not_only_valid_judged_cases():
    cases = [
        make_case(case_pass=True, case_id="a"),
        make_case(case_pass=True, case_id="b"),
        make_case(case_pass=False, valid=False, judge_failed=True, case_id="c"),
    ]
    metrics = compute_dialog_metrics(cases)
    assert metrics["passed_cases"] == 2
    assert metrics["total_cases"] == 3
    assert metrics["pass_rate"] == pytest.approx(2 / 3)


def test_failed_cases_enter_total_but_not_quality_mean():
    cases = [
        make_case(case_pass=True, case_id="a"),
        make_case(case_pass=True, case_id="b"),
        make_case(case_pass=False, valid=False, judge_failed=True, case_id="c"),
    ]
    metrics = compute_dialog_metrics(cases)
    assert metrics["total_cases"] == 3
    assert metrics["valid_judged_cases"] == 2
    assert metrics["judge_failed_count"] == 1
    assert metrics["relevance_mean"] == 0.8
    assert metrics["accuracy_mean"] == 0.8
    assert metrics["completeness_mean"] == 0.8
    assert metrics["helpfulness_mean"] == 0.8
    assert metrics["overall_mean"] == 0.8


def test_metrics_read_final_scores_not_base_scores():
    case = make_case(case_pass=True, case_id="capped")
    case["turns"][0]["judge"] = {
        "assessment": {
            "base_scores": {"relevance": 1.0, "accuracy": 1.0, "helpfulness": 1.0},
            "required_point_coverage": [],
            "violations": [],
            "reasoning_summary": "x",
        },
        "applied_caps": {"accuracy": 0.5},
        "final_scores": {
            "relevance": 1.0,
            "accuracy": 0.5,
            "completeness": 1.0,
            "helpfulness": 1.0,
            "overall": 0.875,
        },
        "latency_ms": 5.0,
    }
    case["case_scores"] = {
        "relevance": 1.0,
        "accuracy": 0.5,
        "completeness": 1.0,
        "helpfulness": 1.0,
        "overall": 0.875,
    }
    metrics = compute_dialog_metrics([case])
    assert metrics["accuracy_mean"] == 0.5


def test_metrics_keep_failure_audit_fields():
    metrics = compute_dialog_metrics([])

    assert set(metrics) == {
        "total_cases", "valid_judged_cases", "passed_cases",
        "relevance_mean", "accuracy_mean", "completeness_mean",
        "helpfulness_mean", "overall_mean", "pass_rate",
        "agent_failed_count", "agent_failed_rate",
        "judge_failed_count", "judge_failed_rate",
        "agent_latency_count", "agent_latency_mean_ms",
        "agent_latency_p50_ms", "agent_latency_p95_ms",
        "judge_latency_count", "judge_latency_mean_ms",
        "judge_latency_p50_ms", "judge_latency_p95_ms",
    }


def test_failed_case_has_false_case_pass_and_zero_pass_rate():
    cases = [
        make_case(case_pass=False, valid=False, agent_failed=True, case_id="agent-boom"),
    ]
    metrics = compute_dialog_metrics(cases)
    assert metrics["total_cases"] == 1
    assert metrics["passed_cases"] == 0
    assert metrics["pass_rate"] == 0.0
    assert metrics["valid_judged_cases"] == 0
    assert metrics["agent_failed_count"] == 1
    assert metrics["agent_failed_rate"] == 1.0
    assert metrics["overall_mean"] is None


def test_global_metrics_exclude_failed_cases_from_quality_only():
    cases = [
        make_case(case_pass=True, case_id="ok"),
        make_case(case_pass=False, valid=False, judge_failed=True, case_id="judge-boom"),
        make_case(case_pass=False, valid=False, agent_failed=True, case_id="agent-boom"),
    ]
    result = compute_dialog_metrics(cases)
    assert result["total_cases"] == 3
    assert result["valid_judged_cases"] == 1
    assert result["overall_mean"] == 0.8
    assert result["passed_cases"] == 1
    assert result["pass_rate"] == pytest.approx(1 / 3)
    assert result["agent_failed_rate"] == 1 / 3
    assert result["judge_failed_rate"] == 1 / 3
    assert result["agent_latency_count"] == 3
    assert result["agent_latency_mean_ms"] == 10.0
    assert result["judge_latency_count"] == 3
    assert result["judge_latency_mean_ms"] == 30.0


def test_skipped_case_enters_total_and_fails_pass_rate():
    cases = [
        make_case(case_pass=True, case_id="ok"),
        make_case(case_pass=False, valid=False, skipped=True, case_id="skipped"),
    ]
    result = compute_dialog_metrics(cases)
    assert result["total_cases"] == 2
    assert result["passed_cases"] == 1
    assert result["pass_rate"] == 0.5
    assert result["valid_judged_cases"] == 1


def test_no_calls_return_null_latency_statistics():
    result = compute_dialog_metrics([])

    assert result["agent_latency_count"] == 0
    assert result["judge_latency_count"] == 0
    for prefix in ("agent", "judge"):
        assert result[f"{prefix}_latency_mean_ms"] is None
        assert result[f"{prefix}_latency_p50_ms"] is None
        assert result[f"{prefix}_latency_p95_ms"] is None


def test_no_valid_judged_cases_returns_null_quality_metrics_but_zero_pass_rate():
    result = compute_dialog_metrics([
        make_case(case_pass=False, valid=False, agent_failed=True, case_id="boom"),
    ])
    for key in ("relevance_mean", "accuracy_mean", "completeness_mean", "helpfulness_mean", "overall_mean"):
        assert result[key] is None
    assert result["pass_rate"] == 0.0
    assert result["passed_cases"] == 0


def test_overall_below_threshold_is_not_rounded_up_or_passed():
    case_scores = aggregate_case_scores([{
        "judge_failed": False,
        "judge": {
            "final_scores": {
                "relevance": 0.75,
                "accuracy": 0.75,
                "completeness": 0.75,
                "helpfulness": 0.7499999999998,
                "overall": 0.75,
            },
        },
    }])

    assert case_scores["overall"] < 0.75
    result = compute_dialog_metrics([{
        "case_id": "low",
        "agent_failed": False,
        "judge_failed": False,
        "judge_skipped": False,
        "case_pass": False,
        "case_scores": case_scores,
        "turns": [],
    }])
    assert result["pass_rate"] == 0.0

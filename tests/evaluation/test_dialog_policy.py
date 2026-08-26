import pytest

from evaluation.dialog_policy import (
    compute_case_pass,
    compute_completeness,
    compute_strictest_caps,
    compute_turn_pass,
    score_assessment,
)


def test_compute_completeness_equal_weight():
    coverage = [
        {"point_index": 1, "status": "covered", "evidence": "a"},
        {"point_index": 2, "status": "partial", "evidence": "b"},
        {"point_index": 3, "status": "missing", "evidence": "c"},
    ]
    assert compute_completeness(coverage) == pytest.approx(0.5)


def test_compute_completeness_rejects_empty():
    with pytest.raises(ValueError):
        compute_completeness([])


def test_compute_completeness_maps_each_status_exactly():
    assert compute_completeness([{"status": "covered"}]) == 1.0
    assert compute_completeness([{"status": "partial"}]) == 0.5
    assert compute_completeness([{"status": "missing"}]) == 0.0
    assert compute_completeness([{"status": "covered"}, {"status": "partial"}, {"status": "covered"}]) == pytest.approx(5 / 6)


def test_compute_completeness_rejects_unknown_status():
    with pytest.raises(ValueError):
        compute_completeness([{"status": "almost"}])


def test_compute_completeness_does_not_round():
    assert compute_completeness([{"status": "partial"}]) == 0.5
    result = compute_completeness([{"status": "covered"}, {"status": "partial"}, {"status": "covered"}])
    assert result == pytest.approx(5 / 6)
    assert result != 0.83


def test_strictest_caps_are_order_independent():
    a = ["unsupported_operation", "sensitive_request_without_safety"]
    b = list(reversed(a))
    assert compute_strictest_caps(a) == compute_strictest_caps(b)
    assert compute_strictest_caps(a) == {
        "accuracy": 0.75,
        "helpfulness": 0.50,
    }


def test_strictest_caps_rejects_unknown_code():
    with pytest.raises(ValueError):
        compute_strictest_caps(["not_a_violation_code"])


def test_strictest_caps_returns_empty_dict_without_violations():
    assert compute_strictest_caps([]) == {}


def test_strictest_caps_only_keeps_below_one():
    assert compute_strictest_caps(["unsupported_process_or_requirement"]) == {"accuracy": 0.75}
    assert compute_strictest_caps(["severe_readability_defect"]) == {"helpfulness": 0.75}
    assert compute_strictest_caps(["misleading_unsupported_content"]) == {"helpfulness": 0.85}


def _assessment(*, base=None, coverage=None, violations=None):
    return {
        "base_scores": base if base is not None else {"relevance": 1.0, "accuracy": 1.0, "helpfulness": 1.0},
        "required_point_coverage": coverage if coverage is not None else [{"point_index": 1, "status": "covered", "evidence": "ok"}],
        "violations": violations if violations is not None else [],
        "reasoning_summary": "clean turn",
    }


def test_score_assessment_applies_single_cap():
    result = score_assessment(_assessment(violations=[{"code": "unsupported_operation", "evidence": ["e"]}]))
    assert result["applied_caps"] == {"accuracy": 0.75, "helpfulness": 0.75}
    assert result["final_scores"] == {
        "relevance": 1.0,
        "accuracy": 0.75,
        "completeness": 1.0,
        "helpfulness": 0.75,
        "overall": 0.875,
    }


def test_score_assessment_applies_strictest_cap_per_dimension():
    result = score_assessment(_assessment(violations=[
        {"code": "unsupported_operation", "evidence": ["a"]},
        {"code": "false_completed_action", "evidence": ["b"]},
    ]))
    assert result["applied_caps"] == {"accuracy": 0.50, "helpfulness": 0.50}
    assert result["final_scores"]["accuracy"] == 0.50
    assert result["final_scores"]["helpfulness"] == 0.50


def test_score_assessment_violation_order_does_not_change_scores():
    violations = [
        {"code": "sensitive_request_without_safety", "evidence": ["a"]},
        {"code": "unsupported_operation", "evidence": ["b"]},
    ]
    forward = score_assessment(_assessment(violations=violations))
    backward = score_assessment(_assessment(violations=list(reversed(violations))))
    assert forward == backward
    assert forward["applied_caps"] == {"accuracy": 0.75, "helpfulness": 0.50}


def test_score_assessment_caps_only_lower_scores():
    base = {"relevance": 0.9, "accuracy": 0.6, "helpfulness": 0.4}
    result = score_assessment(_assessment(base=base, violations=[{"code": "unsupported_operation", "evidence": ["e"]}]))
    assert result["final_scores"]["accuracy"] == 0.6
    assert result["final_scores"]["helpfulness"] == 0.4
    assert result["final_scores"]["relevance"] == 0.9


def test_score_assessment_final_overall_is_unrounded_mean_of_final_dimensions():
    result = score_assessment(_assessment(
        base={"relevance": 0.9, "accuracy": 0.8, "helpfulness": 0.9},
        coverage=[
            {"point_index": 1, "status": "covered", "evidence": "a"},
            {"point_index": 2, "status": "missing", "evidence": "b"},
        ],
        violations=[{"code": "context_contradiction", "evidence": ["e"]}],
    ))
    expected = {
        "relevance": 0.9,
        "accuracy": 0.5,
        "completeness": 0.5,
        "helpfulness": 0.9,
    }
    expected["overall"] = sum(expected.values()) / 4
    assert result["final_scores"] == expected
    assert result["applied_caps"] == {"accuracy": 0.5}


def test_score_assessment_empty_coverage_raises():
    with pytest.raises(ValueError):
        score_assessment(_assessment(coverage=[]))


def test_score_assessment_unknown_violation_raises():
    with pytest.raises(ValueError):
        score_assessment(_assessment(violations=[{"code": "unknown", "evidence": ["e"]}]))


def test_score_assessment_returns_only_applied_caps_and_final_scores():
    result = score_assessment(_assessment())
    assert set(result) == {"applied_caps", "final_scores"}
    assert result["applied_caps"] == {}
    assert set(result["final_scores"]) == {"relevance", "accuracy", "completeness", "helpfulness", "overall"}


def _scores(**overrides):
    scores = {
        "relevance": 0.8,
        "accuracy": 0.8,
        "completeness": 0.8,
        "helpfulness": 0.8,
        "overall": 0.8,
    }
    scores.update(overrides)
    return scores


def test_turn_fails_when_one_dimension_below_floor_even_if_overall_passes():
    scores = {
        "relevance": 1.0,
        "accuracy": 0.5,
        "completeness": 1.0,
        "helpfulness": 1.0,
        "overall": 0.875,
    }
    assert compute_turn_pass(
        scores,
        agent_failed=False,
        judge_failed=False,
        judge_skipped=False,
    ) is False


def test_turn_passes_when_all_dimensions_and_overall_meet_thresholds():
    scores = {
        "relevance": 0.75,
        "accuracy": 0.75,
        "completeness": 0.75,
        "helpfulness": 0.75,
        "overall": 0.75,
    }
    assert compute_turn_pass(
        scores,
        agent_failed=False,
        judge_failed=False,
        judge_skipped=False,
    ) is True


def test_turn_fails_on_agent_failed():
    assert compute_turn_pass(_scores(), agent_failed=True, judge_failed=False, judge_skipped=False) is False


def test_turn_fails_on_judge_failed():
    assert compute_turn_pass(_scores(), agent_failed=False, judge_failed=True, judge_skipped=False) is False


def test_turn_fails_on_judge_skipped():
    assert compute_turn_pass(_scores(), agent_failed=False, judge_failed=False, judge_skipped=True) is False


def test_turn_fails_when_overall_below_threshold():
    assert compute_turn_pass(
        _scores(overall=0.7499999999999),
        agent_failed=False,
        judge_failed=False,
        judge_skipped=False,
    ) is False


def test_turn_boundary_floats_not_rounded_up():
    scores = {
        "relevance": 0.75,
        "accuracy": 0.75,
        "completeness": 0.75,
        "helpfulness": 0.7499999999998,
        "overall": 0.75,
    }
    assert compute_turn_pass(
        scores,
        agent_failed=False,
        judge_failed=False,
        judge_skipped=False,
    ) is False


def test_case_pass_is_all_turns():
    assert compute_case_pass([True, False, True]) is False
    assert compute_case_pass([True, True]) is True


def test_case_pass_empty_raises():
    with pytest.raises(ValueError):
        compute_case_pass([])


def test_failure_flags_make_case_pass_false_via_turn_passes():
    assert compute_case_pass([
        compute_turn_pass(_scores(), agent_failed=False, judge_failed=False, judge_skipped=False),
        compute_turn_pass(_scores(), agent_failed=True, judge_failed=False, judge_skipped=False),
    ]) is False

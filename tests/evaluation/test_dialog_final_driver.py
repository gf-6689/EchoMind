"""Offline tests for the one-time Judge v5 formal driver.

Every dependency is fake: no network, no API key, no real run
directories, and no writes outside ``tmp_path``.  These tests freeze the
orchestration contract of ``data/eval/runs/run_dialog_eval_v5_final.py``:

1. warm-up failure -> the formal phase never starts;
2. identity failure  -> zero API calls and no directories;
3. formal dir exists -> immediate stop;
4. warm-up dir exists -> immediate stop;
5. formal phase only starts after the warm-up hard gate passes.
"""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

DRIVER_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "eval"
    / "runs"
    / "run_dialog_eval_v5_final.py"
)
_spec = importlib.util.spec_from_file_location("run_dialog_eval_v5_final", DRIVER_PATH)
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)

from evaluation.dialog_metrics import aggregate_case_scores, compute_dialog_metrics
from evaluation.dialog_policy import compute_case_pass, compute_turn_pass, score_assessment


def _assessment(point_count=1):
    return {
        "base_scores": {"relevance": 1.0, "accuracy": 1.0, "helpfulness": 1.0},
        "required_point_coverage": [
            {"point_index": index, "status": "covered", "evidence": f"covers point {index}"}
            for index in range(1, point_count + 1)
        ],
        "violations": [],
        "reasoning_summary": "response covers every required point",
    }


def _turn(point_count=1):
    assessment = _assessment(point_count)
    scored = score_assessment(assessment)
    return {
        "turn_id": 1,
        "user_message": "q",
        "agent_response": "ok",
        "agent_latency_ms": 1.0,
        "agent_failed": False,
        "agent_error": None,
        "judge_failed": False,
        "judge_error": None,
        "judge_skipped": False,
        "judge_attempts": 1,
        "judge": {
            "assessment": assessment,
            "applied_caps": scored["applied_caps"],
            "final_scores": scored["final_scores"],
            "latency_ms": 1.0,
        },
        "turn_pass": compute_turn_pass(
            scored["final_scores"],
            agent_failed=False,
            judge_failed=False,
            judge_skipped=False,
        ),
    }


def _row(case_id, turn_count, fail_judge_turn=None):
    turns = []
    for index in range(1, turn_count + 1):
        turn = _turn()
        turn["turn_id"] = index
        if index == fail_judge_turn:
            turn["judge_failed"] = True
            turn["judge_error"] = "simulated judge failure"
            turn["judge_attempts"] = 3
            turn["judge"] = {"latency_ms": 1.0}
            turn["turn_pass"] = False
        turns.append(turn)
    case_pass = compute_case_pass([turn["turn_pass"] for turn in turns])
    return {
        "case_id": case_id,
        "category": "test",
        "description": "offline fake case",
        "turns": turns,
        "agent_failed": any(turn["agent_failed"] for turn in turns),
        "judge_failed": any(
            turn["judge_failed"] for turn in turns if not turn["judge_skipped"]
        ),
        "judge_skipped": any(turn["judge_skipped"] for turn in turns),
        "case_scores": aggregate_case_scores(turns),
        "case_pass": case_pass,
        "passed": case_pass,
        "routing_audit": {"intent_match": True, "agent_match": True},
    }


def _fake_cases():
    """35 cases / 43 turns matching the frozen dataset shape."""
    turn_counts = [1] * 35
    turn_counts[25] = 3
    turn_counts[26] = 2
    turn_counts[27] = 3
    turn_counts[28] = 2
    turn_counts[29] = 3
    return [
        {
            "case_id": driver.EXPECTED_CASE_IDS[index],
            "turns": [{"required_points": ["p"]}] * turn_counts[index],
        }
        for index in range(35)
    ]


def _identity(revision="test-revision"):
    return {
        "recorded_at": "2026-08-26T00:00:00Z",
        "git_revision": revision,
        "driver_sha256": "test-driver-sha",
        "dataset_path": "test-dataset-path",
        "dataset_sha256": driver.EXPECTED_DATASET_SHA256,
        "expected_cases": 35,
        "expected_turns": 43,
        "agent_model": "deepseek-v4-pro",
        "judge_model": "deepseek-v4-pro",
        "prompt_version": driver.PROMPT_VERSION,
        "judge_output_strategy": driver.JUDGE_OUTPUT_STRATEGY,
        "pass_rule_version": driver.PASS_RULE_VERSION,
        "dimension_pass_floor": driver.DIMENSION_PASS_FLOOR,
        "overall_pass_threshold": driver.OVERALL_PASS_THRESHOLD,
        "completeness_policy": driver.COMPLETENESS_POLICY_VERSION,
        "violation_policy_version": driver.VIOLATION_POLICY_VERSION,
    }


def _config():
    return {
        "api_key": "test-key",
        "base_url": "http://test.invalid",
        "agent_model": "deepseek-v4-pro",
        "judge_model": "deepseek-v4-pro",
    }


class FakeClient:
    def __init__(self):
        self.api_calls = 0


class FakeDepsFactory:
    def __init__(self):
        self.called = 0
        self.client = FakeClient()

    def __call__(self):
        self.called += 1
        return (object(), object())


def _write_artifacts(directory, rows, *, revision):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "dialog_predictions.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics = compute_dialog_metrics(rows)
    (directory / "dialog_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "dataset_path": "test-dataset-path",
        "dataset_sha256": driver.EXPECTED_DATASET_SHA256,
        "case_count": len(rows),
        "git_revision": revision,
        "agent_model": "deepseek-v4-pro",
        "judge_model": "deepseek-v4-pro",
        "prompt_version": "dialog_judge_v5",
        "temperature": 0.0,
        "pass_threshold": 0.75,
        "pass_rule_version": "dialog_pass_v5",
        "dimension_pass_floor": 0.75,
        "overall_pass_threshold": 0.75,
        "completeness_policy": "required_point_coverage_equal_weight_v1",
        "violation_policy_version": "dialog_violation_caps_v1",
        "timeout": 30.0,
        "max_attempts": 3,
        "context_mode": "controlled_context",
        "judge_output_strategy": "forced_tool_then_strict_json_fallback",
        "retrieval_evaluated": False,
    }
    (directory / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class FakeRunner:
    """Writes a plausible artifact set per phase and records call order."""

    def __init__(self, *, revision="test-revision", warmup_judge_failed=False):
        self.revision = revision
        self.warmup_judge_failed = warmup_judge_failed
        self.calls = []
        self.identity_existed_before_formal = None

    async def __call__(self, dependencies, cases, output_dir):
        self.calls.append([case["case_id"] for case in cases])
        if len(cases) > 1 and self.identity_existed_before_formal is None:
            warmup_dir = output_dir.parent / "warmup"
            self.identity_existed_before_formal = (
                warmup_dir / "formal_model_identity.json"
            ).is_file()
        if len(cases) == 1:
            failed = 1 if self.warmup_judge_failed else None
            rows = [
                _row(cases[0]["case_id"], len(cases[0]["turns"]), fail_judge_turn=failed)
            ]
        else:
            rows = [_row(case["case_id"], len(case["turns"])) for case in cases]
        _write_artifacts(output_dir, rows, revision=self.revision)


def _run(coro):
    return asyncio.run(coro)


def _invoke(tmp_path, *, config=None, identity=None, factory=None, runner=None):
    return _run(
        driver.run_final(
            cases=_fake_cases(),
            warmup_dir=tmp_path / "warmup",
            formal_dir=tmp_path / "formal",
            dataset_sha256=driver.EXPECTED_DATASET_SHA256,
            config=config or _config(),
            identity=identity or _identity(),
            create_dependencies=factory or FakeDepsFactory(),
            run_phase=runner or FakeRunner(),
        )
    )


def test_warmup_failure_never_starts_formal_run(tmp_path):
    factory = FakeDepsFactory()
    runner = FakeRunner(warmup_judge_failed=True)
    with pytest.raises(RuntimeError):
        _invoke(tmp_path, factory=factory, runner=runner)
    assert factory.called == 1
    assert len(runner.calls) == 1
    assert runner.calls[0] == [driver.EXPECTED_CASE_IDS[0]]
    assert not (tmp_path / "formal").exists()
    assert (tmp_path / "warmup" / "dialog_predictions.jsonl").is_file()
    assert not (tmp_path / "warmup" / "formal_model_identity.json").exists()


def test_identity_failure_makes_zero_api_calls(tmp_path):
    factory = FakeDepsFactory()
    runner = FakeRunner()
    with pytest.raises(RuntimeError):
        _invoke(tmp_path, config=dict(_config(), agent_model="other-model"), factory=factory, runner=runner)
    assert factory.called == 0
    assert factory.client.api_calls == 0
    assert runner.calls == []
    assert not (tmp_path / "warmup").exists()
    assert not (tmp_path / "formal").exists()


def test_formal_dir_exists_stops_immediately(tmp_path):
    factory = FakeDepsFactory()
    (tmp_path / "formal").mkdir()
    with pytest.raises(FileExistsError):
        _invoke(tmp_path, factory=factory)
    assert factory.called == 0
    assert not (tmp_path / "warmup").exists()


def test_warmup_dir_exists_stops_immediately(tmp_path):
    factory = FakeDepsFactory()
    (tmp_path / "warmup").mkdir()
    with pytest.raises(FileExistsError):
        _invoke(tmp_path, factory=factory)
    assert factory.called == 0
    assert not (tmp_path / "formal").exists()


def test_formal_phase_runs_only_after_warmup_gate(tmp_path):
    factory = FakeDepsFactory()
    runner = FakeRunner()
    evidence = _invoke(tmp_path, factory=factory, runner=runner)
    assert factory.called == 1
    assert runner.calls == [
        [driver.EXPECTED_CASE_IDS[0]],
        driver.EXPECTED_CASE_IDS,
    ]
    assert runner.identity_existed_before_formal is True
    assert (tmp_path / "warmup" / "formal_model_identity.json").is_file()
    assert (tmp_path / "formal" / "dialog_predictions.jsonl").is_file()
    assert evidence["total_cases"] == 35
    assert evidence["total_turns"] == 43
    assert evidence["pass_rate"] == 1.0
    assert evidence["intent_routing_exact_match"] == 35
    assert evidence["agent_routing_exact_match"] == 35
    assert evidence["known_judge_semantic_variance"] == [
        "dialog_eval_024/T1",
        "dialog_eval_028/T2",
    ]

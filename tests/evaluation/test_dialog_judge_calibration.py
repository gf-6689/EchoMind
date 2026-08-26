import asyncio
import builtins
import json
from pathlib import Path

import pytest

from evaluation.run_dialog_judge_calibration import (
    CALIBRATION_CASE_IDS,
    EXPECTED_CASE_PASS,
    TURN_ORACLE,
    load_calibration_inputs,
    run_calibration,
)

TURN_COUNTS = {
    "dialog_eval_001": [1],
    "dialog_eval_018": [3],
    "dialog_eval_019": [3],
    "dialog_eval_024": [3],
    "dialog_eval_025": [3],
    "dialog_eval_026": [2, 2, 2],
    "dialog_eval_028": [2, 2, 2],
    "dialog_eval_031": [4],
    "dialog_eval_033": [3],
    "dialog_eval_034": [3],
}


def make_dataset():
    cases = []
    for cid in CALIBRATION_CASE_IDS:
        cases.append({
            "case_id": cid,
            "category": "faq",
            "description": f"case {cid}",
            "context": f"controlled context for {cid}",
            "turns": [
                {
                    "user_message": f"q{turn_index}",
                    "reference_answer": f"ref{turn_index}",
                    "required_points": [f"p{point}" for point in range(1, count + 1)],
                }
                for turn_index, count in enumerate(TURN_COUNTS[cid], 1)
            ],
            "expected_routing": {"intent": "query", "agent_type": "general"},
        })
    return cases


def make_predictions():
    rows = []
    for cid in CALIBRATION_CASE_IDS:
        rows.append({
            "case_id": cid,
            "turns": [
                {"turn_id": turn_index, "agent_response": f"frozen answer {cid} turn {turn_index}"}
                for turn_index in range(1, len(TURN_COUNTS[cid]) + 1)
            ],
        })
    return rows


def make_metadata():
    return {
        "agent_model": "deepseek-v4-pro",
        "judge_model": "deepseek-v4-pro",
        "prompt_version": "dialog_judge_v4",
    }


def write_inputs(tmp_path):
    dataset_path = tmp_path / "dialog.json"
    dataset_path.write_text(json.dumps(make_dataset()), encoding="utf-8")
    predictions_path = tmp_path / "predictions.jsonl"
    predictions_path.write_text(
        "\n".join(json.dumps(row) for row in make_predictions()) + "\n",
        encoding="utf-8",
    )
    metadata_path = tmp_path / "run_metadata.json"
    metadata_path.write_text(json.dumps(make_metadata()), encoding="utf-8")
    return dataset_path, predictions_path, metadata_path


def ordered_oracle_entries():
    entries = []
    for cid in CALIBRATION_CASE_IDS:
        for turn_index in range(1, len(TURN_COUNTS[cid]) + 1):
            entries.append((cid, turn_index, TURN_ORACLE[(cid, turn_index)]))
    return entries


class OracleFakeJudge:
    """Return oracle-satisfying v5 assessments in case/turn order."""

    def __init__(self):
        self.calls = []

    def _assessment(self, call_index, **overrides):
        _, _, oracle = ordered_oracle_entries()[call_index - 1]
        coverage = [
            {"point_index": index + 1, "status": status, "evidence": f"e{index + 1}"}
            for index, status in enumerate(oracle["coverage"])
        ]
        violations = [
            {"code": code, "evidence": [f"ev-{code}"]}
            for code in oracle.get("required_violations", [])
        ]
        assessment = {
            "base_scores": {"relevance": 1.0, "accuracy": 1.0, "helpfulness": 1.0},
            "required_point_coverage": coverage,
            "violations": violations,
            "reasoning_summary": "semantic facts only",
        }
        assessment.update(overrides)
        return assessment

    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": {
                "assessment": self._assessment(len(self.calls)),
                "latency_ms": 1.0,
            },
        }


def run_offline(tmp_path, judge):
    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    cases, predictions, metadata, dataset_sha, predictions_sha = load_calibration_inputs(
        dataset_path, predictions_path, metadata_path
    )
    output_dir = tmp_path / "out"
    summary = asyncio.run(run_calibration(
        cases=cases,
        predictions=predictions,
        metadata=metadata,
        judge=judge,
        output_dir=output_dir,
        dataset_sha256=dataset_sha,
        predictions_sha256=predictions_sha,
        git_revision="test-revision",
    ))
    return summary, output_dir


def test_oracle_covers_ten_cases_and_fourteen_turns():
    assert len(CALIBRATION_CASE_IDS) == 10
    assert len(TURN_ORACLE) == 14
    assert sum(len(TURN_COUNTS[cid]) for cid in CALIBRATION_CASE_IDS) == 14
    assert EXPECTED_CASE_PASS == {
        "dialog_eval_001": False,
        "dialog_eval_018": False,
        "dialog_eval_019": False,
        "dialog_eval_024": False,
        "dialog_eval_025": False,
        "dialog_eval_026": False,
        "dialog_eval_028": True,
        "dialog_eval_031": False,
        "dialog_eval_033": False,
        "dialog_eval_034": True,
    }


def test_offline_calibration_passes_with_oracle_fake_judge(tmp_path):
    judge = OracleFakeJudge()
    summary, output_dir = run_offline(tmp_path, judge)

    assert summary["calibration_passed"] is True
    assert summary["case_count"] == 10
    assert summary["turn_count"] == 14
    assert summary["agent_api_calls"] == 0
    assert summary["judge_api_calls"] == 14
    assert summary["judge_failed_count"] == 0
    assert summary["oracle_failed_turns"] == 0
    assert summary["manual_review_failed_turns"] == 0
    assert summary["case_pass"] == EXPECTED_CASE_PASS
    assert summary["case_pass_match"] is True
    assert len(judge.calls) == 14

    assert (output_dir / "run_metadata.json").exists()
    assert (output_dir / "calibration_results.jsonl").exists()
    assert (output_dir / "calibration_summary.json").exists()
    rows = [
        json.loads(line)
        for line in (output_dir / "calibration_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["case_id"] for row in rows] == CALIBRATION_CASE_IDS
    assert all(row["oracle_match"] for row in rows)

    metadata = json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["judge_model"] == "deepseek-v4-pro"
    assert metadata["prompt_version"] == "dialog_judge_v5"
    assert metadata["judge_output_strategy"] == "forced_tool_then_strict_json_fallback"
    assert metadata["pass_rule_version"] == "dialog_pass_v5"
    assert metadata["dimension_pass_floor"] == 0.75
    assert metadata["overall_pass_threshold"] == 0.75
    assert metadata["completeness_policy"] == "required_point_coverage_equal_weight_v1"
    assert metadata["violation_policy_version"] == "dialog_violation_caps_v1"
    assert metadata["agent_api_calls"] == 0
    assert metadata["case_count"] == 10
    assert metadata["turn_count"] == 14


def test_calibration_never_imports_agent_orchestrator(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "agents.agent_orchestrator" or name.startswith("agents.agent_orchestrator."):
            raise AssertionError("calibration must never import AgentOrchestrator")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    summary, _ = run_offline(tmp_path, OracleFakeJudge())

    assert summary["agent_api_calls"] == 0
    assert summary["calibration_passed"] is True


def test_existing_output_dir_fails_immediately(tmp_path):
    judge = OracleFakeJudge()
    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    cases, predictions, metadata, dataset_sha, predictions_sha = load_calibration_inputs(
        dataset_path, predictions_path, metadata_path
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    with pytest.raises(FileExistsError):
        asyncio.run(run_calibration(
            cases=cases,
            predictions=predictions,
            metadata=metadata,
            judge=judge,
            output_dir=output_dir,
            dataset_sha256=dataset_sha,
            predictions_sha256=predictions_sha,
            git_revision="test-revision",
        ))
    assert judge.calls == []


def test_missing_calibration_case_fails(tmp_path):
    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    cases, predictions, metadata, dataset_sha, predictions_sha = load_calibration_inputs(
        dataset_path, predictions_path, metadata_path
    )
    cases = [case for case in cases if case["case_id"] != "dialog_eval_034"]

    with pytest.raises(ValueError, match="missing"):
        asyncio.run(run_calibration(
            cases=cases,
            predictions=predictions,
            metadata=metadata,
            judge=OracleFakeJudge(),
            output_dir=tmp_path / "out",
            dataset_sha256=dataset_sha,
            predictions_sha256=predictions_sha,
            git_revision="test-revision",
        ))


def test_wrong_judge_model_fails(tmp_path):
    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    cases, predictions, metadata, dataset_sha, predictions_sha = load_calibration_inputs(
        dataset_path, predictions_path, metadata_path
    )
    metadata["judge_model"] = "some-other-model"

    with pytest.raises(ValueError, match="deepseek-v4-pro"):
        asyncio.run(run_calibration(
            cases=cases,
            predictions=predictions,
            metadata=metadata,
            judge=OracleFakeJudge(),
            output_dir=tmp_path / "out",
            dataset_sha256=dataset_sha,
            predictions_sha256=predictions_sha,
            git_revision="test-revision",
        ))


def test_missing_prediction_response_fails(tmp_path):
    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    cases, predictions, metadata, dataset_sha, predictions_sha = load_calibration_inputs(
        dataset_path, predictions_path, metadata_path
    )
    predictions = [row for row in predictions if row["case_id"] != "dialog_eval_026"]

    with pytest.raises(ValueError, match="predictions"):
        asyncio.run(run_calibration(
            cases=cases,
            predictions=predictions,
            metadata=metadata,
            judge=OracleFakeJudge(),
            output_dir=tmp_path / "out",
            dataset_sha256=dataset_sha,
            predictions_sha256=predictions_sha,
            git_revision="test-revision",
        ))


class ExtraViolationJudge(OracleFakeJudge):
    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        assessment = self._assessment(len(self.calls))
        assessment["violations"] = [
            {"code": "context_contradiction", "evidence": ["extra"]},
            *assessment["violations"],
        ]
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": {"assessment": assessment, "latency_ms": 1.0},
        }


def test_extra_violation_fails_closed(tmp_path):
    summary, output_dir = run_offline(tmp_path, ExtraViolationJudge())

    assert summary["calibration_passed"] is False
    assert summary["oracle_failed_turns"] == 14
    assert "unexpected extra violations" in summary["failures"][0]
    assert (output_dir / "calibration_summary.json").exists()


class ExactMissJudge(OracleFakeJudge):
    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        assessment = self._assessment(len(self.calls))
        if len(self.calls) == 6:  # 026/T1
            assessment["base_scores"]["accuracy"] = 0.7
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": {"assessment": assessment, "latency_ms": 1.0},
        }


def test_final_exact_mismatch_fails_calibration(tmp_path):
    summary, output_dir = run_offline(tmp_path, ExactMissJudge())

    assert summary["calibration_passed"] is False
    assert summary["oracle_failed_turns"] >= 1
    assert any("final_accuracy" in failure for failure in summary["failures"])
    assert output_dir.exists()


class CasePassMissJudge(OracleFakeJudge):
    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        assessment = self._assessment(len(self.calls))
        if len(self.calls) == 9:  # 028/T1
            assessment["required_point_coverage"] = [
                {"point_index": 1, "status": "missing", "evidence": "omitted"},
                {"point_index": 2, "status": "missing", "evidence": "omitted"},
            ]
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": {"assessment": assessment, "latency_ms": 1.0},
        }


def test_case_pass_mismatch_fails_calibration(tmp_path):
    summary, _ = run_offline(tmp_path, CasePassMissJudge())

    assert summary["calibration_passed"] is False
    assert summary["case_pass"]["dialog_eval_028"] is False
    assert summary["case_pass_match"] is False


class ConflictReasoningJudge(OracleFakeJudge):
    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        assessment = self._assessment(len(self.calls))
        assessment["reasoning_summary"] = "the overall score is 0.75 and the final score is capped"
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": {"assessment": assessment, "latency_ms": 1.0},
        }


def test_reasoning_conflict_sets_manual_review_failed(tmp_path):
    summary, output_dir = run_offline(tmp_path, ConflictReasoningJudge())

    assert summary["manual_review_failed_turns"] == 14
    assert summary["calibration_passed"] is False
    rows = [
        json.loads(line)
        for line in (output_dir / "calibration_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(any(turn["reasoning_conflict"] for turn in row["turns"]) for row in rows)


def test_python_recompute_verification_catches_drift(tmp_path, monkeypatch):
    from evaluation import run_dialog_judge_calibration as module

    real_score = module.score_assessment
    calls = {"count": 0}

    def drift_score(assessment):
        calls["count"] += 1
        result = real_score(assessment)
        if calls["count"] % 2 == 0:  # verification call
            result = json.loads(json.dumps(result))
            result["final_scores"]["accuracy"] = 0.7
        return result

    monkeypatch.setattr(module, "score_assessment", drift_score)
    summary, _ = run_offline(tmp_path, OracleFakeJudge())

    assert summary["calibration_passed"] is False
    assert any("recompute" in failure or "final_scores" in failure for failure in summary["failures"])


class FailingJudge:
    async def judge_turn(self, **kwargs):
        return {
            "judge_failed": True,
            "judge_error": "judge API-key=secret failure",
            "judge_skipped": False,
            "judge_attempts": 3,
            "judge": {"latency_ms": 1.0},
        }


def test_judge_failure_is_recorded_and_fails_calibration(tmp_path):
    summary, output_dir = run_offline(tmp_path, FailingJudge())

    assert summary["judge_failed_count"] == 14
    assert summary["oracle_failed_turns"] == 14
    assert summary["calibration_passed"] is False
    assert all("secret" not in failure for failure in summary["failures"])


def test_main_returns_nonzero_on_failed_calibration_and_zero_on_success(tmp_path, monkeypatch):
    from evaluation import run_dialog_judge_calibration as module

    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    # Never load the real .env inside the test process; it would leak
    # environment variables into other tests in the same session.
    monkeypatch.setattr(module, "_load_environment", lambda: None)

    def fake_create_judge(judge_model):
        return ExactMissJudge(), ()

    monkeypatch.setattr(module, "_create_judge", fake_create_judge)
    output_dir = tmp_path / "out-fail"
    assert module.main([
        "--dialog-data", str(dataset_path),
        "--source-predictions", str(predictions_path),
        "--source-metadata", str(metadata_path),
        "--output-dir", str(output_dir),
    ]) == 1
    assert (output_dir / "calibration_summary.json").exists()

    def fake_create_judge_ok(judge_model):
        return OracleFakeJudge(), ()

    monkeypatch.setattr(module, "_create_judge", fake_create_judge_ok)
    output_dir_ok = tmp_path / "out-ok"
    assert module.main([
        "--dialog-data", str(dataset_path),
        "--source-predictions", str(predictions_path),
        "--source-metadata", str(metadata_path),
        "--output-dir", str(output_dir_ok),
    ]) == 0
    summary = json.loads((output_dir_ok / "calibration_summary.json").read_text(encoding="utf-8"))
    assert summary["calibration_passed"] is True


def test_parser_rejects_api_key_argument():
    from evaluation.run_dialog_judge_calibration import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "--dialog-data", "x",
            "--source-predictions", "y",
            "--source-metadata", "z",
            "--output-dir", "w",
            "--api-key", "secret",
        ])


def test_metadata_hashes_match_source_files(tmp_path):
    import hashlib

    dataset_path, predictions_path, metadata_path = write_inputs(tmp_path)
    _, _, _, dataset_sha, predictions_sha = load_calibration_inputs(
        dataset_path, predictions_path, metadata_path
    )
    assert dataset_sha == hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    assert predictions_sha == hashlib.sha256(predictions_path.read_bytes()).hexdigest()


def test_results_jsonl_records_full_v5_layers(tmp_path):
    _, output_dir = run_offline(tmp_path, OracleFakeJudge())

    rows = [
        json.loads(line)
        for line in (output_dir / "calibration_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    turn = rows[0]["turns"][0]
    assert set(turn) == {
        "turn_id", "judge_attempts", "judge_failed", "judge_error",
        "assessment", "applied_caps", "final_scores", "turn_pass",
        "oracle", "oracle_failures", "oracle_match", "reasoning_conflict",
    }
    assert set(turn["assessment"]) == {"base_scores", "required_point_coverage", "violations", "reasoning_summary"}
    assert "final_scores" not in turn["assessment"]
    assert turn["final_scores"]["completeness"] == 0.5
    assert turn["turn_pass"] is False

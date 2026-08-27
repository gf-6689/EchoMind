"""Deterministic dialog baseline/regression module tests.

Tests use only tmp_path fixtures and fake JSON artifacts; they never
read or write the real formal evaluation directories and never touch
.test-tmp/ or .pytest_cache/.
"""

import hashlib
import json

import pytest

from evaluation import regression


DEFAULT_DATASET_SHA256 = "cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2"
DEFAULT_JUDGE_MODEL = "deepseek-v4-pro"
DEFAULT_PROMPT_VERSION = "dialog_judge_v5"
DEFAULT_PASS_RULE_VERSION = "dialog_pass_v5"
DEFAULT_GIT_REVISION = "127ac799af2c16e3632580b846f153f4c1de382d"


def _sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fake_metrics(
    path,
    total_cases=35,
    passed_cases=24,
    overall_mean=0.9232142857142858,
    pass_rate=0.6857142857142857,
    agent_failed_rate=0.0,
    judge_failed_rate=0.0,
):
    payload = {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "overall_mean": overall_mean,
        "pass_rate": pass_rate,
        "agent_failed_rate": agent_failed_rate,
        "judge_failed_rate": judge_failed_rate,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")


def _write_fake_metadata(
    path,
    dataset_sha256=DEFAULT_DATASET_SHA256,
    judge_model=DEFAULT_JUDGE_MODEL,
    prompt_version=DEFAULT_PROMPT_VERSION,
    pass_rule_version=DEFAULT_PASS_RULE_VERSION,
    git_revision=DEFAULT_GIT_REVISION,
    case_count=35,
):
    payload = {
        "git_revision": git_revision,
        "dataset_sha256": dataset_sha256,
        "judge_model": judge_model,
        "prompt_version": prompt_version,
        "pass_rule_version": pass_rule_version,
        "case_count": case_count,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")


def _write_fake_predictions(path, total_cases, passed_cases):
    lines = [
        json.dumps({"case_id": f"case-{index:03d}", "case_pass": index < passed_cases}, ensure_ascii=False)
        for index in range(total_cases)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _write_fake_adjudication(
    path,
    adjudicated_pass_rate=0.6285714285714286,
    reviewed_cases=27,
    inherited_cases=8,
    total_cases=35,
    machine_pass_rate=0.6857142857142857,
):
    payload = {
        "total_cases": total_cases,
        "reviewed_cases": reviewed_cases,
        "inherited_cases": inherited_cases,
        "machine_pass_rate": machine_pass_rate,
        "adjudicated_pass_rate": adjudicated_pass_rate,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")


def _write_fake_artifacts(
    tmp_path,
    *,
    overall_mean=0.9232142857142858,
    pass_rate=0.6857142857142857,
    agent_failed_rate=0.0,
    judge_failed_rate=0.0,
    dataset_sha256=DEFAULT_DATASET_SHA256,
    judge_model=DEFAULT_JUDGE_MODEL,
    prompt_version=DEFAULT_PROMPT_VERSION,
    pass_rule_version=DEFAULT_PASS_RULE_VERSION,
    git_revision=DEFAULT_GIT_REVISION,
):
    metrics_path = tmp_path / "dialog_metrics.json"
    metadata_path = tmp_path / "run_metadata.json"
    predictions_path = tmp_path / "dialog_predictions.jsonl"
    adjudication_path = tmp_path / "adjudication_workbook.json"
    _write_fake_metrics(
        metrics_path,
        overall_mean=overall_mean,
        pass_rate=pass_rate,
        agent_failed_rate=agent_failed_rate,
        judge_failed_rate=judge_failed_rate,
    )
    _write_fake_metadata(
        metadata_path,
        dataset_sha256=dataset_sha256,
        judge_model=judge_model,
        prompt_version=prompt_version,
        pass_rule_version=pass_rule_version,
        git_revision=git_revision,
    )
    _write_fake_predictions(predictions_path, total_cases=35, passed_cases=24)
    _write_fake_adjudication(adjudication_path)
    return {
        "metrics": metrics_path,
        "metadata": metadata_path,
        "predictions": predictions_path,
        "adjudication": adjudication_path,
    }


def _build_with(paths):
    return regression.build_baseline(
        metrics_path=paths["metrics"],
        metadata_path=paths["metadata"],
        predictions_path=paths["predictions"],
        adjudication_path=paths["adjudication"],
        created_at="2026-08-27T00:00:00Z",
    )


def test_write_json_new_creates_file_exclusively(tmp_path):
    target = tmp_path / "report.json"
    payload = {"schema_version": "test", "values": [1, 2, 3]}
    regression.write_json_new(target, payload)
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_write_json_new_fails_when_target_exists_and_preserves_content(tmp_path):
    target = tmp_path / "report.json"
    original = b'{"original": true}\n'
    target.write_bytes(original)
    with pytest.raises(FileExistsError):
        regression.write_json_new(target, {"replacement": "must not happen"})
    assert target.read_bytes() == original


def test_regression_input_error_is_value_error():
    assert issubclass(regression.RegressionInputError, ValueError)


def test_build_baseline_from_valid_artifacts(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    baseline = _build_with(paths)
    assert set(baseline) == {
        "schema_version",
        "baseline_kind",
        "created_at",
        "execution_revision",
        "dataset_sha256",
        "predictions_sha256",
        "metrics_sha256",
        "judge_model",
        "prompt_version",
        "pass_rule_version",
        "machine_overall_mean",
        "machine_pass_rate",
        "agent_failed_rate",
        "judge_failed_rate",
        "adjudicated_pass_rate",
    }
    assert baseline["schema_version"] == "dialog_regression_baseline_v1"
    assert baseline["baseline_kind"] == "dialog_machine_monitoring"
    assert baseline["created_at"] == "2026-08-27T00:00:00Z"
    assert baseline["execution_revision"] == DEFAULT_GIT_REVISION
    assert baseline["dataset_sha256"] == DEFAULT_DATASET_SHA256
    assert baseline["predictions_sha256"] == _sha256_of(paths["predictions"])
    assert baseline["metrics_sha256"] == _sha256_of(paths["metrics"])
    assert baseline["judge_model"] == DEFAULT_JUDGE_MODEL
    assert baseline["prompt_version"] == DEFAULT_PROMPT_VERSION
    assert baseline["pass_rule_version"] == DEFAULT_PASS_RULE_VERSION
    assert baseline["machine_overall_mean"] == 0.9232142857142858
    assert baseline["machine_pass_rate"] == 0.6857142857142857
    assert baseline["agent_failed_rate"] == 0.0
    assert baseline["judge_failed_rate"] == 0.0
    assert baseline["adjudicated_pass_rate"] == {
        "value": 0.6285714285714286,
        "usage": "report_only",
        "included_in_automatic_regression": False,
        "reviewed_cases": 27,
        "inherited_cases": 8,
    }


def test_build_baseline_cross_checks_predictions_count_and_passed_cases(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    _write_fake_predictions(paths["predictions"], total_cases=30, passed_cases=24)
    with pytest.raises(regression.RegressionInputError):
        _build_with(paths)
    _write_fake_predictions(paths["predictions"], total_cases=35, passed_cases=23)
    with pytest.raises(regression.RegressionInputError):
        _build_with(paths)


def test_build_baseline_rejects_nonzero_agent_failure_rate(tmp_path):
    paths = _write_fake_artifacts(tmp_path, agent_failed_rate=0.02)
    with pytest.raises(regression.RegressionInputError):
        _build_with(paths)


def test_build_baseline_rejects_nonzero_judge_failure_rate(tmp_path):
    paths = _write_fake_artifacts(tmp_path, judge_failed_rate=0.02)
    with pytest.raises(regression.RegressionInputError):
        _build_with(paths)


def test_build_baseline_rejects_missing_metrics_fields(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    payload = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    del payload["overall_mean"]
    paths["metrics"].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(regression.RegressionInputError):
        _build_with(paths)


def test_create_baseline_fails_when_output_exists_and_preserves_file(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    output = tmp_path / "baseline.json"
    original = b'{"keep": "me"}\n'
    output.write_bytes(original)
    with pytest.raises(FileExistsError):
        regression.create_baseline(
            metrics_path=paths["metrics"],
            metadata_path=paths["metadata"],
            predictions_path=paths["predictions"],
            adjudication_path=paths["adjudication"],
            output_path=output,
            created_at="2026-08-27T00:00:00Z",
        )
    assert output.read_bytes() == original

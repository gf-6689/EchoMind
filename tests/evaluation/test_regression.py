"""Deterministic dialog baseline/regression module tests.

Tests use only tmp_path fixtures and fake JSON artifacts; they never
read or write the real formal evaluation directories and never touch
.test-tmp/ or .pytest_cache/.
"""

import hashlib
import inspect
import json
from decimal import Decimal
from pathlib import Path

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
    _write_fake_adjudication(adjudication_path, machine_pass_rate=pass_rate)
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


def _write_compare_inputs(
    tmp_path,
    *,
    baseline_overall_mean=0.9232142857142858,
    baseline_pass_rate=0.6857142857142857,
    current_overall_mean=0.9232142857142858,
    current_pass_rate=0.6857142857142857,
    current_agent_failed_rate=0.0,
    current_judge_failed_rate=0.0,
    baseline_dataset_sha256=DEFAULT_DATASET_SHA256,
    baseline_judge_model=DEFAULT_JUDGE_MODEL,
    baseline_prompt_version=DEFAULT_PROMPT_VERSION,
    baseline_pass_rule_version=DEFAULT_PASS_RULE_VERSION,
    baseline_git_revision=DEFAULT_GIT_REVISION,
    current_dataset_sha256=DEFAULT_DATASET_SHA256,
    current_judge_model=DEFAULT_JUDGE_MODEL,
    current_prompt_version=DEFAULT_PROMPT_VERSION,
    current_pass_rule_version=DEFAULT_PASS_RULE_VERSION,
    current_git_revision=DEFAULT_GIT_REVISION,
):
    (tmp_path / "baseline-src").mkdir()
    (tmp_path / "current-src").mkdir()
    baseline_inputs = _write_fake_artifacts(
        tmp_path / "baseline-src",
        overall_mean=baseline_overall_mean,
        pass_rate=baseline_pass_rate,
        dataset_sha256=baseline_dataset_sha256,
        judge_model=baseline_judge_model,
        prompt_version=baseline_prompt_version,
        pass_rule_version=baseline_pass_rule_version,
        git_revision=baseline_git_revision,
    )
    current_inputs = _write_fake_artifacts(
        tmp_path / "current-src",
        overall_mean=current_overall_mean,
        pass_rate=current_pass_rate,
        agent_failed_rate=current_agent_failed_rate,
        judge_failed_rate=current_judge_failed_rate,
        dataset_sha256=current_dataset_sha256,
        judge_model=current_judge_model,
        prompt_version=current_prompt_version,
        pass_rule_version=current_pass_rule_version,
        git_revision=current_git_revision,
    )
    baseline_path = tmp_path / "baseline.json"
    regression.write_json_new(
        baseline_path,
        regression.build_baseline(
            metrics_path=baseline_inputs["metrics"],
            metadata_path=baseline_inputs["metadata"],
            predictions_path=baseline_inputs["predictions"],
            adjudication_path=baseline_inputs["adjudication"],
            created_at="2026-08-27T00:00:00Z",
        ),
    )
    return {
        "baseline": baseline_path,
        "metrics": current_inputs["metrics"],
        "metadata": current_inputs["metadata"],
        "predictions": current_inputs["predictions"],
    }


def _compare_with(inputs):
    return regression.compare_against_baseline(
        baseline_path=inputs["baseline"],
        metrics_path=inputs["metrics"],
        metadata_path=inputs["metadata"],
        predictions_path=inputs["predictions"],
    )


def test_overall_mean_drop_over_5_percent_is_regression(tmp_path):
    inputs = _write_compare_inputs(
        tmp_path, baseline_overall_mean=1.0, current_overall_mean=0.94
    )
    report = _compare_with(inputs)
    comparison = next(
        item
        for item in report["metric_comparisons"]
        if item["metric"] == "machine_overall_mean"
    )
    assert comparison["regression"] is True
    assert report["regression_detected"] is True
    assert any("machine_overall_mean" in entry for entry in report["regressions"])


def test_pass_rate_drop_over_5_percent_is_regression(tmp_path):
    inputs = _write_compare_inputs(tmp_path, baseline_pass_rate=0.8, current_pass_rate=0.75)
    report = _compare_with(inputs)
    comparison = next(
        item
        for item in report["metric_comparisons"]
        if item["metric"] == "machine_pass_rate"
    )
    assert comparison["regression"] is True
    assert report["regression_detected"] is True
    assert any("machine_pass_rate" in entry for entry in report["regressions"])


@pytest.mark.parametrize(
    ("current", "delta_relation", "expected_regression"),
    [
        (0.95, "equal", False),
        (0.949999, "below", True),
        (0.950001, "above", False),
    ],
)
def test_threshold_boundary_uses_decimal_exact_judgment(
    tmp_path, current, delta_relation, expected_regression
):
    inputs = _write_compare_inputs(
        tmp_path, baseline_overall_mean=1.0, current_overall_mean=current
    )
    report = _compare_with(inputs)
    comparison = next(
        item
        for item in report["metric_comparisons"]
        if item["metric"] == "machine_overall_mean"
    )
    delta = Decimal(str(comparison["relative_delta"]))
    threshold = Decimal("-0.05")
    if delta_relation == "equal":
        assert delta == threshold
    elif delta_relation == "below":
        assert delta < threshold
    else:
        assert delta > threshold
    assert comparison["regression"] is expected_regression


def test_current_agent_failure_rate_positive_is_regression(tmp_path):
    inputs = _write_compare_inputs(tmp_path, current_agent_failed_rate=0.02)
    report = _compare_with(inputs)
    gate = next(
        item for item in report["failure_gates"] if item["gate"] == "agent_failed_rate"
    )
    assert gate["regression"] is True
    assert report["regression_detected"] is True
    assert any("agent_failed_rate" in entry for entry in report["regressions"])


def test_current_judge_failure_rate_positive_is_regression(tmp_path):
    inputs = _write_compare_inputs(tmp_path, current_judge_failed_rate=0.02)
    report = _compare_with(inputs)
    gate = next(
        item for item in report["failure_gates"] if item["gate"] == "judge_failed_rate"
    )
    assert gate["regression"] is True
    assert report["regression_detected"] is True
    assert any("judge_failed_rate" in entry for entry in report["regressions"])


def test_dataset_sha_mismatch_fails_closed_with_invalid_report(tmp_path):
    inputs = _write_compare_inputs(tmp_path, current_dataset_sha256="f" * 64)
    report = _compare_with(inputs)
    assert report["comparison_valid"] is False
    assert report["regressions"] == []
    assert report["regression_detected"] is False
    checks = {item["field"]: item for item in report["identity_checks"]}
    assert checks["dataset_sha256"]["match"] is False
    assert checks["dataset_sha256"]["baseline"] == DEFAULT_DATASET_SHA256
    assert checks["dataset_sha256"]["current"] == "f" * 64


def test_judge_model_mismatch_fails_closed(tmp_path):
    inputs = _write_compare_inputs(tmp_path, current_judge_model="different-judge-model")
    report = _compare_with(inputs)
    assert report["comparison_valid"] is False
    checks = {item["field"]: item for item in report["identity_checks"]}
    assert checks["judge_model"]["match"] is False


def test_prompt_version_mismatch_fails_closed(tmp_path):
    inputs = _write_compare_inputs(tmp_path, current_prompt_version="different-prompt")
    report = _compare_with(inputs)
    assert report["comparison_valid"] is False
    checks = {item["field"]: item for item in report["identity_checks"]}
    assert checks["prompt_version"]["match"] is False


def test_pass_rule_version_mismatch_fails_closed(tmp_path):
    inputs = _write_compare_inputs(tmp_path, current_pass_rule_version="different-rule")
    report = _compare_with(inputs)
    assert report["comparison_valid"] is False
    checks = {item["field"]: item for item in report["identity_checks"]}
    assert checks["pass_rule_version"]["match"] is False


def test_execution_revision_and_artifact_hashes_may_differ(tmp_path):
    inputs = _write_compare_inputs(
        tmp_path,
        baseline_git_revision=DEFAULT_GIT_REVISION,
        current_git_revision="9999999999999999999999999999999999999999",
    )
    with inputs["predictions"].open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"case_id": "extra", "case_pass": false}\n')
    metrics_payload = json.loads(inputs["metrics"].read_text(encoding="utf-8"))
    metrics_payload["note"] = "different content"
    inputs["metrics"].write_text(
        json.dumps(metrics_payload, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    report = _compare_with(inputs)
    assert report["comparison_valid"] is True
    assert all(item["match"] for item in report["identity_checks"])
    assert report["current_execution_revision"] == "9999999999999999999999999999999999999999"
    baseline_payload = json.loads(inputs["baseline"].read_text(encoding="utf-8"))
    assert report["current_predictions_sha256"] != baseline_payload["predictions_sha256"]
    assert report["current_metrics_sha256"] != baseline_payload["metrics_sha256"]


def test_adjudicated_pass_rate_not_in_automatic_regression(tmp_path):
    inputs = _write_compare_inputs(tmp_path)
    report = _compare_with(inputs)
    baseline_payload = json.loads(inputs["baseline"].read_text(encoding="utf-8"))
    assert (
        report["adjudicated_pass_rate_report_only"]
        == baseline_payload["adjudicated_pass_rate"]
    )
    assert all(
        item["metric"] != "adjudicated_pass_rate" for item in report["metric_comparisons"]
    )
    assert all("adjudicated" not in entry for entry in report["regressions"])
    assert all(
        item["gate"] != "adjudicated_pass_rate" for item in report["failure_gates"]
    )
    assert "adjudication" not in inspect.signature(
        regression.compare_against_baseline
    ).parameters


def test_compare_does_not_modify_baseline(tmp_path):
    inputs = _write_compare_inputs(
        tmp_path, baseline_overall_mean=1.0, current_overall_mean=0.5
    )
    before = _sha256_of(inputs["baseline"])
    report = _compare_with(inputs)
    after = _sha256_of(inputs["baseline"])
    assert before == after
    assert report["comparison_valid"] is True


def test_metric_comparison_records_baseline_current_delta_threshold_regression(tmp_path):
    inputs = _write_compare_inputs(
        tmp_path, baseline_overall_mean=1.0, current_overall_mean=0.94
    )
    report = _compare_with(inputs)
    comparison = next(
        item
        for item in report["metric_comparisons"]
        if item["metric"] == "machine_overall_mean"
    )
    assert set(comparison) == {
        "metric",
        "baseline",
        "current",
        "relative_delta",
        "threshold",
        "regression",
    }
    assert comparison["baseline"] == 1.0
    assert comparison["current"] == 0.94
    assert comparison["relative_delta"] == pytest.approx(-0.06)
    assert comparison["threshold"] == -0.05
    assert comparison["regression"] is True


def test_report_contains_all_required_top_level_fields(tmp_path):
    inputs = _write_compare_inputs(tmp_path)
    report = _compare_with(inputs)
    assert set(report) == {
        "schema_version",
        "baseline_path",
        "baseline_sha256",
        "current_execution_revision",
        "current_predictions_sha256",
        "current_metrics_sha256",
        "comparison_valid",
        "identity_checks",
        "metric_comparisons",
        "failure_gates",
        "regressions",
        "regression_detected",
        "adjudicated_pass_rate_report_only",
    }
    assert report["schema_version"] == "dialog_regression_report_v1"


def test_no_intent_fields_in_baseline_or_report(tmp_path):
    inputs = _write_compare_inputs(tmp_path)
    report = _compare_with(inputs)
    baseline_payload = json.loads(inputs["baseline"].read_text(encoding="utf-8"))
    for name in ("intent_accuracy", "intent_macro_f1"):
        assert name not in baseline_payload
        assert name not in report


def _write_cli_create_args(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    output = tmp_path / "baseline.json"
    argv = [
        "create-baseline",
        "--metrics", str(paths["metrics"]),
        "--metadata", str(paths["metadata"]),
        "--predictions", str(paths["predictions"]),
        "--adjudication", str(paths["adjudication"]),
        "--output", str(output),
        "--created-at", "2026-08-27T00:00:00Z",
    ]
    return paths, argv, output


def _write_cli_compare_args(
    tmp_path,
    *,
    current_overall_mean=0.9232142857142858,
    current_dataset_sha256=DEFAULT_DATASET_SHA256,
):
    inputs = _write_compare_inputs(
        tmp_path,
        current_overall_mean=current_overall_mean,
        current_dataset_sha256=current_dataset_sha256,
    )
    output = tmp_path / "regression-report.json"
    argv = [
        "compare",
        "--baseline", str(inputs["baseline"]),
        "--metrics", str(inputs["metrics"]),
        "--metadata", str(inputs["metadata"]),
        "--predictions", str(inputs["predictions"]),
        "--output", str(output),
    ]
    return inputs, argv, output


def test_cli_create_baseline_end_to_end_exit_0(tmp_path):
    paths, argv, output = _write_cli_create_args(tmp_path)
    assert regression.main(argv) == 0
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "dialog_regression_baseline_v1"
    assert payload["created_at"] == "2026-08-27T00:00:00Z"


def test_cli_compare_clean_exit_0(tmp_path):
    inputs, argv, output = _write_cli_compare_args(tmp_path)
    assert regression.main(argv) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["comparison_valid"] is True
    assert payload["regression_detected"] is False
    assert payload["regressions"] == []


def test_cli_compare_regression_exit_1(tmp_path):
    inputs, argv, output = _write_cli_compare_args(tmp_path, current_overall_mean=0.5)
    assert regression.main(argv) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["regression_detected"] is True
    assert payload["regressions"]


def test_cli_compare_identity_mismatch_exit_2_with_report_written(tmp_path):
    inputs, argv, output = _write_cli_compare_args(
        tmp_path, current_dataset_sha256="f" * 64
    )
    baseline_before = _sha256_of(inputs["baseline"])
    assert regression.main(argv) == 2
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["comparison_valid"] is False
    assert payload["regressions"] == []
    assert _sha256_of(inputs["baseline"]) == baseline_before


def test_cli_report_output_exists_exit_2(tmp_path):
    inputs, argv, output = _write_cli_compare_args(tmp_path)
    original = b'{"keep": "historical report"}\n'
    output.write_bytes(original)
    baseline_before = _sha256_of(inputs["baseline"])
    assert regression.main(argv) == 2
    assert output.read_bytes() == original
    assert _sha256_of(inputs["baseline"]) == baseline_before


def test_cli_invalid_json_exit_2(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    paths["metrics"].write_text("{not json", encoding="utf-8")
    argv = [
        "create-baseline",
        "--metrics", str(paths["metrics"]),
        "--metadata", str(paths["metadata"]),
        "--predictions", str(paths["predictions"]),
        "--adjudication", str(paths["adjudication"]),
        "--output", str(tmp_path / "baseline.json"),
    ]
    assert regression.main(argv) == 2


def test_cli_missing_file_exit_2(tmp_path):
    paths = _write_fake_artifacts(tmp_path)
    argv = [
        "create-baseline",
        "--metrics", str(tmp_path / "missing-metrics.json"),
        "--metadata", str(paths["metadata"]),
        "--predictions", str(paths["predictions"]),
        "--adjudication", str(paths["adjudication"]),
        "--output", str(tmp_path / "baseline.json"),
    ]
    assert regression.main(argv) == 2


def test_module_imports_stdlib_only_and_never_reads_env_or_network(tmp_path, monkeypatch):
    source = Path(regression.__file__).read_text(encoding="utf-8")
    for token in (
        "dotenv",
        "load_dotenv",
        "anthropic",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "subprocess",
    ):
        assert token not in source
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "EVAL_JUDGE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    paths, argv, output = _write_cli_create_args(tmp_path)
    assert regression.main(argv) == 0
    assert output.is_file()

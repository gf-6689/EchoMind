import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.agent_orchestrator import Request
from evaluation.run_dialog_eval import (
    build_parser,
    evaluate_case,
    load_and_validate,
    main,
    prepare_output_dir,
    resolve_config,
    run_evaluation,
)
from evaluation.dialog_metrics import compute_dialog_metrics


def make_case(messages):
    return {
        "case_id": "case-1",
        "category": "multi_turn_refund",
        "description": "test case",
        "context": "The refund arrives within five business days.",
        "turns": [
            {
                "user_message": message,
                "reference_answer": "Use the controlled context.",
                "required_points": ["refund"],
            }
            for message in messages
        ],
        "expected_routing": {"intent": "refund", "agent_type": "billing"},
    }


def make_named_case(case_id, messages):
    case = make_case(messages)
    case["case_id"] = case_id
    return case


def build_args(**overrides):
    values = {
        "dialog_data": Path("dialog.json"),
        "output_dir": Path("run"),
        "limit": None,
        "base_url": None,
        "agent_model": None,
        "judge_model": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def agent_result(number):
    enum_value = lambda value: SimpleNamespace(value=value)
    return SimpleNamespace(
        response=f"answer {number}",
        intent=enum_value("refund"),
        primary_agent=enum_value("billing"),
        agent_type=enum_value("billing"),
        supporting_agents=[enum_value("general")],
        routing_reason="fake route",
        routing_confidence=0.9,
        escalated=False,
        latency_ms=12.0,
    )


class FakeOrchestrator:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeJudge:
    def __init__(self):
        self.calls = []

    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        judge = {
            "relevance": 0.8,
            "accuracy": 0.8,
            "completeness": 0.8,
            "helpfulness": 0.8,
            "overall": 0.8,
            "reasoning": "fake reasoning",
            "latency_ms": 20.0,
        }
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": judge,
        }


class FailingJudge(FakeJudge):
    def __init__(self, fail_on_call, failure):
        super().__init__()
        self.fail_on_call = fail_on_call
        self.failure = failure

    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == self.fail_on_call:
            return self.failure
        judge = {
            "relevance": 0.8,
            "accuracy": 0.8,
            "completeness": 0.8,
            "helpfulness": 0.8,
            "overall": 0.8,
            "reasoning": "fake reasoning",
            "latency_ms": 20.0,
        }
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": judge,
        }


class SkippingJudge(FakeJudge):
    async def judge_turn(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "judge_failed": False,
                "judge_error": None,
                "judge_skipped": True,
                "judge_attempts": 0,
                "judge": None,
            }
        judge = {
            "relevance": 0.8,
            "accuracy": 0.8,
            "completeness": 0.8,
            "helpfulness": 0.8,
            "overall": 0.8,
            "reasoning": "fake reasoning",
            "latency_ms": 20.0,
        }
        return {
            "judge_failed": False,
            "judge_error": None,
            "judge_skipped": False,
            "judge_attempts": 1,
            "judge": judge,
        }


def test_evaluate_case_reuses_conv_id_truncates_request_history_and_preserves_judge_history():
    orchestrator = FakeOrchestrator([agent_result(index) for index in range(1, 5)])
    judge = FakeJudge()

    output = asyncio.run(evaluate_case(make_case(["one", "two", "three", "four"]), orchestrator, judge))

    assert all(isinstance(request, Request) for request in orchestrator.requests)
    assert {request.conv_id for request in orchestrator.requests} == {output["conv_id"]}
    assert orchestrator.requests[0].history == []
    assert orchestrator.requests[3].history == [
        {"role": "assistant", "content": "answer 1"},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": "answer 2"},
        {"role": "user", "content": "three"},
        {"role": "assistant", "content": "answer 3"},
    ]
    assert judge.calls[3]["history"] == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "answer 1"},
        {"role": "user", "content": "two"},
        {"role": "assistant", "content": "answer 2"},
        {"role": "user", "content": "three"},
        {"role": "assistant", "content": "answer 3"},
    ]
    assert output["expected_routing"] == {"intent": "refund", "agent_type": "billing"}
    assert output["routing_audit"] == {"intent_match": True, "agent_match": True}
    assert output["agent_error"] is None
    assert output["judge_error"] is None
    assert output["turns"][0] == {
        "turn_id": 1,
        "user_message": "one",
        "agent_response": "answer 1",
        "intent": "refund",
        "primary_agent": "billing",
        "supporting_agents": ["general"],
        "routing_reason": "fake route",
        "routing_confidence": 0.9,
        "escalated": False,
        "agent_latency_ms": 12.0,
        "agent_failed": False,
        "agent_error": None,
        "judge_failed": False,
        "judge_error": None,
        "judge_skipped": False,
        "judge_attempts": 1,
        "judge": {
            "relevance": 0.8,
            "accuracy": 0.8,
            "completeness": 0.8,
            "helpfulness": 0.8,
            "overall": 0.8,
            "reasoning": "fake reasoning",
            "latency_ms": 20.0,
        },
    }


def test_agent_failure_skips_judge_and_preserves_later_input_turns():
    orchestrator = FakeOrchestrator([RuntimeError("API-key=secret-token agent boom")])
    judge = FakeJudge()

    output = asyncio.run(evaluate_case(make_case(["one", "two", "three"]), orchestrator, judge))

    first, *later = output["turns"]
    assert first["agent_response"] is None
    assert first["agent_failed"] is True
    assert first["judge_skipped"] is True
    assert first["judge_attempts"] == 0
    assert "secret-token" not in first["agent_error"]
    assert [turn["user_message"] for turn in later] == ["two", "three"]
    assert all(turn["agent_error"] == "skipped after prior agent failure" for turn in later)
    assert all(turn["judge_skipped"] and turn["judge_attempts"] == 0 for turn in output["turns"])
    assert judge.calls == []
    assert output["agent_failed"] is True
    assert output["agent_error"] == "turn 1: API-key=[REDACTED] agent boom"
    assert output["judge_failed"] is False
    assert output["judge_error"] is None
    assert output["case_scores"] is None
    assert output["passed"] is None
    assert output["routing_audit"] == {"intent_match": False, "agent_match": False}


def test_judge_final_failure_invalidates_case_but_keeps_agent_response():
    judge = FailingJudge(
        fail_on_call=2,
        failure={
            "judge_failed": True,
            "judge_error": "final judge failure",
            "judge_skipped": False,
            "judge_attempts": 3,
            "judge": {"latency_ms": 30.0},
        },
    )
    output = asyncio.run(evaluate_case(
        make_case(["one", "two"]),
        FakeOrchestrator([agent_result(1), agent_result(2)]),
        judge,
    ))

    assert output["turns"][1]["agent_response"] == "answer 2"
    assert output["turns"][1]["judge_failed"] is True
    assert output["turns"][1]["judge_attempts"] == 3
    assert output["judge_failed"] is True
    assert output["agent_error"] is None
    assert output["judge_error"] == "turn 2: final judge failure"
    assert output["judge_skipped"] is False
    assert output["case_scores"] is None
    assert output["passed"] is None


def test_unstarted_judge_failure_is_not_skipped_and_is_sanitized():
    judge = FailingJudge(
        fail_on_call=1,
        failure={
            "judge_failed": True,
            "judge_error": "API-key=secret-token prompt failed",
            "judge_skipped": False,
            "judge_attempts": 0,
            "judge": None,
        },
    )
    output = asyncio.run(evaluate_case(
        make_case(["one"]),
        FakeOrchestrator([agent_result(1)]),
        judge,
    ))

    turn = output["turns"][0]
    assert turn["judge"] is None
    assert turn["judge_attempts"] == 0
    assert turn["judge_failed"] is True
    assert turn["judge_skipped"] is False
    assert "secret-token" not in turn["judge_error"]
    assert output["judge_failed"] is True
    assert output["judge_skipped"] is False
    assert output["case_scores"] is None
    assert output["passed"] is None


def test_case_is_judge_skipped_when_any_turn_is_skipped():
    output = asyncio.run(evaluate_case(
        make_case(["one", "two"]),
        FakeOrchestrator([agent_result(1), agent_result(2)]),
        SkippingJudge(),
    ))

    assert output["turns"][0]["judge_skipped"] is True
    assert output["turns"][1]["judge_skipped"] is False
    assert output["judge_skipped"] is True
    assert output["judge_failed"] is False
    assert output["agent_error"] is None
    assert output["judge_error"] is None
    assert output["case_scores"] is None
    assert output["passed"] is None


def test_dialog_validator_rejects_duplicate_case_ids(tmp_path):
    path = tmp_path / "bad.json"
    case = {
        "case_id": "same",
        "category": "faq",
        "description": "x",
        "context": "",
        "turns": [
            {
                "user_message": "q",
                "reference_answer": "a",
                "required_points": ["p"],
            }
        ],
        "expected_routing": {"intent": "query", "agent_type": "general"},
    }
    path.write_text(json.dumps([case, case], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case_id"):
        load_and_validate(path)


def test_dialog_validator_unit_fixture_is_independent_of_workspace_layout(tmp_path):
    path = tmp_path / "dialog_smoke.json"
    path.write_text(
        json.dumps([make_named_case(f"dialog_smoke_{index:03d}", (f"question {index}",)) for index in range(1, 6)]),
        encoding="utf-8",
    )

    cases = load_and_validate(path, expected_count=5)

    assert [case["case_id"] for case in cases] == [
        "dialog_smoke_001",
        "dialog_smoke_002",
        "dialog_smoke_003",
        "dialog_smoke_004",
        "dialog_smoke_005",
    ]


def test_dialog_validator_rejects_wrong_expected_count(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="expected 5 cases, found 0"):
        load_and_validate(path, expected_count=5)


def test_parser_has_no_api_key_option():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([
            "--dialog-data", "x", "--output-dir", "y", "--api-key", "secret",
        ])


def test_main_rejects_api_key_argument_without_echoing_its_secret(capsys):
    with pytest.raises(SystemExit) as raised:
        main([
            "--dialog-data", "x", "--output-dir", "y", "--api-key", "env-secret",
        ])

    stderr = capsys.readouterr().err
    assert raised.value.code == 2
    assert "--api-key is not supported" in stderr
    assert "env-secret" not in stderr


@pytest.mark.parametrize(
    "forbidden_args",
    [
        ["--api-key=SUBPROCESS_SENTINEL"],
        ["--api-key", "SUBPROCESS_SENTINEL"],
    ],
    ids=["equals", "split"],
)
def test_supported_direct_python_launcher_does_not_echo_forbidden_key_value(forbidden_args):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.run_dialog_eval",
            "--dialog-data",
            "unused.json",
            "--output-dir",
            "unused-output",
            *forbidden_args,
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    combined_output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "--api-key is not supported" in combined_output
    assert "SUBPROCESS_SENTINEL" not in combined_output


def test_resolve_config_reads_key_only_from_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-secret")

    config = resolve_config(build_args(), os.environ)

    assert config == {
        "api_key": "env-secret",
        "base_url": None,
        "agent_model": "deepseek-v4-pro",
        "judge_model": "deepseek-v4-pro",
    }


def test_resolve_config_requires_an_environment_key():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not configured"):
        resolve_config(build_args(), {})


def test_prepare_output_dir_rejects_non_empty_directory(tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    (output / "existing.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        prepare_output_dir(output)


def test_run_writes_one_case_per_jsonl_line_and_safe_metadata(tmp_path):
    dataset_path = tmp_path / "dialog.json"
    dataset_path.write_text("[]", encoding="utf-8")
    cases = [
        make_named_case("case-1", ("question 1",)),
        make_named_case("case-2", ("question 2",)),
    ]
    config = {
        "api_key": "must-not-leak",
        "base_url": "https://example.invalid",
        "agent_model": "agent",
        "judge_model": "judge",
    }

    paths = asyncio.run(run_evaluation(
        cases=cases,
        output_dir=tmp_path / "run",
        orchestrator=FakeOrchestrator([agent_result(1), agent_result(2)]),
        judge=FakeJudge(),
        config=config,
        dataset_path=dataset_path,
    ))

    lines = paths["predictions"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["case_id"] for line in lines] == ["case-1", "case-2"]
    assert json.loads(paths["metrics"].read_text(encoding="utf-8"))["total_cases"] == 2
    metadata_text = paths["metadata"].read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)
    assert "must-not-leak" not in metadata_text
    assert set(metadata) == {
        "dataset_path", "dataset_sha256", "case_count", "git_revision",
        "agent_model", "judge_model", "prompt_version", "temperature",
        "pass_threshold", "timeout", "max_attempts", "context_mode",
        "retrieval_evaluated", "started_at", "completed_at",
    }
    assert metadata["dataset_sha256"] == hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    assert metadata["case_count"] == 2
    assert metadata["prompt_version"] == "dialog_judge_v2"
    assert metadata["context_mode"] == "controlled_context"
    assert metadata["retrieval_evaluated"] is False


def test_run_preserves_partial_jsonl_and_writes_best_effort_outputs_on_case_failure(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    dataset_path = tmp_path / "dialog.json"
    dataset_path.write_text("[]", encoding="utf-8")
    completed = {"count": 0}

    async def fake_evaluate_case(case, orchestrator, judge, user_id="eval-user", secrets=()):
        completed["count"] += 1
        if completed["count"] == 2:
            raise RuntimeError("request failed for must-not-leak")
        return {
            "case_id": case["case_id"], "agent_failed": False, "judge_failed": False,
            "case_scores": {name: 0.8 for name in ("relevance", "accuracy", "completeness", "helpfulness", "overall")},
            "turns": [],
        }

    monkeypatch.setattr(run_dialog_eval, "evaluate_case", fake_evaluate_case)
    output_dir = tmp_path / "run"
    config = {"api_key": "must-not-leak", "base_url": None, "agent_model": "agent", "judge_model": "judge"}

    with pytest.raises(RuntimeError, match="request failed"):
        asyncio.run(run_evaluation(
            cases=[make_named_case("case-1", ("one",)), make_named_case("case-2", ("two",))],
            output_dir=output_dir,
            orchestrator=object(),
            judge=object(),
            config=config,
            dataset_path=dataset_path,
        ))

    assert [json.loads(line)["case_id"] for line in (output_dir / "dialog_predictions.jsonl").read_text(encoding="utf-8").splitlines()] == ["case-1"]
    assert json.loads((output_dir / "dialog_metrics.json").read_text(encoding="utf-8"))["total_cases"] == 1
    metadata_text = (output_dir / "run_metadata.json").read_text(encoding="utf-8")
    assert json.loads(metadata_text)["case_count"] == 1
    assert "must-not-leak" not in metadata_text


def _persistable_case(case_id):
    return {
        "case_id": case_id,
        "agent_failed": False,
        "agent_error": None,
        "judge_failed": False,
        "judge_error": None,
        "case_scores": {
            name: 0.8
            for name in ("relevance", "accuracy", "completeness", "helpfulness", "overall")
        },
        "turns": [],
    }


def _run_with_fake_case_results(tmp_path, monkeypatch, case_ids=("case-1", "case-2")):
    from evaluation import run_dialog_eval

    async def fake_evaluate_case(case, orchestrator, judge, user_id="eval-user", secrets=()):
        return _persistable_case(case["case_id"])

    monkeypatch.setattr(run_dialog_eval, "evaluate_case", fake_evaluate_case)
    dataset_path = tmp_path / "dialog.json"
    dataset_path.write_text("[]", encoding="utf-8")
    output_dir = tmp_path / "run"
    config = {
        "api_key": "must-not-leak",
        "base_url": None,
        "agent_model": "agent",
        "judge_model": "judge",
    }
    operation = lambda: asyncio.run(run_evaluation(
        cases=[make_named_case(case_id, ("question",)) for case_id in case_ids],
        output_dir=output_dir,
        orchestrator=object(),
        judge=object(),
        config=config,
        dataset_path=dataset_path,
    ))
    return operation, output_dir


def _assert_persisted_artifact_counts(output_dir, expected_count):
    rows = [
        json.loads(line)
        for line in (output_dir / "dialog_predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    metrics = json.loads((output_dir / "dialog_metrics.json").read_text(encoding="utf-8"))
    metadata = json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert len(rows) == metrics["total_cases"] == metadata["case_count"] == expected_count


def test_serialization_failure_does_not_count_unwritten_case(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    real_dumps = run_dialog_eval.json.dumps

    def failing_dumps(value, *args, **kwargs):
        if isinstance(value, dict) and value.get("case_id") == "case-2":
            raise TypeError("case serialization failed")
        return real_dumps(value, *args, **kwargs)

    monkeypatch.setattr(run_dialog_eval.json, "dumps", failing_dumps)
    operation, output_dir = _run_with_fake_case_results(tmp_path, monkeypatch)

    with pytest.raises(TypeError, match="case serialization failed"):
        operation()

    _assert_persisted_artifact_counts(output_dir, 1)


class _FailingPredictionHandle:
    def __init__(self, handle, mode):
        self._handle = handle
        self._mode = mode
        self._case_writes = 0
        self._failed = False

    def __enter__(self):
        self._handle.__enter__()
        return self

    def __exit__(self, *args):
        return self._handle.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def write(self, value):
        self._case_writes += 1
        if self._case_writes == 2 and self._mode == "write":
            self._handle.write(value[:12])
            self._failed = True
            raise OSError("prediction write failed")
        return self._handle.write(value)

    def flush(self):
        if self._case_writes == 2 and self._mode == "flush" and not self._failed:
            self._failed = True
            raise OSError("prediction flush failed")
        return self._handle.flush()


@pytest.mark.parametrize("failure_mode", ["write", "flush"])
def test_prediction_persistence_failure_rolls_back_partial_line_and_counts_only_flushed_rows(
    tmp_path, monkeypatch, failure_mode
):
    real_open = Path.open
    output_dir = tmp_path / "run"
    predictions_path = output_dir / "dialog_predictions.jsonl"

    def patched_open(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        if Path(path) == predictions_path:
            return _FailingPredictionHandle(handle, failure_mode)
        return handle

    monkeypatch.setattr(Path, "open", patched_open)
    operation, _ = _run_with_fake_case_results(tmp_path, monkeypatch)

    with pytest.raises(OSError, match=f"prediction {failure_mode} failed"):
        operation()

    _assert_persisted_artifact_counts(output_dir, 1)
    assert [
        json.loads(line)["case_id"]
        for line in predictions_path.read_text(encoding="utf-8").splitlines()
    ] == ["case-1"]


def test_agent_exception_latency_is_recorded_and_included_in_metrics():
    class SlowFailingOrchestrator:
        async def run(self, request):
            await asyncio.sleep(0.01)
            raise RuntimeError("agent boom")

    output = asyncio.run(evaluate_case(make_case(["one"]), SlowFailingOrchestrator(), FakeJudge()))
    latency = output["turns"][0]["agent_latency_ms"]
    metrics = compute_dialog_metrics([output])

    assert latency >= 5.0
    assert metrics["agent_latency_count"] == 1
    assert metrics["agent_latency_mean_ms"] == latency
    assert metrics["judge_latency_count"] == 0
    assert metrics["judge_latency_mean_ms"] is None
    assert metrics["judge_latency_p50_ms"] is None
    assert metrics["judge_latency_p95_ms"] is None


def test_successful_run_attempts_metadata_when_metrics_atomic_replace_fails(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    real_replace = run_dialog_eval.os.replace
    attempted = []

    def failing_replace(source, destination):
        destination = Path(destination)
        attempted.append(destination.name)
        if destination.name == "dialog_metrics.json":
            raise OSError("metrics replace failed")
        return real_replace(source, destination)

    monkeypatch.setattr(run_dialog_eval.os, "replace", failing_replace)
    operation, output_dir = _run_with_fake_case_results(tmp_path, monkeypatch, ("case-1",))

    with pytest.raises(RuntimeError, match="metrics replace failed"):
        operation()

    assert attempted == ["dialog_metrics.json", "run_metadata.json"]
    assert json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))["case_count"] == 1


def test_finalization_reports_both_metrics_and_metadata_failures(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    attempted = []

    def failing_replace(source, destination):
        name = Path(destination).name
        attempted.append(name)
        raise OSError(f"{name} replace failed")

    monkeypatch.setattr(run_dialog_eval.os, "replace", failing_replace)
    operation, _ = _run_with_fake_case_results(tmp_path, monkeypatch, ("case-1",))

    with pytest.raises(RuntimeError) as raised:
        operation()

    assert attempted == ["dialog_metrics.json", "run_metadata.json"]
    assert "dialog_metrics.json replace failed" in str(raised.value)
    assert "run_metadata.json replace failed" in str(raised.value)


def test_case_failure_still_attempts_metadata_when_metrics_finalization_fails(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    async def failing_evaluate_case(case, orchestrator, judge, user_id="eval-user", secrets=()):
        raise RuntimeError("case evaluation failed")

    real_replace = run_dialog_eval.os.replace
    attempted = []

    def failing_replace(source, destination):
        destination = Path(destination)
        attempted.append(destination.name)
        if destination.name == "dialog_metrics.json":
            raise OSError("metrics replace failed")
        return real_replace(source, destination)

    monkeypatch.setattr(run_dialog_eval.os, "replace", failing_replace)
    operation, output_dir = _run_with_fake_case_results(tmp_path, monkeypatch, ("case-1",))
    monkeypatch.setattr(run_dialog_eval, "evaluate_case", failing_evaluate_case)

    with pytest.raises(BaseExceptionGroup) as raised:
        operation()

    assert attempted == ["dialog_metrics.json", "run_metadata.json"]
    assert "case evaluation failed" in str(raised.value.exceptions[0])
    assert "metrics replace failed" in str(raised.value.exceptions[1])
    assert json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))["case_count"] == 0


def test_cli_validates_entire_dataset_before_applying_limit(tmp_path, monkeypatch):
    dataset_path = tmp_path / "dialog.json"
    valid_case = make_named_case("case-1", ("one",))
    invalid_case = make_named_case("case-2", ("two",))
    invalid_case["unexpected"] = True
    dataset_path.write_text(json.dumps([valid_case, invalid_case]), encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-secret")
    output_dir = tmp_path / "run"

    assert main([
        "--dialog-data", str(dataset_path), "--output-dir", str(output_dir), "--limit", "1",
    ]) == 1
    assert not output_dir.exists()


def test_main_metadata_uses_validated_dataset_snapshot_when_source_changes(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    dataset_path = tmp_path / "dialog.json"
    dataset_path.write_text(json.dumps([make_named_case("case-1", ("one",))]), encoding="utf-8")
    expected_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    output_dir = tmp_path / "run"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-secret")

    class MutatingOrchestrator:
        async def run(self, request):
            dataset_path.write_text("[]", encoding="utf-8")
            return agent_result(1)

    monkeypatch.setattr(
        run_dialog_eval,
        "_create_dependencies",
        lambda config: (MutatingOrchestrator(), FakeJudge()),
    )

    assert main(["--dialog-data", str(dataset_path), "--output-dir", str(output_dir)]) == 0
    metadata = json.loads((output_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["dataset_sha256"] == expected_hash


def test_main_rejects_non_empty_output_before_constructing_dependencies(tmp_path, monkeypatch):
    from evaluation import run_dialog_eval

    dataset_path = tmp_path / "dialog.json"
    dataset_path.write_text(json.dumps([make_named_case("case-1", ("one",))]), encoding="utf-8")
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    (output_dir / "existing.json").write_text("{}", encoding="utf-8")
    constructed = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-secret")
    monkeypatch.setattr(
        run_dialog_eval,
        "_create_dependencies",
        lambda config: constructed.append(config),
    )

    assert main(["--dialog-data", str(dataset_path), "--output-dir", str(output_dir)]) == 1
    assert constructed == []

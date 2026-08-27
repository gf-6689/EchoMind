"""One-time formal driver for the Judge v5 35-case / 43-turn run.

This committed driver only orchestrates the frozen evaluation contract:
preflight checks, one dependency construction, a hard-gated warm-up
phase, the formal 35-case phase, read-only verification and an evidence
summary.  All scoring, caps, pass decisions and metric aggregation come
from the production modules ``evaluation.dialog_policy``,
``evaluation.dialog_metrics`` and ``evaluation.run_dialog_eval``; nothing
is reimplemented here.  Dependencies and the run phase are injectable so
the offline test suite can drive every gate with fakes.
"""

import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from evaluation.dialog_judge import JUDGE_OUTPUT_STRATEGY, PROMPT_VERSION
from evaluation.dialog_metrics import compute_dialog_metrics
from evaluation.dialog_policy import (
    COMPLETENESS_POLICY_VERSION,
    DIMENSION_PASS_FLOOR,
    OVERALL_PASS_THRESHOLD,
    PASS_RULE_VERSION,
    VIOLATION_POLICY_VERSION,
    compute_case_pass,
    compute_turn_pass,
    score_assessment,
)
from evaluation.run_dialog_eval import (
    _create_dependencies,
    _load_validated_dataset,
    resolve_config,
    run_evaluation,
)

DATASET = Path(r"E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json")
WARMUP_DIR = Path(r"E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-warmup-v5-20260826")
FORMAL_DIR = Path(r"E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826")
DRIVER_REL_PATH = "data/eval/runs/run_dialog_eval_v5_final.py"
EXPECTED_AGENT_MODEL = "deepseek-v4-pro"
EXPECTED_JUDGE_MODEL = "deepseek-v4-pro"
EXPECTED_DATASET_SHA256 = "cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2"
EXPECTED_CASE_IDS = [f"dialog_eval_{index:03d}" for index in range(1, 36)]
JUDGE_TEMPERATURE = 0.0
JUDGE_TIMEOUT_SECONDS = 30.0
JUDGE_MAX_ATTEMPTS = 3

IDENTITY_KEYS = (
    "agent_model",
    "judge_model",
    "prompt_version",
    "judge_output_strategy",
    "pass_rule_version",
    "dataset_sha256",
    "git_revision",
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={REPO.resolve().as_posix()}", *args],
        cwd=REPO,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def committed_driver_sha256() -> str:
    """SHA-256 of the driver blob committed at HEAD (the executed source)."""
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={REPO.resolve().as_posix()}", "show", f"HEAD:{DRIVER_REL_PATH}"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("driver is not committed at HEAD")
    return hashlib.sha256(completed.stdout).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_artifacts(directory: Path) -> tuple[list[dict], dict, dict]:
    required = {
        "dialog_predictions.jsonl",
        "dialog_metrics.json",
        "run_metadata.json",
    }
    names = {path.name for path in directory.iterdir() if path.is_file()}
    if names != required:
        raise RuntimeError(f"artifact set mismatch for {directory}: {sorted(names)}")
    rows = [
        json.loads(line)
        for line in (directory / "dialog_predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    metrics = json.loads((directory / "dialog_metrics.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "run_metadata.json").read_text(encoding="utf-8"))
    return rows, metrics, metadata


def _verify_python_recompute(row: dict) -> None:
    """Field-exact recompute of every deterministic value stored per turn/case."""
    for turn in row["turns"]:
        scored = score_assessment(turn["judge"]["assessment"])
        if scored["applied_caps"] != turn["judge"]["applied_caps"]:
            raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: recompute mismatch: applied_caps")
        if scored["final_scores"] != turn["judge"]["final_scores"]:
            raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: recompute mismatch: final_scores")
        expected_pass = compute_turn_pass(
            scored["final_scores"],
            agent_failed=bool(turn["agent_failed"]),
            judge_failed=bool(turn["judge_failed"]),
            judge_skipped=bool(turn["judge_skipped"]),
        )
        if expected_pass != turn["turn_pass"]:
            raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: recompute mismatch: turn_pass")
    expected_case_pass = compute_case_pass([bool(turn["turn_pass"]) for turn in row["turns"]])
    if expected_case_pass != row["case_pass"] or expected_case_pass != row["passed"]:
        raise RuntimeError(f"{row['case_id']}: recompute mismatch: case_pass")


def verify_common(
    rows: list[dict],
    metrics: dict,
    metadata: dict,
    expected_count: int,
    execution_revision: str,
) -> None:
    if len(rows) != expected_count:
        raise RuntimeError("prediction count mismatch")
    if metrics["total_cases"] != expected_count or metadata["case_count"] != expected_count:
        raise RuntimeError("artifact case counts disagree")
    if metadata["dataset_sha256"] != EXPECTED_DATASET_SHA256:
        raise RuntimeError("dataset hash mismatch")
    if metadata["git_revision"] != execution_revision:
        raise RuntimeError("metadata Git revision mismatch")
    if metadata["agent_model"] != EXPECTED_AGENT_MODEL or metadata["judge_model"] != EXPECTED_JUDGE_MODEL:
        raise RuntimeError("model identity mismatch")
    if metadata["prompt_version"] != "dialog_judge_v5":
        raise RuntimeError("Prompt version mismatch")
    if metadata["judge_output_strategy"] != "forced_tool_then_strict_json_fallback":
        raise RuntimeError("Judge output strategy mismatch")
    if metadata["pass_rule_version"] != "dialog_pass_v5":
        raise RuntimeError("pass rule version mismatch")
    if metadata["dimension_pass_floor"] != 0.75 or metadata["overall_pass_threshold"] != 0.75:
        raise RuntimeError("pass threshold mismatch")
    if metadata["completeness_policy"] != "required_point_coverage_equal_weight_v1":
        raise RuntimeError("completeness policy mismatch")
    if metadata["violation_policy_version"] != "dialog_violation_caps_v1":
        raise RuntimeError("violation policy mismatch")
    if metadata["temperature"] != 0.0 or metadata["max_attempts"] != 3:
        raise RuntimeError("Judge runtime configuration mismatch")
    if metadata["context_mode"] != "controlled_context" or metadata["retrieval_evaluated"] is not False:
        raise RuntimeError("evaluation scope metadata mismatch")
    if compute_dialog_metrics(rows) != metrics:
        raise RuntimeError("metrics recompute mismatch")
    if metrics["agent_failed_count"] != 0 or metrics["judge_failed_count"] != 0:
        raise RuntimeError("Agent or Judge failure gate failed")
    if metrics["valid_judged_cases"] != expected_count:
        raise RuntimeError("valid judged case count mismatch")
    for row in rows:
        for turn in row["turns"]:
            if not turn.get("agent_response") or not str(turn["agent_response"]).strip():
                raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: blank Agent response")
            if turn.get("agent_failed"):
                raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: Agent failure flag set")
            if turn.get("judge_skipped") or turn.get("judge_failed"):
                raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: Judge skipped or failed")
            judge_payload = turn.get("judge") or {}
            if judge_payload.get("assessment") is None:
                raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: Judge assessment missing")
            for field in ("applied_caps", "final_scores"):
                if field not in judge_payload:
                    raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: Judge {field} missing")
            if judge_payload.get("latency_ms") is None:
                raise RuntimeError(f"{row['case_id']}/T{turn['turn_id']}: Judge latency missing")
        _verify_python_recompute(row)


def verify_warmup(warmup_dir: Path, execution_revision: str) -> None:
    rows, metrics, metadata = load_artifacts(warmup_dir)
    verify_common(rows, metrics, metadata, 1, execution_revision)
    if [row["case_id"] for row in rows] != ["dialog_eval_001"]:
        raise RuntimeError("warm-up case identity mismatch")


def verify_formal(formal_dir: Path, execution_revision: str, identity: dict) -> None:
    rows, metrics, metadata = load_artifacts(formal_dir)
    verify_common(rows, metrics, metadata, 35, execution_revision)
    if [row["case_id"] for row in rows] != EXPECTED_CASE_IDS:
        raise RuntimeError("formal case IDs/order mismatch")
    if sum(len(row["turns"]) for row in rows) != 43:
        raise RuntimeError("formal turn count mismatch")
    for key in IDENTITY_KEYS:
        if metadata[key] != identity[key]:
            raise RuntimeError(f"formal metadata {key} disagrees with pre-run identity record")


def build_evidence(rows: list[dict], metrics: dict) -> dict:
    total_turns = sum(len(row["turns"]) for row in rows)
    intent_matches = sum(bool(row["routing_audit"]["intent_match"]) for row in rows)
    agent_matches = sum(bool(row["routing_audit"]["agent_match"]) for row in rows)
    mismatches = [row["case_id"] for row in rows if not all(row["routing_audit"].values())]
    return {
        "total_cases": metrics["total_cases"],
        "total_turns": total_turns,
        "passed_cases": metrics["passed_cases"],
        "pass_rate": metrics["pass_rate"],
        "valid_judged_cases": metrics["valid_judged_cases"],
        "relevance_mean": metrics["relevance_mean"],
        "accuracy_mean": metrics["accuracy_mean"],
        "completeness_mean": metrics["completeness_mean"],
        "helpfulness_mean": metrics["helpfulness_mean"],
        "overall_mean": metrics["overall_mean"],
        "agent_failed_count": metrics["agent_failed_count"],
        "agent_failed_rate": metrics["agent_failed_rate"],
        "judge_failed_count": metrics["judge_failed_count"],
        "judge_failed_rate": metrics["judge_failed_rate"],
        "agent_latency_mean_ms": metrics["agent_latency_mean_ms"],
        "agent_latency_p50_ms": metrics["agent_latency_p50_ms"],
        "agent_latency_p95_ms": metrics["agent_latency_p95_ms"],
        "judge_latency_mean_ms": metrics["judge_latency_mean_ms"],
        "judge_latency_p50_ms": metrics["judge_latency_p50_ms"],
        "judge_latency_p95_ms": metrics["judge_latency_p95_ms"],
        "intent_routing_exact_match": intent_matches,
        "agent_routing_exact_match": agent_matches,
        "routing_mismatch_cases": mismatches,
        "routing_ambiguous_taxonomy_cases": ["dialog_eval_015", "dialog_eval_023"],
        "known_judge_semantic_variance": ["dialog_eval_024/T1", "dialog_eval_028/T2"],
    }


async def run_final(
    *,
    cases: list,
    warmup_dir: Path,
    formal_dir: Path,
    dataset_sha256: str,
    config: dict,
    identity: dict,
    create_dependencies,
    run_phase,
) -> dict:
    """Run warm-up and formal phases behind every frozen gate.

    All identity and directory checks happen before ``create_dependencies``
    is called, so a failed preflight makes zero API calls.  The warm-up
    hard gate is ``verify_warmup``; the formal phase starts only after it
    passes.  This function never resumes, overwrites or appends.
    """
    if warmup_dir.exists():
        raise FileExistsError(f"warm-up output path already exists: {warmup_dir}")
    if formal_dir.exists():
        raise FileExistsError(f"formal output path already exists: {formal_dir}")
    if config.get("agent_model") != EXPECTED_AGENT_MODEL:
        raise RuntimeError("resolved agent model is not the exact expected model")
    if config.get("judge_model") != EXPECTED_JUDGE_MODEL:
        raise RuntimeError("resolved judge model is not the exact expected model")
    for key, expected in (
        ("prompt_version", PROMPT_VERSION),
        ("judge_output_strategy", JUDGE_OUTPUT_STRATEGY),
        ("pass_rule_version", PASS_RULE_VERSION),
        ("dimension_pass_floor", DIMENSION_PASS_FLOOR),
        ("overall_pass_threshold", OVERALL_PASS_THRESHOLD),
        ("completeness_policy", COMPLETENESS_POLICY_VERSION),
        ("violation_policy_version", VIOLATION_POLICY_VERSION),
    ):
        if identity.get(key) != expected:
            raise RuntimeError(f"identity {key} is not the frozen value")
    if dataset_sha256 != EXPECTED_DATASET_SHA256:
        raise RuntimeError("dataset SHA-256 changed")
    if len(cases) != 35 or sum(len(case["turns"]) for case in cases) != 43:
        raise RuntimeError("dataset must contain 35 cases and 43 turns")

    dependencies = create_dependencies()

    await run_phase(dependencies, cases[:1], warmup_dir)
    verify_warmup(warmup_dir, identity["git_revision"])

    formal_identity = dict(identity)
    formal_identity["recorded_at"] = _utc_now()
    formal_identity["recorded_before"] = "formal 35-case run"
    formal_identity["warmup_case_id"] = "dialog_eval_001"
    formal_identity["warmup_valid_judged_cases"] = 1
    (warmup_dir / "formal_model_identity.json").write_text(
        json.dumps(formal_identity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    await run_phase(dependencies, cases, formal_dir)
    verify_formal(formal_dir, identity["git_revision"], identity)
    rows, metrics, _ = load_artifacts(formal_dir)
    return build_evidence(rows, metrics)


async def _run_phase(dependencies, cases, output_dir, config, dataset_path, dataset_sha256):
    orchestrator, judge = dependencies
    await run_evaluation(
        cases=cases,
        output_dir=output_dir,
        orchestrator=orchestrator,
        judge=judge,
        config=config,
        dataset_path=dataset_path,
        dataset_sha256=dataset_sha256,
    )


async def main() -> None:
    if Path(__file__).resolve().parent != (REPO / "data/eval/runs").resolve():
        raise RuntimeError("driver must remain under data/eval/runs")
    if WARMUP_DIR.exists() or FORMAL_DIR.exists():
        raise FileExistsError("warm-up or formal output path already exists")
    if PROMPT_VERSION != "dialog_judge_v5":
        raise RuntimeError("current Prompt version is not dialog_judge_v5")
    if JUDGE_OUTPUT_STRATEGY != "forced_tool_then_strict_json_fallback":
        raise RuntimeError("current Judge strategy is not the frozen transport")
    if PASS_RULE_VERSION != "dialog_pass_v5":
        raise RuntimeError("current pass rule version is not dialog_pass_v5")
    if DIMENSION_PASS_FLOOR != 0.75 or OVERALL_PASS_THRESHOLD != 0.75:
        raise RuntimeError("current pass thresholds are not frozen")
    if git("diff", "--quiet", check=False).returncode != 0:
        raise RuntimeError("tracked working tree is not clean")
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        raise RuntimeError("index is not clean")
    execution_revision = git("rev-parse", "HEAD").stdout.strip()
    driver_sha256 = committed_driver_sha256()

    # Credentials come exclusively from the project .env; shell env cannot
    # silently change the formal Agent/Judge model identity.
    project_env = {
        key: value
        for key, value in dotenv_values(REPO / ".env").items()
        if isinstance(value, str)
    }
    args = SimpleNamespace(
        base_url=None,
        agent_model=EXPECTED_AGENT_MODEL,
        judge_model=EXPECTED_JUDGE_MODEL,
    )
    config = resolve_config(args, project_env)
    if config["agent_model"] != EXPECTED_AGENT_MODEL or config["judge_model"] != EXPECTED_JUDGE_MODEL:
        raise RuntimeError("resolved models are not the exact expected models")
    if not config["base_url"]:
        raise RuntimeError("project .env base URL is missing")

    cases, dataset_sha256 = _load_validated_dataset(DATASET)
    if dataset_sha256 != EXPECTED_DATASET_SHA256:
        raise RuntimeError("dataset SHA-256 changed")
    if len(cases) != 35 or sum(len(case["turns"]) for case in cases) != 43:
        raise RuntimeError("dataset must contain 35 cases and 43 turns")

    identity = {
        "recorded_at": _utc_now(),
        "git_revision": execution_revision,
        "driver_sha256": driver_sha256,
        "dataset_path": str(DATASET),
        "dataset_sha256": dataset_sha256,
        "expected_cases": 35,
        "expected_turns": 43,
        "agent_model": EXPECTED_AGENT_MODEL,
        "judge_model": EXPECTED_JUDGE_MODEL,
        "prompt_version": PROMPT_VERSION,
        "judge_output_strategy": JUDGE_OUTPUT_STRATEGY,
        "pass_rule_version": PASS_RULE_VERSION,
        "dimension_pass_floor": DIMENSION_PASS_FLOOR,
        "overall_pass_threshold": OVERALL_PASS_THRESHOLD,
        "completeness_policy": COMPLETENESS_POLICY_VERSION,
        "violation_policy_version": VIOLATION_POLICY_VERSION,
        "temperature": JUDGE_TEMPERATURE,
        "thinking": "disabled",
        "judge_max_attempts": JUDGE_MAX_ATTEMPTS,
        "judge_timeout_seconds": JUDGE_TIMEOUT_SECONDS,
        "warmup_dir": str(WARMUP_DIR),
        "formal_dir": str(FORMAL_DIR),
    }
    print("MODEL_IDENTITY_RECORD\n" + json.dumps(identity, ensure_ascii=False, indent=2))

    evidence = await run_final(
        cases=cases,
        warmup_dir=WARMUP_DIR,
        formal_dir=FORMAL_DIR,
        dataset_sha256=dataset_sha256,
        config=config,
        identity=identity,
        create_dependencies=lambda: _create_dependencies(config),
        run_phase=lambda dependencies, phase_cases, output_dir: _run_phase(
            dependencies, phase_cases, output_dir, config, DATASET, dataset_sha256
        ),
    )
    print("FORMAL_EVIDENCE\n" + json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

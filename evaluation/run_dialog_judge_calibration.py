"""Frozen-answer offline calibration for dialog judge v5.

Replays the frozen v4 Agent responses against the v5 judge and checks every
turn against the frozen 10-case / 14-turn oracle.  Agent API calls are
exactly zero: this driver never imports, accepts or invokes the agent
orchestrator.  The output directory must not exist; calibration never
resumes, overwrites or appends.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from evaluation.dialog_judge import (
    JUDGE_OUTPUT_STRATEGY,
    PROMPT_VERSION,
    DialogJudge,
    sanitize_error,
)
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

JUDGE_TEMPERATURE = 0.0
JUDGE_TIMEOUT_SECONDS = 30.0
JUDGE_MAX_ATTEMPTS = 3
EXPECTED_JUDGE_MODEL = "deepseek-v4-pro"

CALIBRATION_CASE_IDS = [
    "dialog_eval_001",
    "dialog_eval_018",
    "dialog_eval_019",
    "dialog_eval_024",
    "dialog_eval_025",
    "dialog_eval_026",
    "dialog_eval_028",
    "dialog_eval_031",
    "dialog_eval_033",
    "dialog_eval_034",
]

EXPECTED_CASE_PASS = {
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

# Frozen per-turn oracle.  True turns must additionally satisfy every final
# dimension >= 0.75, and dimensions capped at 0.75 must land on exactly 0.75.
TURN_ORACLE = {
    ("dialog_eval_001", 1): {
        "coverage": ["partial"],
        "required_violations": [],
        "final_exact": {"completeness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_018", 1): {
        "coverage": ["covered", "covered", "covered"],
        "required_violations": [
            "unsupported_operation",
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
            "sensitive_request_without_safety",
        ],
        "final_at_most": {"helpfulness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_019", 1): {
        "coverage": ["covered", "covered", "covered"],
        "required_violations": [
            "unsupported_operation",
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
            "sensitive_request_without_safety",
        ],
        "final_at_most": {"helpfulness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_024", 1): {
        "coverage": ["covered", "covered", "missing"],
        "required_violations": [
            "unsupported_operation",
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
        ],
        "final_exact": {"completeness": 2 / 3},
        "turn_pass": False,
    },
    ("dialog_eval_025", 1): {
        "coverage": ["partial", "covered", "covered"],
        "required_violations": ["false_completed_action"],
        "final_at_most": {"accuracy": 0.5, "helpfulness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_026", 1): {
        "coverage": ["covered", "covered"],
        "required_violations": ["unsupported_operation"],
        "final_exact": {"accuracy": 0.75, "helpfulness": 0.75},
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_026", 2): {
        "coverage": ["covered", "covered"],
        "required_violations": ["false_completed_action"],
        "final_at_most": {"accuracy": 0.5, "helpfulness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_026", 3): {
        "coverage": ["covered", "covered"],
        "required_violations": ["unsupported_operation"],
        "final_exact": {"accuracy": 0.75, "helpfulness": 0.75},
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_028", 1): {
        "coverage": ["covered", "covered"],
        "required_violations": [],
        "no_caps": True,
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_028", 2): {
        "coverage": ["partial", "covered"],
        "required_violations": [
            "unsupported_operation",
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
        ],
        "final_exact": {"completeness": 0.75, "accuracy": 0.75, "helpfulness": 0.75},
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_028", 3): {
        "coverage": ["covered", "covered"],
        "required_violations": [
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
        ],
        "final_exact": {"accuracy": 0.75},
        "final_at_least": {"relevance": 0.75, "completeness": 0.75, "helpfulness": 0.75},
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
    ("dialog_eval_031", 1): {
        "coverage": ["covered", "covered", "covered", "covered"],
        "required_violations": [
            "unsupported_operation",
            "unsupported_process_or_requirement",
            "sensitive_request_without_safety",
        ],
        "final_at_most": {"helpfulness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_033", 1): {
        "coverage": ["covered", "covered", "covered"],
        "required_violations": [
            "false_completed_action",
            "unsupported_process_or_requirement",
            "misleading_unsupported_content",
        ],
        "final_at_most": {"accuracy": 0.5, "helpfulness": 0.5},
        "turn_pass": False,
    },
    ("dialog_eval_034", 1): {
        "coverage": ["covered", "partial", "covered"],
        "required_violations": ["unsupported_operation"],
        "final_exact": {"completeness": 5 / 6, "accuracy": 0.75, "helpfulness": 0.75},
        "all_dimensions_at_least": 0.75,
        "turn_pass": True,
    },
}

EXPECTED_TURN_COUNTS = {
    case_id: max(turn for (other, turn) in TURN_ORACLE if other == case_id)
    for case_id in CALIBRATION_CASE_IDS
}

FORBIDDEN_REASONING_SUBSTRINGS = (
    "overall",
    "final_scores",
    "turn_pass",
    "case_pass",
    "pass rate",
    "final score",
)
FORBIDDEN_REASONING_WORDS = ("cap", "capped")
SCORE_NUMBER_RE = re.compile(r"0?\.\d+")


def check_reasoning_conflict(
    reasoning_summary: str,
    violations: Iterable[Mapping[str, object]],
    coverage_statuses: Iterable[str],
) -> bool:
    """Detect obvious conflicts between the reasoning text and structural fields."""
    lowered = reasoning_summary.lower()
    if any(token in lowered for token in FORBIDDEN_REASONING_SUBSTRINGS):
        return True
    words = [word for word in re.split(r"[^a-z0-9.]+", lowered) if word]
    if any(word in FORBIDDEN_REASONING_WORDS for word in words):
        return True
    if any(SCORE_NUMBER_RE.fullmatch(word) for word in words):
        return True
    if list(violations) and "no violation" in lowered:
        return True
    if "all required points" in lowered and any(status != "covered" for status in coverage_statuses):
        return True
    return False


def _check_turn_oracle(
    case_id: str,
    turn_index: int,
    assessment: Mapping[str, object],
    final_scores: Mapping[str, float],
    applied_caps: Mapping[str, float],
    turn_pass: bool,
) -> List[str]:
    oracle = TURN_ORACLE[(case_id, turn_index)]
    failures = []
    actual_statuses = [entry["status"] for entry in assessment["required_point_coverage"]]
    if actual_statuses != oracle["coverage"]:
        failures.append(f"coverage mismatch: {actual_statuses} != {oracle['coverage']}")
    actual_codes = [violation["code"] for violation in assessment["violations"]]
    required = oracle.get("required_violations", [])
    missing = sorted(set(required) - set(actual_codes))
    if missing:
        failures.append(f"missing required violations: {missing}")
    extra = sorted(code for code in actual_codes if code not in required)
    if extra:
        failures.append(f"unexpected extra violations: {extra}")
    for name, expected in oracle.get("final_exact", {}).items():
        if final_scores[name] != expected:
            failures.append(f"final_{name} {final_scores[name]!r} != {expected!r}")
    for name, ceiling in oracle.get("final_at_most", {}).items():
        if final_scores[name] > ceiling:
            failures.append(f"final_{name} {final_scores[name]!r} > {ceiling!r}")
    for name, floor in oracle.get("final_at_least", {}).items():
        if final_scores[name] < floor:
            failures.append(f"final_{name} {final_scores[name]!r} < {floor!r}")
    floor = oracle.get("all_dimensions_at_least")
    if floor is not None:
        for name in ("relevance", "accuracy", "completeness", "helpfulness"):
            if final_scores[name] < floor:
                failures.append(f"final_{name} {final_scores[name]!r} below floor {floor!r}")
    if oracle.get("no_caps") and applied_caps:
        failures.append(f"no caps expected but applied_caps={applied_caps!r}")
    if turn_pass != oracle["turn_pass"]:
        failures.append(f"turn_pass {turn_pass!r} != {oracle['turn_pass']!r}")
    return failures


def _verify_python_recompute(
    assessment: Mapping[str, object],
    applied_caps: Mapping[str, float],
    final_scores: Mapping[str, float],
) -> List[str]:
    mismatches = []
    recomputed = score_assessment(assessment)
    if recomputed["applied_caps"] != dict(applied_caps):
        mismatches.append("python recompute mismatch: applied_caps")
    if recomputed["final_scores"] != dict(final_scores):
        mismatches.append("python recompute mismatch: final_scores")
    return mismatches


def _select_calibration_cases(cases: Iterable[Mapping[str, object]]) -> List[Mapping[str, object]]:
    by_id = {}
    for case in cases:
        case_id = case.get("case_id")
        if case_id in CALIBRATION_CASE_IDS:
            by_id[case_id] = case
    missing = sorted(set(CALIBRATION_CASE_IDS) - set(by_id))
    if missing:
        raise ValueError(f"calibration cases missing from dataset: {missing}")
    selected = [by_id[case_id] for case_id in CALIBRATION_CASE_IDS]
    for case in selected:
        case_id = case["case_id"]
        turns = case.get("turns")
        if not isinstance(turns, list) or len(turns) != EXPECTED_TURN_COUNTS[case_id]:
            raise ValueError(
                f"expected {EXPECTED_TURN_COUNTS[case_id]} turns for {case_id}, "
                f"found {len(turns) if isinstance(turns, list) else turns!r}"
            )
        for turn in turns:
            required_points = turn.get("required_points")
            if not isinstance(required_points, list) or not required_points:
                raise ValueError(f"{case_id}: required_points must be a non-empty list")
    total_turns = sum(len(case["turns"]) for case in selected)
    if len(selected) != 10 or total_turns != 14:
        raise ValueError(f"expected 10 cases / 14 turns, found {len(selected)} / {total_turns}")
    return selected


def _frozen_responses(
    selected_cases: Iterable[Mapping[str, object]],
    predictions: Iterable[Mapping[str, object]],
) -> Dict[str, List[str]]:
    by_id = {row.get("case_id"): row for row in predictions}
    responses = {}
    for case in selected_cases:
        case_id = case["case_id"]
        row = by_id.get(case_id)
        if row is None:
            raise ValueError(f"predictions missing case: {case_id}")
        turns = row.get("turns")
        if not isinstance(turns, list) or len(turns) != len(case["turns"]):
            raise ValueError(f"predictions turn count mismatch for {case_id}")
        agent_responses = [turn.get("agent_response") for turn in turns]
        if any(response is None for response in agent_responses):
            raise ValueError(f"predictions missing agent_response for {case_id}")
        responses[case_id] = [str(response) for response in agent_responses]
    return responses


def load_calibration_inputs(
    dialog_data_path: Path,
    predictions_path: Path,
    metadata_path: Path,
) -> Tuple[List[Mapping[str, object]], List[Mapping[str, object]], Dict[str, object], str, str]:
    """Load the frozen dataset, v4 predictions and v4 metadata with their SHA-256."""
    dataset_bytes = dialog_data_path.read_bytes()
    cases = json.loads(dataset_bytes.decode("utf-8"))
    predictions_bytes = predictions_path.read_bytes()
    predictions = [
        json.loads(line)
        for line in predictions_bytes.decode("utf-8").splitlines()
        if line.strip()
    ]
    metadata = json.loads(metadata_path.read_bytes().decode("utf-8"))
    return (
        cases,
        predictions,
        metadata,
        hashlib.sha256(dataset_bytes).hexdigest(),
        hashlib.sha256(predictions_bytes).hexdigest(),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


async def run_calibration(
    *,
    cases: List[Mapping[str, object]],
    predictions: List[Mapping[str, object]],
    metadata: Mapping[str, object],
    judge: object,
    output_dir: Path,
    dataset_sha256: str,
    predictions_sha256: str,
    git_revision: Optional[str],
    dataset_path: Optional[Path] = None,
    source_predictions_path: Optional[Path] = None,
    source_metadata_path: Optional[Path] = None,
) -> Dict[str, object]:
    """Judge the frozen answers for the 10 calibration cases and check the oracle."""
    if output_dir.exists():
        raise FileExistsError(f"calibration output directory already exists: {output_dir}")
    judge_model = metadata.get("judge_model")
    if judge_model != EXPECTED_JUDGE_MODEL:
        raise ValueError(
            f"expected judge model {EXPECTED_JUDGE_MODEL!r}, found {judge_model!r}"
        )
    selected = _select_calibration_cases(cases)
    frozen_responses = _frozen_responses(selected, predictions)
    started_at = _utc_now()
    output_dir.mkdir(parents=True)

    completed_cases: List[Dict[str, object]] = []
    failures: List[str] = []
    judge_api_calls = 0
    judge_failed_count = 0
    oracle_failed_turns = 0
    manual_review_failed_turns = 0
    case_pass_map: Dict[str, bool] = {}
    case_pass_match = True
    unexpected_error: Optional[str] = None

    try:
        for case in selected:
            case_id = case["case_id"]
            turn_results = []
            history: List[Dict[str, str]] = []
            for turn_index, turn in enumerate(case["turns"], 1):
                response = frozen_responses[case_id][turn_index - 1]
                judge_result = dict(await judge.judge_turn(
                    question=turn["user_message"],
                    response=response,
                    context=case.get("context", ""),
                    reference_answer=turn["reference_answer"],
                    required_points=turn["required_points"],
                    history=list(history),
                ))
                judge_api_calls += int(judge_result.get("judge_attempts") or 0)
                turn_pass = False
                assessment = None
                applied_caps = None
                final_scores = None
                oracle_failures: List[str] = []
                reasoning_conflict = False
                if judge_result.get("judge_failed"):
                    judge_failed_count += 1
                    error = judge_result.get("judge_error")
                    if error is not None:
                        judge_result["judge_error"] = sanitize_error(
                            RuntimeError(str(error))
                        )
                    oracle_failures.append(
                        f"judge failed: {judge_result.get('judge_error')}"
                    )
                else:
                    judge_payload = judge_result.get("judge") or {}
                    assessment = judge_payload.get("assessment")
                    if assessment is None:
                        oracle_failures.append("judge returned no assessment")
                    else:
                        scored = score_assessment(assessment)
                        applied_caps = scored["applied_caps"]
                        final_scores = scored["final_scores"]
                        turn_pass = compute_turn_pass(
                            final_scores,
                            agent_failed=False,
                            judge_failed=False,
                            judge_skipped=False,
                        )
                        oracle_failures.extend(_check_turn_oracle(
                            case_id,
                            turn_index,
                            assessment,
                            final_scores,
                            applied_caps,
                            turn_pass,
                        ))
                        oracle_failures.extend(_verify_python_recompute(
                            assessment, applied_caps, final_scores
                        ))
                        reasoning_conflict = check_reasoning_conflict(
                            assessment["reasoning_summary"],
                            assessment["violations"],
                            [entry["status"] for entry in assessment["required_point_coverage"]],
                        )
                if oracle_failures:
                    oracle_failed_turns += 1
                    failures.extend(
                        f"{case_id}/T{turn_index}: {message}" for message in oracle_failures
                    )
                if reasoning_conflict:
                    manual_review_failed_turns += 1
                    failures.append(
                        f"{case_id}/T{turn_index}: reasoning_summary conflicts with structural fields"
                    )
                turn_results.append({
                    "turn_id": turn_index,
                    "judge_attempts": judge_result.get("judge_attempts", 0),
                    "judge_failed": bool(judge_result.get("judge_failed")),
                    "judge_error": judge_result.get("judge_error"),
                    "assessment": assessment,
                    "applied_caps": applied_caps,
                    "final_scores": final_scores,
                    "turn_pass": turn_pass,
                    "oracle": TURN_ORACLE[(case_id, turn_index)],
                    "oracle_failures": oracle_failures,
                    "oracle_match": not oracle_failures,
                    "reasoning_conflict": reasoning_conflict,
                })
                history.extend((
                    {"role": "user", "content": str(turn["user_message"])},
                    {"role": "assistant", "content": response},
                ))
            case_pass = compute_case_pass([turn["turn_pass"] for turn in turn_results])
            expected_case_pass = EXPECTED_CASE_PASS[case_id]
            matched = case_pass is expected_case_pass
            case_pass_map[case_id] = case_pass
            if not matched:
                case_pass_match = False
                failures.append(
                    f"{case_id}: case_pass {case_pass!r} != expected {expected_case_pass!r}"
                )
            completed_cases.append({
                "case_id": case_id,
                "turns": turn_results,
                "case_pass": case_pass,
                "case_pass_expected": expected_case_pass,
                "case_pass_match": matched,
                "oracle_match": matched and all(
                    turn["oracle_match"] and not turn["reasoning_conflict"]
                    for turn in turn_results
                ),
            })
    except Exception as exc:  # keep the directory and the evidence collected so far
        unexpected_error = sanitize_error(exc)
        failures.append(f"calibration aborted: {unexpected_error}")

    completed_at = _utc_now()
    calibration_passed = (
        judge_failed_count == 0
        and oracle_failed_turns == 0
        and manual_review_failed_turns == 0
        and case_pass_match
        and unexpected_error is None
    )
    summary = {
        "calibration_passed": calibration_passed,
        "case_count": len(case_pass_map),
        "turn_count": sum(len(case["turns"]) for case in completed_cases) if completed_cases else 14,
        "agent_api_calls": 0,
        "judge_api_calls": judge_api_calls,
        "judge_failed_count": judge_failed_count,
        "oracle_failed_turns": oracle_failed_turns,
        "manual_review_failed_turns": manual_review_failed_turns,
        "case_pass": case_pass_map,
        "case_pass_match": case_pass_match,
        "failures": failures,
    }
    metadata_out = {
        "dataset_path": str(dataset_path) if dataset_path else None,
        "dataset_sha256": dataset_sha256,
        "source_predictions_path": str(source_predictions_path) if source_predictions_path else None,
        "source_predictions_sha256": predictions_sha256,
        "source_metadata_path": str(source_metadata_path) if source_metadata_path else None,
        "git_revision": git_revision,
        "judge_model": judge_model,
        "prompt_version": PROMPT_VERSION,
        "judge_output_strategy": JUDGE_OUTPUT_STRATEGY,
        "pass_rule_version": PASS_RULE_VERSION,
        "dimension_pass_floor": DIMENSION_PASS_FLOOR,
        "overall_pass_threshold": OVERALL_PASS_THRESHOLD,
        "completeness_policy": COMPLETENESS_POLICY_VERSION,
        "violation_policy_version": VIOLATION_POLICY_VERSION,
        "temperature": JUDGE_TEMPERATURE,
        "max_attempts": JUDGE_MAX_ATTEMPTS,
        "agent_api_calls": 0,
        "case_count": 10,
        "turn_count": 14,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    with (output_dir / "calibration_results.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for case_record in completed_cases:
            handle.write(json.dumps(case_record, ensure_ascii=False) + "\n")
    _atomic_write_json(output_dir / "run_metadata.json", metadata_out)
    _atomic_write_json(output_dir / "calibration_summary.json", summary)
    return summary


class _SafeArgumentParser(argparse.ArgumentParser):
    """Reject forbidden credential arguments without reflecting their values."""

    def parse_args(self, args: Optional[List[str]] = None, namespace: object = None) -> argparse.Namespace:
        supplied_args = sys.argv[1:] if args is None else args
        if any(argument == "--api-key" or argument.startswith("--api-key=") for argument in supplied_args):
            self.error("--api-key is not supported; configure ANTHROPIC_API_KEY in environment or .env")
        return super().parse_args(args, namespace)


def build_parser() -> argparse.ArgumentParser:
    """Build the credential-free calibration CLI."""
    parser = _SafeArgumentParser(description="Run the frozen-answer judge v5 calibration.")
    parser.add_argument("--dialog-data", type=Path, required=True)
    parser.add_argument("--source-predictions", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def _load_environment() -> None:
    from dotenv import load_dotenv

    load_dotenv()


def _create_judge(judge_model: str) -> Tuple[object, Tuple[str, ...]]:
    """Create an independent judge client; the Agent orchestrator is never touched."""
    from anthropic import AsyncAnthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
    client_options = {"api_key": api_key}
    if base_url:
        client_options["base_url"] = base_url
    judge = DialogJudge(
        AsyncAnthropic(**client_options),
        str(judge_model),
        timeout_seconds=JUDGE_TIMEOUT_SECONDS,
        max_attempts=JUDGE_MAX_ATTEMPTS,
        secrets=(api_key,),
    )
    return judge, (api_key,)


def _get_git_revision(repo: Path) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={repo.resolve().as_posix()}", "rev-parse", "HEAD"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    revision = completed.stdout.strip()
    return revision or None


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_dir.exists():
        print(f"calibration output directory already exists: {args.output_dir}", file=sys.stderr)
        return 1
    try:
        _load_environment()
        cases, predictions, metadata, dataset_sha256, predictions_sha256 = load_calibration_inputs(
            args.dialog_data, args.source_predictions, args.source_metadata
        )
        judge_model = metadata.get("judge_model")
        if judge_model != EXPECTED_JUDGE_MODEL:
            raise ValueError(
                f"expected judge model {EXPECTED_JUDGE_MODEL!r}, found {judge_model!r}"
            )
        judge, _ = _create_judge(judge_model)
        summary = asyncio.run(run_calibration(
            cases=cases,
            predictions=predictions,
            metadata=metadata,
            judge=judge,
            output_dir=args.output_dir,
            dataset_sha256=dataset_sha256,
            predictions_sha256=predictions_sha256,
            git_revision=_get_git_revision(Path(__file__).resolve().parent.parent),
            dataset_path=args.dialog_data,
            source_predictions_path=args.source_predictions,
            source_metadata_path=args.source_metadata,
        ))
        return 0 if summary["calibration_passed"] else 1
    except Exception as exc:
        print(sanitize_error(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

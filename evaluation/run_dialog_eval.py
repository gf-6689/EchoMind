"""Shared dataset loading and validation for dialog evaluation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from agents.agent_orchestrator import Request
from evaluation.dialog_judge import (
    DialogJudge,
    JUDGE_OUTPUT_STRATEGY,
    PROMPT_VERSION,
    sanitize_error,
)
from evaluation.dialog_metrics import aggregate_case_scores, compute_dialog_metrics
from .intent_metrics import INTENT_LABELS


PASS_THRESHOLD = 0.75
JUDGE_TEMPERATURE = 0.0
JUDGE_TIMEOUT_SECONDS = 30.0
JUDGE_MAX_ATTEMPTS = 3


_CASE_FIELDS = {
    "case_id",
    "category",
    "description",
    "context",
    "turns",
    "expected_routing",
}
_TURN_FIELDS = {"user_message", "reference_answer", "required_points"}
_ROUTING_FIELDS = {"intent", "agent_type"}
_AGENT_TYPES = {"general", "technical", "billing", "escalation"}


def _require_exact_fields(value: object, fields: set[str], location: str) -> Dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{location}: must be an object")
    actual_fields = set(value)
    missing = fields - actual_fields
    extra = actual_fields - fields
    if missing:
        raise ValueError(f"{location}: missing fields {sorted(missing)}")
    if extra:
        raise ValueError(f"{location}: unexpected fields {sorted(extra)}")
    return value


def _require_string(value: object, location: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{location}: must be a string")
    if nonempty and not value.strip():
        raise ValueError(f"{location}: must be non-empty")
    return value


def validate_cases(cases: object, expected_count: Optional[int] = None) -> None:
    """Validate the fixed dialog-case schema used by all evaluation runners."""
    if not isinstance(cases, list):
        raise ValueError("dialog cases: top level must be a list")
    if expected_count is not None and len(cases) != expected_count:
        raise ValueError(f"expected {expected_count} cases, found {len(cases)}")

    seen_case_ids = set()
    for case_number, raw_case in enumerate(cases, 1):
        location = f"case {case_number}"
        case = _require_exact_fields(raw_case, _CASE_FIELDS, location)
        case_id = _require_string(case["case_id"], f"{location}.case_id", nonempty=True)
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)

        _require_string(case["category"], f"{location}.category", nonempty=True)
        _require_string(case["description"], f"{location}.description", nonempty=True)
        _require_string(case["context"], f"{location}.context")

        turns = case["turns"]
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"{location}.turns: must be a non-empty list")
        for turn_number, raw_turn in enumerate(turns, 1):
            turn_location = f"{location}.turns[{turn_number}]"
            turn = _require_exact_fields(raw_turn, _TURN_FIELDS, turn_location)
            _require_string(turn["user_message"], f"{turn_location}.user_message", nonempty=True)
            _require_string(turn["reference_answer"], f"{turn_location}.reference_answer", nonempty=True)
            required_points = turn["required_points"]
            if not isinstance(required_points, list) or not required_points:
                raise ValueError(f"{turn_location}.required_points: must be a non-empty list")
            for point_number, point in enumerate(required_points, 1):
                _require_string(
                    point,
                    f"{turn_location}.required_points[{point_number}]",
                    nonempty=True,
                )

        routing = _require_exact_fields(
            case["expected_routing"], _ROUTING_FIELDS, f"{location}.expected_routing"
        )
        intent = _require_string(routing["intent"], f"{location}.expected_routing.intent")
        if intent not in INTENT_LABELS:
            raise ValueError(f"{location}.expected_routing.intent: unknown intent {intent!r}")
        agent_type = _require_string(
            routing["agent_type"], f"{location}.expected_routing.agent_type"
        )
        if agent_type not in _AGENT_TYPES:
            raise ValueError(
                f"{location}.expected_routing.agent_type: unknown agent type {agent_type!r}"
            )


def load_and_validate(
    path: Path, expected_count: Optional[int] = None
) -> List[Dict[str, object]]:
    cases, _ = _load_validated_dataset(path, expected_count=expected_count)
    return cases


def _load_validated_dataset(
    path: Path, expected_count: Optional[int] = None
) -> tuple[List[Dict[str, object]], str]:
    dataset_bytes = path.read_bytes()
    cases = json.loads(dataset_bytes.decode("utf-8"))
    validate_cases(cases, expected_count=expected_count)
    return cases, hashlib.sha256(dataset_bytes).hexdigest()


def build_controlled_context(context: object) -> str:
    """Return only the case-supplied evaluation context."""
    return str(context)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def routing_audit(expected: Mapping[str, object], first_turn: Mapping[str, object]) -> Dict[str, bool]:
    return {
        "intent_match": first_turn.get("intent") == expected.get("intent"),
        "agent_match": first_turn.get("primary_agent") == expected.get("agent_type"),
    }


def _summarize_case_errors(
    turns: Iterable[Mapping[str, object]], failure_key: str, error_key: str
) -> Optional[str]:
    summaries = [
        f"turn {turn['turn_id']}: {turn[error_key]}"
        for turn in turns
        if turn.get(failure_key) and turn.get(error_key)
    ]
    return "; ".join(summaries) or None


async def evaluate_case(
    case: Mapping[str, object],
    orchestrator: object,
    judge: object,
    user_id: str = "eval-user",
    secrets: Iterable[str] = (),
) -> Dict[str, object]:
    """Run and independently judge every turn in one validated dialog case."""
    conv_id = str(uuid4())
    history: List[Dict[str, str]] = []
    turn_results = []
    prior_agent_failure = False
    for turn_index, turn in enumerate(case["turns"], 1):
        if prior_agent_failure:
            turn_results.append({
                "turn_id": turn_index,
                "user_message": turn["user_message"],
                "agent_response": None,
                "intent": None,
                "primary_agent": None,
                "supporting_agents": [],
                "routing_reason": None,
                "routing_confidence": None,
                "escalated": None,
                "agent_latency_ms": None,
                "agent_failed": False,
                "agent_error": "skipped after prior agent failure",
                "judge_failed": False,
                "judge_error": None,
                "judge_skipped": True,
                "judge_attempts": 0,
                "judge": None,
            })
            continue
        request = Request(
            message=turn["user_message"],
            user_id=user_id,
            conv_id=conv_id,
            context=build_controlled_context(case["context"]),
            history=list(history[-5:]),
        )
        agent_started = time.monotonic()
        try:
            result = await orchestrator.run(request)
        except Exception as exc:
            agent_latency_ms = (time.monotonic() - agent_started) * 1000
            turn_results.append({
                "turn_id": turn_index,
                "user_message": turn["user_message"],
                "agent_response": None,
                "intent": None,
                "primary_agent": None,
                "supporting_agents": [],
                "routing_reason": None,
                "routing_confidence": None,
                "escalated": None,
                "agent_latency_ms": agent_latency_ms,
                "agent_failed": True,
                "agent_error": sanitize_error(exc, secrets),
                "judge_failed": False,
                "judge_error": None,
                "judge_skipped": True,
                "judge_attempts": 0,
                "judge": None,
            })
            prior_agent_failure = True
            continue
        primary_agent = result.primary_agent or result.agent_type
        turn_result = {
            "turn_id": turn_index,
            "user_message": turn["user_message"],
            "agent_response": result.response,
            "intent": _enum_value(result.intent),
            "primary_agent": _enum_value(primary_agent),
            "supporting_agents": [_enum_value(item) for item in result.supporting_agents],
            "routing_reason": result.routing_reason,
            "routing_confidence": result.routing_confidence,
            "escalated": result.escalated,
            "agent_latency_ms": result.latency_ms,
            "agent_failed": not result.success,
            "agent_error": (
                None
                if result.success
                else sanitize_error(
                    RuntimeError(result.error or "agent returned unsuccessful result"),
                    secrets,
                )
            ),
        }
        if not result.success:
            turn_result.update({
                "judge_failed": False,
                "judge_error": None,
                "judge_skipped": True,
                "judge_attempts": 0,
                "judge": None,
            })
            turn_results.append(turn_result)
            prior_agent_failure = True
            continue
        judge_result = dict(await judge.judge_turn(
            question=turn["user_message"],
            response=result.response,
            context=request.context,
            reference_answer=turn["reference_answer"],
            required_points=turn["required_points"],
            history=list(history),
        ))
        if judge_result.get("judge_error") is not None:
            judge_result["judge_error"] = sanitize_error(
                RuntimeError(str(judge_result["judge_error"])), secrets
            )
        turn_result.update(judge_result)
        turn_results.append(turn_result)
        history.extend((
            {"role": "user", "content": turn["user_message"]},
            {"role": "assistant", "content": result.response},
        ))

    case_scores = aggregate_case_scores(turn_results)
    expected_routing = dict(case["expected_routing"])
    agent_failed = any(turn["agent_failed"] for turn in turn_results)
    judge_failed = any(
        turn["judge_failed"] for turn in turn_results if not turn["judge_skipped"]
    )
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "description": case["description"],
        "conv_id": conv_id,
        "expected_routing": expected_routing,
        "turns": turn_results,
        "agent_failed": agent_failed,
        "agent_error": _summarize_case_errors(turn_results, "agent_failed", "agent_error"),
        "judge_failed": judge_failed,
        "judge_error": _summarize_case_errors(turn_results, "judge_failed", "judge_error"),
        "judge_skipped": any(turn["judge_skipped"] for turn in turn_results),
        "case_scores": case_scores,
        "passed": case_scores["overall"] >= PASS_THRESHOLD if case_scores is not None else None,
        "routing_audit": routing_audit(expected_routing, turn_results[0]),
    }


def _positive_int(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit must be a positive integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("--limit must be a positive integer")
    return value


class _SafeArgumentParser(argparse.ArgumentParser):
    """Reject forbidden credential arguments without reflecting their values."""

    def parse_args(self, args: Optional[List[str]] = None, namespace: object = None) -> argparse.Namespace:
        supplied_args = sys.argv[1:] if args is None else args
        if any(argument == "--api-key" or argument.startswith("--api-key=") for argument in supplied_args):
            self.error("--api-key is not supported; configure ANTHROPIC_API_KEY in environment or .env")
        return super().parse_args(args, namespace)


def build_parser() -> argparse.ArgumentParser:
    """Build the deliberately small, credential-free dialog-evaluation CLI."""
    parser = _SafeArgumentParser(description="Run the dialog evaluation dataset.")
    parser.add_argument("--dialog-data", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=_positive_int)
    parser.add_argument("--base-url")
    parser.add_argument("--agent-model")
    parser.add_argument("--judge-model")
    return parser


def resolve_config(args: object, environ: Mapping[str, str]) -> Dict[str, object]:
    """Resolve configuration without accepting or emitting credentials via the CLI."""
    api_key = environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    base_url = getattr(args, "base_url", None) or environ.get("ANTHROPIC_BASE_URL", "").strip() or None
    agent_model = (
        getattr(args, "agent_model", None)
        or environ.get("ANTHROPIC_MODEL", "").strip()
        or "deepseek-v4-pro"
    )
    judge_model = (
        getattr(args, "judge_model", None)
        or environ.get("EVAL_JUDGE_MODEL", "").strip()
        or agent_model
    )
    return {
        "api_key": api_key,
        "base_url": base_url,
        "agent_model": agent_model,
        "judge_model": judge_model,
    }


def prepare_output_dir(path: Path) -> None:
    """Create a new output directory or accept an empty one, never overwrite data."""
    if path.exists():
        if not path.is_dir():
            raise FileExistsError(f"output path is not a directory: {path}")
        if any(path.iterdir()):
            raise FileExistsError(f"output directory is not empty: {path}")
        return
    path.mkdir(parents=True)


def get_git_revision(repo: Path) -> Optional[str]:
    """Return the current worktree revision without mutating repository configuration."""
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_metadata(
    *,
    dataset_path: Path,
    dataset_sha256: str,
    case_count: int,
    config: Mapping[str, object],
    started_at: str,
    completed_at: str,
    repo: Path,
) -> Dict[str, object]:
    """Build reproducible metadata containing only the approved safe fields."""
    return {
        "dataset_path": str(dataset_path),
        "dataset_sha256": dataset_sha256,
        "case_count": case_count,
        "git_revision": get_git_revision(repo),
        "agent_model": config["agent_model"],
        "judge_model": config["judge_model"],
        "prompt_version": PROMPT_VERSION,
        "temperature": JUDGE_TEMPERATURE,
        "pass_threshold": PASS_THRESHOLD,
        "timeout": JUDGE_TIMEOUT_SECONDS,
        "max_attempts": JUDGE_MAX_ATTEMPTS,
        "context_mode": "controlled_context",
        "judge_output_strategy": JUDGE_OUTPUT_STRATEGY,
        "retrieval_evaluated": False,
        "started_at": started_at,
        "completed_at": completed_at,
    }


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
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


def _finalize_artifacts(
    *,
    completed: List[Dict[str, object]],
    metrics_path: Path,
    metadata_path: Path,
    dataset_path: Path,
    dataset_sha256: str,
    config: Mapping[str, object],
    started_at: str,
    completed_at: str,
) -> Optional[RuntimeError]:
    errors = []
    payloads = {}
    builders = (
        ("dialog_metrics.json", metrics_path, lambda: compute_dialog_metrics(completed)),
        (
            "run_metadata.json",
            metadata_path,
            lambda: build_metadata(
                dataset_path=dataset_path,
                dataset_sha256=dataset_sha256,
                case_count=len(completed),
                config=config,
                started_at=started_at,
                completed_at=completed_at,
                repo=Path(__file__).resolve().parent.parent,
            ),
        ),
    )
    for name, path, builder in builders:
        try:
            payloads[name] = (path, builder())
        except Exception as exc:
            errors.append(f"{name} build failed: {exc}")
    for name, (path, payload) in payloads.items():
        try:
            _atomic_write_json(path, payload)
        except Exception as exc:
            errors.append(f"{name} write failed: {exc}")
    if errors:
        return RuntimeError("artifact finalization failed: " + "; ".join(errors))
    return None


async def run_evaluation(
    *,
    cases: List[Dict[str, object]],
    output_dir: Path,
    orchestrator: object,
    judge: object,
    config: Mapping[str, object],
    dataset_path: Path,
    dataset_sha256: Optional[str] = None,
) -> Dict[str, Path]:
    """Evaluate cases sequentially, flushing each JSONL record before the next case."""
    prepare_output_dir(output_dir)
    predictions_path = output_dir / "dialog_predictions.jsonl"
    metrics_path = output_dir / "dialog_metrics.json"
    metadata_path = output_dir / "run_metadata.json"
    paths = {"predictions": predictions_path, "metrics": metrics_path, "metadata": metadata_path}
    completed: List[Dict[str, object]] = []
    started_at = _utc_now()
    secrets = (str(config["api_key"]),)
    evaluated_dataset_sha256 = dataset_sha256 or _sha256_file(dataset_path)
    evaluation_error: Optional[BaseException] = None

    try:
        with predictions_path.open("w", encoding="utf-8", newline="\n") as handle:
            for case in cases:
                result = await evaluate_case(case, orchestrator, judge, secrets=secrets)
                serialized = json.dumps(result, ensure_ascii=False) + "\n"
                last_good_offset = handle.tell()
                try:
                    handle.write(serialized)
                    handle.flush()
                except BaseException:
                    try:
                        handle.seek(last_good_offset)
                        handle.truncate()
                        handle.flush()
                    except Exception:
                        pass
                    raise
                completed.append(result)
    except BaseException as exc:
        evaluation_error = exc

    completed_at = _utc_now()
    finalization_error = _finalize_artifacts(
        completed=completed,
        metrics_path=metrics_path,
        metadata_path=metadata_path,
        dataset_path=dataset_path,
        dataset_sha256=evaluated_dataset_sha256,
        config=config,
        started_at=started_at,
        completed_at=completed_at,
    )
    if evaluation_error is not None:
        if finalization_error is not None:
            raise BaseExceptionGroup(
                "evaluation and artifact finalization failed",
                [evaluation_error, finalization_error],
            )
        raise evaluation_error.with_traceback(evaluation_error.__traceback__)
    if finalization_error is not None:
        raise finalization_error
    return paths


def _create_dependencies(config: Mapping[str, object]) -> tuple[object, DialogJudge]:
    """Create separate agent and judge clients from resolved configuration."""
    from anthropic import AsyncAnthropic
    from agents.agent_orchestrator import AgentOrchestrator

    api_key = str(config["api_key"])
    base_url = config["base_url"]
    orchestrator = AgentOrchestrator(
        api_key=api_key,
        base_url=base_url,
        model=str(config["agent_model"]),
    )
    client_options = {"api_key": api_key}
    if base_url:
        client_options["base_url"] = base_url
    judge_client = AsyncAnthropic(**client_options)
    return orchestrator, DialogJudge(
        judge_client,
        str(config["judge_model"]),
        timeout_seconds=JUDGE_TIMEOUT_SECONDS,
        max_attempts=JUDGE_MAX_ATTEMPTS,
        secrets=(api_key,),
    )


def _load_environment() -> None:
    from dotenv import load_dotenv

    load_dotenv()


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config: Optional[Dict[str, object]] = None
    try:
        _load_environment()
        config = resolve_config(args, os.environ)
        cases, dataset_sha256 = _load_validated_dataset(args.dialog_data)
        if args.limit is not None:
            cases = cases[:args.limit]
        prepare_output_dir(args.output_dir)
        orchestrator, judge = _create_dependencies(config)
        asyncio.run(run_evaluation(
            cases=cases,
            output_dir=args.output_dir,
            orchestrator=orchestrator,
            judge=judge,
            config=config,
            dataset_path=args.dialog_data,
            dataset_sha256=dataset_sha256,
        ))
        return 0
    except Exception as exc:
        secrets = (str(config["api_key"]),) if config else ()
        print(sanitize_error(exc, secrets), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

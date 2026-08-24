"""Run intent prediction or recompute metrics from saved prediction JSONL."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .intent_metrics import INTENT_LABELS, compute_intent_metrics


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank lines are not allowed")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


async def generate_predictions(
    dataset_rows: List[Dict[str, Any]],
    recognizer: Any,
    mode: str = "fusion",
) -> List[Dict[str, Any]]:
    """Run a recognizer sequentially and produce auditable prediction rows."""
    predictions: List[Dict[str, Any]] = []
    required = {"id", "message", "gold_intent"}
    for row_number, row in enumerate(dataset_rows, 1):
        missing = required - row.keys()
        if missing:
            raise ValueError(f"dataset row {row_number}: missing fields {sorted(missing)}")

        started = time.monotonic()
        try:
            result = await recognizer.recognize(row["message"], mode=mode)
            latency_ms = float(
                getattr(result, "latency_ms", (time.monotonic() - started) * 1000)
            )
            prediction = {
                "id": row["id"],
                "message": row["message"],
                "gold_intent": row["gold_intent"],
                "predicted_intent": result.intent.value,
                "confidence": float(result.confidence),
                "latency_ms": latency_ms,
                "error": None,
                "mode": mode,
            }
            source_scores = getattr(result, "source_scores", None)
            if source_scores:
                prediction["source_scores"] = source_scores
            source_errors = getattr(result, "source_errors", None)
            if source_errors:
                prediction["source_errors"] = source_errors
        except Exception as exc:
            prediction = {
                "id": row["id"],
                "message": row["message"],
                "gold_intent": row["gold_intent"],
                "predicted_intent": "other",
                "confidence": 0.0,
                "latency_ms": (time.monotonic() - started) * 1000,
                "error": f"{type(exc).__name__}: {exc}",
                "mode": mode,
            }
        predictions.append(prediction)
    return predictions


async def _generate_and_close(
    dataset_rows: List[Dict[str, Any]], recognizer: Any, mode: str = "fusion"
) -> List[Dict[str, Any]]:
    try:
        return await generate_predictions(dataset_rows, recognizer, mode=mode)
    finally:
        client = getattr(recognizer, "client", None)
        close = getattr(client, "close", None)
        if close:
            close_result = close()
            if inspect.isawaitable(close_result):
                await close_result


def _create_recognizer(
    api_key: Optional[str], base_url: Optional[str], model: Optional[str]
) -> Any:
    _load_environment()
    resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not resolved_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured; set it in .env or pass --api-key"
        )

    from core.intent_recognizer import IntentRecognizer

    return IntentRecognizer(
        api_key=resolved_key,
        base_url=base_url or os.getenv("ANTHROPIC_BASE_URL", "").strip() or None,
        model=model
        or os.getenv("ANTHROPIC_MODEL", "").strip()
        or "claude-3-5-sonnet-20241022",
    )


def _load_environment(path: Path = Path(".env")) -> None:
    """Load local configuration, with no hard dependency on python-dotenv."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        if not path.exists():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    else:
        load_dotenv(path)


def _compute_metrics(rows: List[Dict[str, Any]]) -> Dict[str, object]:
    required = {"gold_intent", "predicted_intent"}
    for i, row in enumerate(rows, 1):
        missing = required - row.keys()
        if missing:
            raise ValueError(f"prediction row {i}: missing fields {sorted(missing)}")
    return compute_intent_metrics(
        [row["gold_intent"] for row in rows],
        [row["predicted_intent"] for row in rows],
        INTENT_LABELS,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--predictions", type=Path,
                        help="recompute metrics from saved prediction JSONL")
    source.add_argument("--intent-data", type=Path,
                        help="run IntentRecognizer on an intent dataset JSONL")
    parser.add_argument("--output-dir", type=Path,
                        help="write intent_metrics.json and normalized predictions.jsonl")
    parser.add_argument("--limit", type=int,
                        help="only process the first N dataset rows (smoke test)")
    parser.add_argument("--api-key", help="override ANTHROPIC_API_KEY")
    parser.add_argument("--base-url", help="override ANTHROPIC_BASE_URL")
    parser.add_argument("--model", help="override ANTHROPIC_MODEL")
    parser.add_argument(
        "--mode",
        choices=("pattern_only", "embedding_only", "llm_only", "fusion"),
        default="fusion",
        help="intent-recognition branch to evaluate (default: fusion)",
    )
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")

    if args.predictions:
        rows = _load_jsonl(args.predictions)
        if args.limit is not None:
            rows = rows[:args.limit]
    else:
        if not args.output_dir:
            parser.error("--output-dir is required when using --intent-data")
        dataset_rows = _load_jsonl(args.intent_data)
        if args.limit is not None:
            dataset_rows = dataset_rows[:args.limit]
        recognizer = _create_recognizer(args.api_key, args.base_url, args.model)
        rows = asyncio.run(_generate_and_close(dataset_rows, recognizer, mode=args.mode))

    metrics = _compute_metrics(rows)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "intent_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (args.output_dir / "intent_predictions.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

"""Deterministic dialog baseline creation and regression comparison.

Pure standard-library module. It never reads environment variables and
never opens network connections, and it never imports or reuses the
legacy baseline logic in evaluation/evaluator.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

BASELINE_SCHEMA_VERSION = "dialog_regression_baseline_v1"
BASELINE_KIND = "dialog_machine_monitoring"
ADJUDICATED_PASS_RATE_FROZEN = 0.6285714285714286


class RegressionInputError(ValueError):
    """Raised when formal artifacts are missing, malformed or inconsistent."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise RegressionInputError(f"missing file: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise RegressionInputError(f"invalid JSON in {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[object]:
    if not path.is_file():
        raise RegressionInputError(f"missing file: {path}")
    records = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise RegressionInputError(
                        f"invalid JSON in {path} line {line_number}: {exc}"
                    ) from exc
    except UnicodeDecodeError as exc:
        raise RegressionInputError(f"cannot decode {path} as UTF-8: {exc}") from exc
    return records


def _require_mapping(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RegressionInputError(f"{location}: must be a JSON object")
    return value


def _require_field(mapping: Mapping[str, object], name: str, location: str) -> object:
    if name not in mapping:
        raise RegressionInputError(f"{location}: missing required field {name!r}")
    return mapping[name]


def _require_number(value: object, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RegressionInputError(f"{location}: must be a number")
    return float(value)


def _require_int(value: object, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegressionInputError(f"{location}: must be an integer")
    return value


def _require_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegressionInputError(f"{location}: must be a non-empty string")
    return value


def _require_dataset_sha256(value: object, location: str) -> str:
    sha = _require_string(value, location)
    if len(sha) != 64 or any(character not in "0123456789abcdef" for character in sha):
        raise RegressionInputError(
            f"{location}: must be a 64-character lowercase hex digest"
        )
    return sha


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    """Serialize fully first, then create the target exclusively.

    The payload is serialized before opening the file so the target
    either appears complete or does not exist at all. Text mode ``x``
    refuses to touch an existing target; nothing here appends or
    replaces.
    """
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)


def build_baseline(
    *,
    metrics_path: Path,
    metadata_path: Path,
    predictions_path: Path,
    adjudication_path: Path,
    created_at: str | None = None,
) -> dict[str, object]:
    """Read the four formal artifacts, cross-check them and build the baseline.

    Never writes any file. Rejects non-zero Agent/Judge failure rates
    (baseline-side hard gates) and any cross-check mismatch.
    """
    metrics = _require_mapping(_read_json(metrics_path), "metrics")
    metadata = _require_mapping(_read_json(metadata_path), "metadata")
    adjudication = _require_mapping(_read_json(adjudication_path), "adjudication workbook")
    predictions = _read_jsonl(predictions_path)

    total_cases = _require_int(
        _require_field(metrics, "total_cases", "metrics"), "metrics.total_cases"
    )
    passed_cases = _require_int(
        _require_field(metrics, "passed_cases", "metrics"), "metrics.passed_cases"
    )
    overall_mean = _require_number(
        _require_field(metrics, "overall_mean", "metrics"), "metrics.overall_mean"
    )
    pass_rate = _require_number(
        _require_field(metrics, "pass_rate", "metrics"), "metrics.pass_rate"
    )
    agent_failed_rate = _require_number(
        _require_field(metrics, "agent_failed_rate", "metrics"), "metrics.agent_failed_rate"
    )
    judge_failed_rate = _require_number(
        _require_field(metrics, "judge_failed_rate", "metrics"), "metrics.judge_failed_rate"
    )

    git_revision = _require_string(
        _require_field(metadata, "git_revision", "metadata"), "metadata.git_revision"
    )
    dataset_sha256 = _require_dataset_sha256(
        _require_field(metadata, "dataset_sha256", "metadata"), "metadata.dataset_sha256"
    )
    judge_model = _require_string(
        _require_field(metadata, "judge_model", "metadata"), "metadata.judge_model"
    )
    prompt_version = _require_string(
        _require_field(metadata, "prompt_version", "metadata"), "metadata.prompt_version"
    )
    pass_rule_version = _require_string(
        _require_field(metadata, "pass_rule_version", "metadata"), "metadata.pass_rule_version"
    )
    case_count = _require_int(
        _require_field(metadata, "case_count", "metadata"), "metadata.case_count"
    )

    if len(predictions) != total_cases:
        raise RegressionInputError(
            f"predictions line count {len(predictions)} does not match"
            f" metrics total_cases {total_cases}"
        )
    predictions_passed = sum(
        1
        for record in predictions
        if isinstance(record, dict) and record.get("case_pass") is True
    )
    if predictions_passed != passed_cases:
        raise RegressionInputError(
            f"predictions passed count {predictions_passed} does not match"
            f" metrics passed_cases {passed_cases}"
        )
    if case_count != total_cases:
        raise RegressionInputError(
            f"metadata case_count {case_count} does not match metrics total_cases {total_cases}"
        )
    workbook_total = _require_int(
        _require_field(adjudication, "total_cases", "adjudication workbook"),
        "adjudication workbook.total_cases",
    )
    reviewed_cases = _require_int(
        _require_field(adjudication, "reviewed_cases", "adjudication workbook"),
        "adjudication workbook.reviewed_cases",
    )
    inherited_cases = _require_int(
        _require_field(adjudication, "inherited_cases", "adjudication workbook"),
        "adjudication workbook.inherited_cases",
    )
    workbook_machine_pass_rate = _require_number(
        _require_field(adjudication, "machine_pass_rate", "adjudication workbook"),
        "adjudication workbook.machine_pass_rate",
    )
    workbook_adjudicated = _require_number(
        _require_field(adjudication, "adjudicated_pass_rate", "adjudication workbook"),
        "adjudication workbook.adjudicated_pass_rate",
    )
    if workbook_total != total_cases:
        raise RegressionInputError(
            f"adjudication workbook total_cases {workbook_total} does not match"
            f" metrics total_cases {total_cases}"
        )
    if reviewed_cases + inherited_cases != total_cases:
        raise RegressionInputError(
            f"adjudication workbook reviewed_cases {reviewed_cases} + inherited_cases"
            f" {inherited_cases} does not match total_cases {total_cases}"
        )
    if workbook_machine_pass_rate != pass_rate:
        raise RegressionInputError(
            f"adjudication workbook machine_pass_rate {workbook_machine_pass_rate}"
            f" does not match metrics pass_rate {pass_rate}"
        )
    if workbook_adjudicated != ADJUDICATED_PASS_RATE_FROZEN:
        raise RegressionInputError(
            f"adjudication workbook adjudicated_pass_rate {workbook_adjudicated}"
            f" does not match frozen value {ADJUDICATED_PASS_RATE_FROZEN}"
        )
    if agent_failed_rate != 0.0:
        raise RegressionInputError("baseline hard gate: agent_failed_rate must be 0.0")
    if judge_failed_rate != 0.0:
        raise RegressionInputError("baseline hard gate: judge_failed_rate must be 0.0")

    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_kind": BASELINE_KIND,
        "created_at": created_at if created_at is not None else _utc_now(),
        "execution_revision": git_revision,
        "dataset_sha256": dataset_sha256,
        "predictions_sha256": _sha256_file(predictions_path),
        "metrics_sha256": _sha256_file(metrics_path),
        "judge_model": judge_model,
        "prompt_version": prompt_version,
        "pass_rule_version": pass_rule_version,
        "machine_overall_mean": overall_mean,
        "machine_pass_rate": pass_rate,
        "agent_failed_rate": agent_failed_rate,
        "judge_failed_rate": judge_failed_rate,
        "adjudicated_pass_rate": {
            "value": workbook_adjudicated,
            "usage": "report_only",
            "included_in_automatic_regression": False,
            "reviewed_cases": reviewed_cases,
            "inherited_cases": inherited_cases,
        },
    }


def create_baseline(
    *,
    metrics_path: Path,
    metadata_path: Path,
    predictions_path: Path,
    adjudication_path: Path,
    output_path: Path,
    created_at: str | None = None,
) -> dict[str, object]:
    """Build the baseline and write it via exclusive creation."""
    baseline = build_baseline(
        metrics_path=metrics_path,
        metadata_path=metadata_path,
        predictions_path=predictions_path,
        adjudication_path=adjudication_path,
        created_at=created_at,
    )
    write_json_new(output_path, baseline)
    return baseline


def main(argv: Sequence[str] | None = None) -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

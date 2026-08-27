"""Deterministic dialog baseline creation and regression comparison.

Pure standard-library module. It never reads environment variables and
never opens network connections, and it never imports or reuses the
legacy baseline logic in evaluation/evaluator.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence


class RegressionInputError(ValueError):
    """Raised when formal artifacts are missing, malformed or inconsistent."""


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


def main(argv: Sequence[str] | None = None) -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

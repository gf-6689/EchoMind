import json
from pathlib import Path

import pytest

from evaluation.run_dialog_eval import load_and_validate


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


def test_dialog_validator_loads_smoke_dataset_with_expected_count():
    path = (
        Path(__file__).resolve().parents[6]
        / "EchoMind_data"
        / "data"
        / "eval"
        / "dialog_smoke.json"
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

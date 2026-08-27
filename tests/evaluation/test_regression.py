"""Deterministic dialog baseline/regression module tests.

Tests use only tmp_path fixtures and fake JSON artifacts; they never
read or write the real formal evaluation directories and never touch
.test-tmp/ or .pytest_cache/.
"""

import json

import pytest

from evaluation import regression


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

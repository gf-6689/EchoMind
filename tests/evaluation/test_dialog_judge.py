import asyncio
from types import SimpleNamespace

import pytest

from evaluation.dialog_judge import DialogJudge, validate_judge_payload


def tool_response(payload):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="score_dialog_response", input=payload)])


class FakeMessages:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes):
        self.messages = FakeMessages(outcomes)


def judge_turn(judge):
    return asyncio.run(judge.judge_turn(
        question="订单为何延迟？",
        response="因暴雨延迟两天",
        context="暴雨导致延迟",
        reference_answer="解释原因",
        required_points=["暴雨"],
        history=[],
    ))


def test_judge_forces_tool_and_returns_valid_scores():
    client = FakeClient([tool_response({"relevance": .9, "accuracy": .8, "completeness": .7, "helpfulness": .6, "reasoning": "覆盖主要事实"})])
    result = judge_turn(DialogJudge(client, "deepseek-v4-pro"))

    call = client.messages.calls[0]
    assert call["temperature"] == 0.0
    assert call["tool_choice"] == {"type": "tool", "name": "score_dialog_response"}
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert call["timeout"] == 30.0
    assert result["judge_attempts"] == 1
    assert result["judge"]["overall"] == pytest.approx(.75)


def test_judge_retries_at_most_three_total_calls_and_keeps_final_error(monkeypatch):
    clock = iter([10.0, 16.5])
    monkeypatch.setattr("evaluation.dialog_judge.time.monotonic", lambda: next(clock))
    client = FakeClient([TimeoutError("first"), ValueError("bad payload"), TimeoutError("third")])
    result = judge_turn(DialogJudge(client, "judge", max_attempts=3))

    assert len(client.messages.calls) == 3
    assert result["judge_failed"] is True
    assert result["judge_attempts"] == 3
    assert "third" in result["judge_error"]
    assert result["judge"]["latency_ms"] == 6500.0


@pytest.mark.parametrize("payload", [
    {"relevance": .5, "accuracy": .5, "completeness": .5, "reasoning": "missing"},
    {"relevance": True, "accuracy": .5, "completeness": .5, "helpfulness": .5, "reasoning": "bool"},
    {"relevance": float("nan"), "accuracy": .5, "completeness": .5, "helpfulness": .5, "reasoning": "nan"},
    {"relevance": 1.1, "accuracy": .5, "completeness": .5, "helpfulness": .5, "reasoning": "range"},
])
def test_validate_judge_payload_rejects_invalid_values(payload):
    with pytest.raises(ValueError):
        validate_judge_payload(payload)


def test_judge_rejects_free_text_and_does_not_substitute_scores():
    client = FakeClient([SimpleNamespace(content=[SimpleNamespace(type="text", text='{"relevance": 1}')])])
    result = judge_turn(DialogJudge(client, "judge", max_attempts=1))

    assert result["judge_failed"] is True
    assert result["judge"]["latency_ms"] >= 0
    assert "overall" not in result["judge"]


def test_judge_redacts_configured_and_header_secrets():
    client = FakeClient([RuntimeError("Authorization: Bearer abc123 API-key=top-secret configured-secret")])
    result = judge_turn(DialogJudge(client, "judge", max_attempts=1, secrets=("configured-secret",)))

    assert "abc123" not in result["judge_error"]
    assert "top-secret" not in result["judge_error"]
    assert "configured-secret" not in result["judge_error"]

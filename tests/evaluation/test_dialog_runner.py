import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.agent_orchestrator import Request
from evaluation.run_dialog_eval import evaluate_case, load_and_validate


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
    assert output["judge_failed"] is False
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

import asyncio

from agents.agent_orchestrator import (
    AgentOrchestrator,
    AgentResponse,
    AgentType,
    BaseAgent,
    Request,
    RoutingDecision,
)
from core.intent_recognizer import IntentCategory, UrgencyLevel


class ExplodingAgent(BaseAgent):
    agent_type = AgentType.GENERAL
    system_prompt = "test"

    async def _call_llm(self, req):
        raise RuntimeError("upstream connection failed")


class StaticAgent:
    def __init__(self, response):
        self.agent_type = response.agent_type
        self.response = response
        self.stats = self

    def routing_score(self):
        return 1.0

    async def handle(self, req):
        return self.response


def make_orchestrator(*responses):
    orchestrator = object.__new__(AgentOrchestrator)
    orchestrator._pool = {}
    for response in responses:
        orchestrator._pool.setdefault(response.agent_type, []).append(StaticAgent(response))
    return orchestrator


def make_request():
    return Request(
        message="请处理第二笔重复扣款退款",
        user_id="test-user",
        conv_id="test-conversation",
        intent=IntentCategory.REFUND,
        intent_group="billing",
        urgency=UrgencyLevel.MEDIUM,
    )


def test_base_agent_preserves_failure_error_for_audit():
    response = asyncio.run(ExplodingAgent(object(), "model").handle(make_request()))

    assert response.success is False
    assert response.error == "upstream connection failed"


def test_orchestrator_reports_success_when_general_fallback_succeeds():
    billing_failure = AgentResponse(
        agent_type=AgentType.BILLING,
        content="billing failed",
        success=False,
        error="billing connection failed",
    )
    general_success = AgentResponse(
        agent_type=AgentType.GENERAL,
        content="fallback answer",
        success=True,
    )
    orchestrator = make_orchestrator(billing_failure, general_success)

    result = asyncio.run(orchestrator.run(make_request()))

    assert result.response == "fallback answer"
    assert result.success is True
    assert result.error is None


def test_orchestrator_reports_failure_when_general_fallback_also_fails():
    billing_failure = AgentResponse(
        agent_type=AgentType.BILLING,
        content="billing failed",
        success=False,
        error="billing connection failed",
    )
    general_failure = AgentResponse(
        agent_type=AgentType.GENERAL,
        content="general failed",
        success=False,
        error="general connection failed",
    )
    orchestrator = make_orchestrator(billing_failure, general_failure)

    result = asyncio.run(orchestrator.run(make_request()))

    assert result.response == "general failed"
    assert result.success is False
    assert result.error == "general connection failed"


def test_parallel_orchestration_reports_failure_when_every_agent_fails():
    technical_failure = AgentResponse(
        agent_type=AgentType.TECHNICAL,
        content="technical failed",
        success=False,
        error="technical connection failed",
    )
    billing_failure = AgentResponse(
        agent_type=AgentType.BILLING,
        content="billing failed",
        success=False,
        error="billing connection failed",
    )
    orchestrator = make_orchestrator(technical_failure, billing_failure)
    decision = RoutingDecision(
        primary_agent=AgentType.TECHNICAL,
        supporting_agents=[AgentType.BILLING],
        reason="test parallel failure",
        confidence=0.9,
    )

    result = asyncio.run(orchestrator.run_parallel(make_request(), decision))

    assert result.response == "抱歉，所有 Agent 均处理失败。"
    assert result.success is False
    assert result.error == "technical connection failed; billing connection failed"

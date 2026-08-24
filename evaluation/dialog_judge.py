"""Independent structured judge client for dialog evaluation."""

import json
import math
import re
from time import monotonic
from types import SimpleNamespace
from typing import Any, Dict, Iterable

from evaluation.dialog_metrics import DIMENSIONS, compute_turn_scores


time = SimpleNamespace(monotonic=monotonic)


PROMPT_VERSION = "dialog_judge_v1"
PROMPT_TEMPLATE = """你是客服回复质量评审。仅依据给定材料评估当前 Agent 回答。
[此前对话]
{history}
[当前用户问题]
{question}
[受控背景]
{context}
[参考答案]
{reference_answer}
[回答必须覆盖]
{required_points}
[Agent 回答]
{response}

按 0 到 1 评分：relevance=是否直接回应问题；accuracy=是否与受控背景一致；
completeness=是否覆盖必须点；helpfulness=用户能否据此采取下一步行动。不得仅因文风流畅给高分，accuracy 不得使用受控背景之外的事实。必须调用 score_dialog_response 工具返回四项分数和简短 reasoning。"""
SCORE_TOOL = {
    "name": "score_dialog_response",
    "description": "Score one customer-service turn using the fixed rubric.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevance": {"type": "number", "minimum": 0, "maximum": 1},
            "accuracy": {"type": "number", "minimum": 0, "maximum": 1},
            "completeness": {"type": "number", "minimum": 0, "maximum": 1},
            "helpfulness": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string", "minLength": 1},
        },
        "required": ["relevance", "accuracy", "completeness", "helpfulness", "reasoning"],
        "additionalProperties": False,
    },
}


def _clean_text(value: Any) -> str:
    """Remove Unicode surrogate code points before HTTP encoding."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.encode("utf-8", errors="ignore").decode("utf-8")


def _clean_json_strings(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        return [_clean_json_strings(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {_clean_text(key): _clean_json_strings(item) for key, item in value.items()}
    return value


def validate_judge_payload(payload: Dict[str, object]) -> Dict[str, object]:
    """Validate a score tool payload and derive its unrounded overall score."""
    expected_fields = {"relevance", "accuracy", "completeness", "helpfulness", "reasoning"}
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise ValueError("judge payload fields do not match schema")
    scores = compute_turn_scores(payload)
    for name in DIMENSIONS:
        value = payload[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
        ):
            raise ValueError(f"invalid judge score: {name}")
    if not isinstance(payload["reasoning"], str) or not payload["reasoning"].strip():
        raise ValueError("judge reasoning must be non-empty")
    return {**scores, "reasoning": payload["reasoning"].strip()}


def _extract_tool_payload(content: Iterable[object]) -> Dict[str, object]:
    """Extract the required score tool result; free-text responses are rejected."""
    for block in content or []:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        block_name = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
        if block_type == "tool_use" and block_name == SCORE_TOOL["name"]:
            return block.get("input") if isinstance(block, dict) else block.input
    raise ValueError("judge tool payload missing")


def sanitize_error(error: Exception, secrets: Iterable[str] = ()) -> str:
    """Produce a bounded diagnostic while preventing credential disclosure."""
    text = str(error).replace("\r", " ").replace("\n", " ")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(authorization:\s*bearer\s+|api[_-]?key[=:]\s*)\S+", r"\1[REDACTED]", text)
    return text[:500]


class DialogJudge:
    """Call an Anthropic-compatible client for one auditable dialog judgment."""

    def __init__(
        self,
        client: object,
        model: str,
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        secrets: Iterable[str] = (),
    ) -> None:
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = min(max(1, int(max_attempts)), 3)
        self.secrets = tuple(secrets)

    def _build_prompt(
        self,
        question: object,
        response: object,
        context: object,
        reference_answer: object,
        required_points: object,
        history: object,
    ) -> str:
        return PROMPT_TEMPLATE.format(
            history=json.dumps(_clean_json_strings(history), ensure_ascii=False),
            question=_clean_text(question),
            context=_clean_text(context),
            reference_answer=_clean_text(reference_answer),
            required_points=json.dumps(_clean_json_strings(required_points), ensure_ascii=False),
            response=_clean_text(response),
        )

    async def judge_turn(
        self,
        *,
        question: object,
        response: object,
        context: object,
        reference_answer: object,
        required_points: object,
        history: object,
    ) -> Dict[str, object]:
        last_error = "unknown judge error"
        try:
            prompt = self._build_prompt(question, response, context, reference_answer, required_points, history)
        except Exception as exc:
            return {
                "judge_failed": True,
                "judge_error": sanitize_error(exc, self.secrets),
                "judge_skipped": False,
                "judge_attempts": 0,
                "judge": None,
            }
        started = time.monotonic()
        for attempt in range(1, self.max_attempts + 1):
            try:
                api_response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=512,
                    temperature=0.0,
                    messages=[{"role": "user", "content": prompt}],
                    tools=[SCORE_TOOL],
                    tool_choice={"type": "tool", "name": SCORE_TOOL["name"]},
                    extra_body={"thinking": {"type": "disabled"}},
                    timeout=self.timeout_seconds,
                )
                scores = validate_judge_payload(_extract_tool_payload(api_response.content))
                scores["latency_ms"] = (time.monotonic() - started) * 1000
                return {
                    "judge_failed": False,
                    "judge_error": None,
                    "judge_skipped": False,
                    "judge_attempts": attempt,
                    "judge": scores,
                }
            except Exception as exc:
                last_error = sanitize_error(exc, self.secrets)
        return {
            "judge_failed": True,
            "judge_error": last_error,
            "judge_skipped": False,
            "judge_attempts": self.max_attempts,
            "judge": {"latency_ms": (time.monotonic() - started) * 1000},
        }

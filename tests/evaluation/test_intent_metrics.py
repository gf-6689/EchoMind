import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.intent_recognizer import IntentCategory, IntentRecognizer, _TEMPLATES
from evaluation.intent_metrics import compute_intent_metrics
from evaluation.run_intent_eval import generate_predictions


LABELS = ["a", "b", "c"]


def test_metrics_use_all_fixed_labels_and_confusion_orientation():
    result = compute_intent_metrics(
        ["a", "a", "b", "c"], ["a", "b", "b", "b"], LABELS
    )
    assert result["total"] == 4
    assert result["correct"] == 2
    assert result["accuracy"] == pytest.approx(0.5)
    assert result["confusion_matrix"] == [[1, 1, 0], [0, 1, 0], [0, 1, 0]]
    assert result["per_class"]["c"]["support"] == 1
    assert result["per_class"]["c"]["f1"] == 0.0
    assert result["macro_f1"] == pytest.approx((2 / 3 + 0.5 + 0) / 3)


def test_empty_input_is_well_defined():
    result = compute_intent_metrics([], [], LABELS)
    assert result["accuracy"] == 0.0
    assert result["macro_f1"] == 0.0
    assert result["total"] == 0


@pytest.mark.parametrize("gold,pred", [(["a"], []), (["a"], ["unknown"])])
def test_invalid_inputs_fail_loudly(gold, pred):
    with pytest.raises(ValueError):
        compute_intent_metrics(gold, pred, LABELS)


def test_prediction_generation_preserves_audit_fields():
    class FakeRecognizer:
        async def recognize(self, message, mode="fusion"):
            return SimpleNamespace(
                intent=SimpleNamespace(value="refund"),
                confidence=0.9,
                latency_ms=12.5,
                source_scores={"pattern": 0.8},
            )

    rows = [{"id": "dev_1", "message": "退款", "gold_intent": "refund"}]
    result = asyncio.run(generate_predictions(rows, FakeRecognizer()))
    assert result == [{
        "id": "dev_1",
        "message": "退款",
        "gold_intent": "refund",
        "predicted_intent": "refund",
        "confidence": 0.9,
        "latency_ms": 12.5,
        "error": None,
        "mode": "fusion",
        "source_scores": {"pattern": 0.8},
    }]


def test_llm_json_parser_accepts_markdown_fences_and_explanation():
    raw = 'result follows:\n```json\n{"intent":"refund","confidence":0.9}\n```'
    assert IntentRecognizer._parse_json_object(raw) == {
        "intent": "refund",
        "confidence": 0.9,
    }


def test_llm_json_parser_rejects_empty_response():
    with pytest.raises(ValueError, match="empty text response"):
        IntentRecognizer._parse_json_object("  ")


def test_tool_payload_parser_extracts_structured_classification():
    content = [{
        "type": "tool_use",
        "name": "classify_intent",
        "input": {"intent": "refund", "confidence": 0.93, "reasoning": "退款进度"},
    }]
    assert IntentRecognizer._extract_tool_payload(content) == content[0]["input"]


def test_pattern_only_mode_runs_without_llm_client():
    recognizer = object.__new__(IntentRecognizer)
    recognizer.threshold = 0.5
    recognizer._cache = {}
    recognizer.cache_hits = 0
    recognizer.cache_misses = 0
    result = asyncio.run(recognizer.recognize("hello", mode="pattern_only"))
    assert result.intent.value == "greeting"
    assert result.source_scores["llm"] == 0.0
    assert result.source_scores["embedding"] == 0.0
    assert result.source_scores["pattern"] > 0.0


def test_invalid_intent_mode_fails_loudly():
    recognizer = object.__new__(IntentRecognizer)
    with pytest.raises(ValueError, match="unsupported intent mode"):
        asyncio.run(recognizer.recognize("hello", mode="invalid"))


def test_embedding_mode_uses_injected_encoder_and_batches_templates():
    target = _TEMPLATES[IntentCategory.REFUND][0]

    class RecordingEncoder:
        def __init__(self):
            self.calls = []

        def encode(self, texts, **kwargs):
            texts = list(texts)
            self.calls.append((texts, kwargs))
            return [[1.0, 0.0] if text == target else [0.0, 1.0] for text in texts]

    encoder = RecordingEncoder()
    recognizer = IntentRecognizer(api_key="test", embedding_encoder=encoder)
    result = asyncio.run(recognizer.recognize(target, mode="embedding_only"))

    assert result.intent == IntentCategory.REFUND
    assert len(encoder.calls) == 2
    assert len(encoder.calls[0][0]) > 19
    assert encoder.calls[1][0] == [target]
    assert all(call[1]["normalize_embeddings"] is True for call in encoder.calls)


def test_bge_encoder_is_loaded_once_into_configured_cache(monkeypatch):
    creations = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, cache_folder):
            creations.append((model_name, cache_folder))

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    cache_dir = Path.cwd() / "data" / "models" / "test-cache"
    recognizer = IntentRecognizer(
        api_key="test",
        embedding_model_name="BAAI/bge-small-zh-v1.5",
        embedding_cache_dir=str(cache_dir),
    )

    first = recognizer._get_embedding_encoder()
    second = recognizer._get_embedding_encoder()

    assert first is second
    assert creations == [("BAAI/bge-small-zh-v1.5", str(cache_dir))]
    assert cache_dir.is_dir()

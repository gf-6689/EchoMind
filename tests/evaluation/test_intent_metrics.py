import asyncio
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import evaluation.intent_metrics as intent_metrics
import evaluation.run_intent_eval as intent_eval
from core.intent_recognizer import IntentCategory, IntentRecognizer, _TEMPLATES
from evaluation.intent_metrics import compute_intent_metrics
from evaluation.run_intent_eval import generate_predictions


LABELS = ["a", "b", "c"]


@pytest.fixture
def workspace_tmp_path():
    root = (Path.cwd() / ".test-tmp").resolve()
    workspace = Path.cwd().resolve()
    assert root.is_relative_to(workspace)
    path = root / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)
        if root.exists() and not any(root.iterdir()):
            root.rmdir()


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


def test_latency_metrics_use_linear_interpolation_percentiles():
    result = intent_metrics.compute_latency_metrics([10.0, 20.0, 30.0, 40.0])

    assert result == {
        "unit": "ms",
        "count": 4,
        "mean_ms": 25.0,
        "p50_ms": 25.0,
        "p95_ms": 38.5,
    }


def test_empty_latency_metrics_are_well_defined():
    assert intent_metrics.compute_latency_metrics([]) == {
        "unit": "ms",
        "count": 0,
        "mean_ms": 0.0,
        "p50_ms": 0.0,
        "p95_ms": 0.0,
    }


@pytest.mark.parametrize(
    "latencies",
    [[10.0, -1.0], [float("nan")], [float("inf")], ["slow"], [None]],
)
def test_latency_metrics_reject_invalid_values(latencies):
    with pytest.raises(ValueError, match="latency"):
        intent_metrics.compute_latency_metrics(latencies)


def test_run_metrics_include_latency_summary():
    rows = [
        {"gold_intent": "query", "predicted_intent": "query", "latency_ms": 10},
        {"gold_intent": "query", "predicted_intent": "query", "latency_ms": 30},
    ]

    result = intent_eval._compute_metrics(rows)

    assert result["latency"] == {
        "unit": "ms",
        "count": 2,
        "mean_ms": 20.0,
        "p50_ms": 20.0,
        "p95_ms": 29.0,
    }


def test_run_metrics_require_latency_for_every_prediction():
    rows = [{"gold_intent": "query", "predicted_intent": "query"}]

    with pytest.raises(ValueError, match="latency_ms"):
        intent_eval._compute_metrics(rows)


def test_run_metrics_include_failed_prediction_latency():
    rows = [
        {
            "gold_intent": "query",
            "predicted_intent": "other",
            "latency_ms": 100.0,
            "error": "TimeoutError: request timed out",
        },
        {
            "gold_intent": "query",
            "predicted_intent": "query",
            "latency_ms": 20.0,
            "error": None,
        },
    ]

    result = intent_eval._compute_metrics(rows)

    assert result["latency"]["count"] == 2
    assert result["latency"]["mean_ms"] == pytest.approx(60.0)


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
                source_intents={"pattern": "refund"},
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
        "source_intents": {"pattern": "refund"},
        "source_errors": {},
    }]


def test_prediction_error_row_keeps_audit_schema():
    class FailingRecognizer:
        async def recognize(self, message, mode="fusion"):
            raise RuntimeError("boom")

    rows = [{"id": "dev_1", "message": "x", "gold_intent": "other"}]
    result = asyncio.run(generate_predictions(rows, FailingRecognizer()))[0]

    assert result["source_scores"] == {}
    assert result["source_intents"] == {}
    assert result["source_errors"] == {"recognizer": "RuntimeError: boom"}


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
    assert result.source_intents == {
        "llm": "other",
        "embedding": "other",
        "pattern": "greeting",
    }


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


def test_bge_encoder_is_loaded_once_into_configured_cache(monkeypatch, workspace_tmp_path):
    creations = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, cache_folder):
            creations.append((model_name, cache_folder))

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    cache_dir = workspace_tmp_path / "models"
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


def _recognizer_for_vote():
    recognizer = object.__new__(IntentRecognizer)
    recognizer.threshold = 0.5
    return recognizer


def test_fusion_does_not_refine_high_confidence_generic_llm_intent():
    intent, _, scores = _recognizer_for_vote()._vote(
        {"intent": IntentCategory.ESCALATION, "confidence": 0.95},
        {"intent": IntentCategory.HUMAN_HANDOFF, "confidence": 0.686},
        {"intent": IntentCategory.HUMAN_HANDOFF, "confidence": 0.5},
    )

    assert intent == IntentCategory.ESCALATION
    assert "refined_by_consensus" not in scores


def test_fusion_does_not_refine_when_embedding_disagrees_with_pattern():
    intent, _, scores = _recognizer_for_vote()._vote(
        {"intent": IntentCategory.TECHNICAL, "confidence": 0.7},
        {"intent": IntentCategory.TECHNICAL, "confidence": 0.739},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.75},
    )

    assert intent == IntentCategory.TECHNICAL
    assert "refined_by_consensus" not in scores


def test_fusion_refines_low_confidence_generic_llm_when_local_sources_agree():
    intent, confidence, scores = _recognizer_for_vote()._vote(
        {"intent": IntentCategory.TECHNICAL, "confidence": 0.7},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.8},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.75},
    )

    assert intent == IntentCategory.TECHNICAL_CRASH
    assert confidence == pytest.approx(0.8)
    assert scores["refined_by_consensus"] == pytest.approx(0.75)


def test_fusion_consensus_refinement_threshold_boundaries():
    intent, _, _ = _recognizer_for_vote()._vote(
        {"intent": IntentCategory.TECHNICAL, "confidence": 0.79},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.65},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.75},
    )
    assert intent == IntentCategory.TECHNICAL_CRASH

    intent, _, _ = _recognizer_for_vote()._vote(
        {"intent": IntentCategory.TECHNICAL, "confidence": 0.8},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.8},
        {"intent": IntentCategory.TECHNICAL_CRASH, "confidence": 0.8},
    )
    assert intent == IntentCategory.TECHNICAL


def test_fusion_llm_failure_respects_confidence_threshold():
    intent, confidence, _ = _recognizer_for_vote()._vote(
        {"intent": IntentCategory.OTHER, "confidence": 0.0, "failed": True},
        {"intent": IntentCategory.REQUEST, "confidence": 0.2},
        {"intent": IntentCategory.OTHER, "confidence": 0.0},
    )

    assert intent == IntentCategory.OTHER
    assert confidence == pytest.approx(0.2)


def test_recognize_preserves_consensus_refinement_in_audit_scores():
    recognizer = object.__new__(IntentRecognizer)
    recognizer.threshold = 0.5
    recognizer._cache = {}
    recognizer.cache_hits = 0
    recognizer.cache_misses = 0
    recognizer._llm_recognize = AsyncMock(return_value={
        "intent": IntentCategory.TECHNICAL,
        "confidence": 0.7,
    })
    recognizer._embedding_recognize = AsyncMock(return_value={
        "intent": IntentCategory.TECHNICAL_CRASH,
        "confidence": 0.8,
    })
    recognizer._pattern_recognize = Mock(return_value={
        "intent": IntentCategory.TECHNICAL_CRASH,
        "confidence": 0.75,
    })

    result = asyncio.run(recognizer.recognize("app crashed", mode="fusion"))

    assert result.intent == IntentCategory.TECHNICAL_CRASH
    assert result.source_scores["refined_by_consensus"] == pytest.approx(0.75)


def test_local_eval_mode_does_not_require_anthropic_key(monkeypatch):
    created = []

    class FakeRecognizer:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(intent_eval, "_load_environment", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("core.intent_recognizer.IntentRecognizer", FakeRecognizer)

    intent_eval._create_recognizer(None, None, None, mode="embedding_only")

    assert created[0]["api_key"] == "local-mode-unused"


def test_llm_eval_mode_still_requires_anthropic_key(monkeypatch):
    monkeypatch.setattr(intent_eval, "_load_environment", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        intent_eval._create_recognizer(None, None, None, mode="llm_only")


def test_output_directory_must_not_overwrite_existing_run(workspace_tmp_path):
    output_dir = workspace_tmp_path / "existing-run"
    output_dir.mkdir()
    (output_dir / "intent_metrics.json").write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        intent_eval._prepare_output_dir(output_dir)

    assert (output_dir / "intent_metrics.json").read_text(encoding="utf-8") == "old"


def test_output_directory_allows_new_or_empty_directory(workspace_tmp_path):
    new_dir = workspace_tmp_path / "new-run"
    intent_eval._prepare_output_dir(new_dir)
    assert new_dir.is_dir()

    intent_eval._prepare_output_dir(new_dir)


def test_embedding_model_initialization_does_not_block_event_loop(monkeypatch):
    gate = threading.Event()

    class FakeEncoder:
        def encode(self, texts, **kwargs):
            return [[1.0, 0.0] for _ in texts]

    recognizer = IntentRecognizer(api_key="test")

    def wait_for_event_loop():
        gate.wait(timeout=0.5)
        return FakeEncoder()

    monkeypatch.setattr(recognizer, "_get_embedding_encoder", wait_for_event_loop)

    async def run():
        started = time.monotonic()
        task = asyncio.create_task(recognizer._encode_texts(["hello"]))
        await asyncio.sleep(0)
        gate.set()
        vectors = await task
        return time.monotonic() - started, vectors

    elapsed, vectors = asyncio.run(run())

    assert elapsed < 0.2
    assert vectors == [[1.0, 0.0]]


def test_concurrent_embedding_requests_encode_templates_once():
    class SlowEncoder:
        def __init__(self):
            self.calls = 0

        def encode(self, texts, **kwargs):
            self.calls += 1
            time.sleep(0.05)
            return [[1.0, 0.0] for _ in texts]

    encoder = SlowEncoder()
    recognizer = IntentRecognizer(api_key="test", embedding_encoder=encoder)

    async def load_twice():
        await asyncio.gather(
            recognizer._load_template_embeddings(),
            recognizer._load_template_embeddings(),
        )

    asyncio.run(load_twice())

    assert encoder.calls == 1

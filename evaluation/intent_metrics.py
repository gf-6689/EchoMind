"""Deterministic metrics for the frozen intent label set.

This module deliberately has no model or network dependency.  Every intent
evaluation mode should reduce its output to ``gold`` and ``pred`` and call
``compute_intent_metrics`` here.
"""

from __future__ import annotations

from typing import Dict, List, Sequence


INTENT_LABELS: List[str] = [
    "query", "complaint", "request", "greeting", "escalation",
    "technical", "billing", "account", "feedback", "order_status",
    "logistics", "refund", "invoice", "payment_issue", "account_security",
    "technical_login", "technical_crash", "human_handoff", "other",
]


def compute_intent_metrics(
    gold: Sequence[str],
    pred: Sequence[str],
    labels: Sequence[str],
) -> Dict[str, object]:
    """Compute fixed-label accuracy, F1 scores, and a confusion matrix.

    Rows in ``confusion_matrix`` are gold labels and columns are predicted
    labels, both in exactly the order supplied by ``labels``.  The complete
    label list is used even when a class has no predictions, so Macro-F1 is
    stable across runs and modes.
    """
    label_list = list(labels)
    if not label_list or len(set(label_list)) != len(label_list):
        raise ValueError("labels must be a non-empty sequence of unique values")
    if len(gold) != len(pred):
        raise ValueError("gold and pred must have the same length")

    allowed = set(label_list)
    unknown = (set(gold) | set(pred)) - allowed
    if unknown:
        raise ValueError(f"unknown labels: {sorted(unknown)}")

    index = {label: i for i, label in enumerate(label_list)}
    matrix = [[0 for _ in label_list] for _ in label_list]
    for actual, predicted in zip(gold, pred):
        matrix[index[actual]][index[predicted]] += 1

    per_class: Dict[str, Dict[str, float]] = {}
    f1_values = []
    for i, label in enumerate(label_list):
        tp = matrix[i][i]
        fp = sum(matrix[row][i] for row in range(len(label_list))) - tp
        fn = sum(matrix[i]) - tp
        support = sum(matrix[i])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
        f1_values.append(f1)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    correct = sum(matrix[i][i] for i in range(len(label_list)))
    total = len(gold)
    return {
        "accuracy": correct / total if total else 0.0,
        "macro_f1": sum(f1_values) / len(f1_values),
        "per_class": per_class,
        "confusion_matrix": matrix,
        "labels": label_list,
        "total": total,
        "correct": correct,
    }

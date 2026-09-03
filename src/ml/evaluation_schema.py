#!/usr/bin/env python3
"""
Chargeback Sentinel – Versioned Evaluation Schema Builder (src/ml/evaluation_schema.py)
---------------------------------------------------------------------------------------
Authoritative source for building the GET /api/model/evaluation response.

Schema version: 1.0  (MAJOR.MINOR semantic versioning)

MAJOR bump: breaking field removal / rename / type change / semantic change.
MINOR bump: additive optional fields / new optional sections.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

ml_dir = Path(__file__).parent
root_dir = ml_dir.parent.parent
if str(ml_dir) not in sys.path:
    sys.path.insert(0, str(ml_dir))

from features import LABEL_ORDER, edge_case_mask, load_csv, matrix_and_labels  # noqa: E402
try:
    from .score_dispute import StringLabelXGBClassifier  # noqa: F401
except ImportError:
    from score_dispute import StringLabelXGBClassifier  # noqa: F401

main_mod = sys.modules.get("__main__")
if main_mod:
    setattr(main_mod, "StringLabelXGBClassifier", StringLabelXGBClassifier)

# ─── Schema version constant ──────────────────────────────────────────────────
SCHEMA_VERSION = "1.0"

# ─── File locations ───────────────────────────────────────────────────────────
DEFAULT_MODEL_PATH = root_dir / "model.pkl"
DEFAULT_TEST_PATH = root_dir / "data" / "ml" / "test.csv"
CONTEST_COST_INR = 150.0


# ─── Internal validators ──────────────────────────────────────────────────────

class EvaluationValidationError(ValueError):
    """Raised when the computed evaluation data fails internal consistency checks."""


def _validate(
    labels: List[str],
    matrix: List[List[int]],
    total_samples: int,
    correct: int,
    incorrect: int,
    per_class_metrics: List[Dict[str, Any]],
) -> None:
    """Validate internal consistency before returning evaluation data to the API layer."""

    # 1. correctPredictions + incorrectPredictions == totalSamples
    if correct + incorrect != total_samples:
        raise EvaluationValidationError(
            f"correctPredictions({correct}) + incorrectPredictions({incorrect}) "
            f"!= totalSamples({total_samples})"
        )

    # 2. confusionMatrix dimensions: matrix.length === labels.length
    if len(matrix) != len(labels):
        raise EvaluationValidationError(
            f"Confusion matrix row count ({len(matrix)}) != labels count ({len(labels)})"
        )
    for i, row in enumerate(matrix):
        if len(row) != len(labels):
            raise EvaluationValidationError(
                f"Confusion matrix row {i} has {len(row)} columns but expected {len(labels)}"
            )

    # 3. sum(confusionMatrix cells) == totalSamples
    cm_total = sum(cell for row in matrix for cell in row)
    if cm_total != total_samples:
        raise EvaluationValidationError(
            f"Sum of confusion matrix cells ({cm_total}) != totalSamples({total_samples})"
        )

    # 4. sum(perClassMetrics[*].support) == totalSamples
    support_total = sum(m["support"] for m in per_class_metrics)
    if support_total != total_samples:
        raise EvaluationValidationError(
            f"Sum of perClassMetrics support ({support_total}) != totalSamples({support_total})"
        )


# ─── Core builder ─────────────────────────────────────────────────────────────

def build_evaluation(
    model_path: Optional[Path] = None,
    test_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Build and validate the full versioned evaluation payload.

    Returns a dict ready for JSON serialisation in GET /api/model/evaluation.
    Raises EvaluationValidationError if consistency checks fail.
    """
    model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    test_path = Path(test_path) if test_path else DEFAULT_TEST_PATH

    # ── Unavailable state if artifacts are missing ────────────────────────────
    if not model_path.exists() or not test_path.exists():
        return {
            "schemaVersion": SCHEMA_VERSION,
            "evaluation": {
                "status": "unavailable",
                "reason": "Model or test-data file not found. Run `npm run ml:train` first.",
            },
        }

    # ── Load model + test data ────────────────────────────────────────────────
    bundle = joblib.load(model_path)
    records = load_csv(test_path)
    total_samples = len(records)

    if total_samples == 0:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "evaluation": {
                "status": "unavailable",
                "reason": "Test dataset is empty — no samples to evaluate.",
                "dataset": {
                    "path": str(test_path),
                    "totalSamples": 0,
                    "edgeCaseSamples": 0,
                },
            },
        }

    model = bundle["model"]
    feature_names: List[str] = bundle.get("feature_names", [])
    label_order: List[str] = bundle.get("label_order", LABEL_ORDER)
    synthetic_notice: str = bundle.get(
        "synthetic_data_notice",
        "Trained on synthetic noisy labels — not real chargeback outcomes.",
    )
    classes: List[str] = list(model.named_steps["classifier"].classes_)

    # ── Predictions + probabilities ───────────────────────────────────────────
    features_mat, actual = matrix_and_labels(records)
    predicted = list(model.predict(features_mat))
    proba = model.predict_proba(features_mat)

    won_available = "won" in classes
    won_idx = classes.index("won") if won_available else None

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    precision_w = float(precision_score(actual, predicted, average="weighted", zero_division=0))
    recall_w = float(recall_score(actual, predicted, average="weighted", zero_division=0))
    f1_w = float(f1_score(actual, predicted, average="weighted", zero_division=0))

    correct = sum(a == b for a, b in zip(actual, predicted))
    incorrect = total_samples - correct
    accuracy = correct / total_samples

    # ── Confusion matrix ──────────────────────────────────────────────────────
    cm_np = confusion_matrix(actual, predicted, labels=label_order)
    cm_matrix = [row.tolist() for row in cm_np]

    # ── Per-class metrics ─────────────────────────────────────────────────────
    per_class_metrics: List[Dict[str, Any]] = []
    for label in label_order:
        p = float(precision_score(actual, predicted, labels=[label], average="micro", zero_division=0))
        r = float(recall_score(actual, predicted, labels=[label], average="micro", zero_division=0))
        f = float(f1_score(actual, predicted, labels=[label], average="micro", zero_division=0))
        support = actual.count(label)
        per_class_metrics.append({
            "label": label,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f, 4),
            "support": support,
        })

    # ── False-positive cost ───────────────────────────────────────────────────
    fp_records = [
        float(rec["txn_amount"])
        for rec, a, p in zip(records, actual, predicted)
        if p == "won" and a == "lost"
    ]
    fp_count = len(fp_records)
    avg_fp_txn = sum(fp_records) / fp_count if fp_count else None
    total_wasted_contest = fp_count * CONTEST_COST_INR

    # ── Edge case subset ──────────────────────────────────────────────────────
    edge_mask = edge_case_mask(records)
    edge_count = sum(edge_mask)
    edge_records_list = [r for r, m in zip(records, edge_mask) if m]

    edge_metrics: Optional[Dict[str, Any]] = None
    if edge_records_list:
        e_features, e_actual = matrix_and_labels(edge_records_list)
        e_predicted = list(model.predict(e_features))
        edge_metrics = {
            "count": edge_count,
            "precision": round(float(precision_score(e_actual, e_predicted, average="weighted", zero_division=0)), 4),
            "recall": round(float(recall_score(e_actual, e_predicted, average="weighted", zero_division=0)), 4),
            "f1": round(float(f1_score(e_actual, e_predicted, average="weighted", zero_division=0)), 4),
        }

    # ── Misclassified sample cases ───────────────────────────────────────────
    sample_errors: List[Dict[str, Any]] = []
    for rec, a, p, prob in zip(records, actual, predicted, proba):
        if a != p and len(sample_errors) < 10:
            win_p = float(prob[won_idx]) if won_available and won_idx is not None else 0.0
            sample_errors.append({
                "disputeId": str(rec.get("dispute_id", "CB-UNKNOWN")),
                "merchant": str(rec.get("merchant_name", "Merchant Partner")),
                "disputeType": str(rec.get("dispute_type", "product_not_received")),
                "amount": float(rec.get("txn_amount", 0)),
                "actualOutcome": a,
                "predictedOutcome": p,
                "winProbability": round(win_p, 4),
                "errorType": "False Positive (Predicted Won)" if p == "won" and a == "lost" else f"Misclassification ({a} → {p})",
            })

    # ── Win-probability distribution bands (optional – available only if 'won' class exists) ──
    if won_available and won_idx is not None:
        win_probs_list = [float(p[won_idx]) for p in proba]
        bands = {
            "lt40": sum(1 for p in win_probs_list if p < 0.40),
            "40to60": sum(1 for p in win_probs_list if 0.40 <= p < 0.60),
            "60to80": sum(1 for p in win_probs_list if 0.60 <= p < 0.80),
            "gte80": sum(1 for p in win_probs_list if p >= 0.80),
        }
        probability_analysis: Dict[str, Any] = {
            "available": True,
            "targetClass": "won",
            "targetClassNote": "winProbability represents P(class='won') from the Logistic Regression model.",
            "minWinProb": round(min(win_probs_list), 4),
            "maxWinProb": round(max(win_probs_list), 4),
            "scoreBands": bands,
        }
    else:
        probability_analysis = {
            "available": False,
            "reason": "Model does not expose a 'won' class probability.",
        }

    # ── ROC / PR / Calibration: not computed in this evaluation setup ─────────
    roc = {"available": False, "reason": "Multi-class ROC-AUC curve not computed in this evaluation setup.", "auc": None, "curve": []}
    precision_recall_curve = {"available": False, "reason": "Multi-class PR curve not computed in this evaluation setup.", "auc": None, "curve": []}
    calibration = {"available": False, "reason": "Calibration curve not computed in this evaluation setup.", "curve": []}

    # ── Internal consistency validation ───────────────────────────────────────
    _validate(label_order, cm_matrix, total_samples, correct, incorrect, per_class_metrics)

    # ── Governance warnings ───────────────────────────────────────────────────
    governance_warnings: List[str] = [synthetic_notice]
    if f1_w > 0.97:
        governance_warnings.append(
            f"WARNING: Weighted F1 is {f1_w:.4f}. Suspiciously high for this small "
            "synthetic dataset — add more label noise before making production claims."
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "evaluation": {
            "status": "success",

            "dataset": {
                "path": str(test_path),
                "totalSamples": total_samples,
                "edgeCaseSamples": edge_count,
                "classDistribution": {label: actual.count(label) for label in label_order},
            },

            "model": {
                "type": "LogisticRegression (scikit-learn)",
                "pipeline": "StandardScaler → balanced LogisticRegression",
                "featureNames": feature_names,
                "labelOrder": label_order,
                "classes": classes,
            },

            "summary": {
                "accuracy": round(accuracy, 4),
                "precision": round(precision_w, 4),
                "recall": round(recall_w, 4),
                "f1": round(f1_w, 4),
                "f1Average": "weighted",
                "correctPredictions": correct,
                "incorrectPredictions": incorrect,
                "totalSamples": total_samples,
            },

            "perClassMetrics": per_class_metrics,

            "confusionMatrix": {
                "labels": label_order,
                "matrix": cm_matrix,
            },

            "errorAnalysis": {
                "falsePositives": {
                    "description": "Cases predicted 'won' but actual outcome was 'lost'",
                    "count": fp_count,
                    "avgTransactionAmountINR": round(avg_fp_txn, 2) if avg_fp_txn is not None else None,
                    "contestCostPerCaseINR": CONTEST_COST_INR,
                    "totalWastedContestCostINR": round(total_wasted_contest, 2),
                },
                "edgeCaseSubset": edge_metrics,
                "sampleMisclassifications": sample_errors,
            },

            "probabilityAnalysis": probability_analysis,

            "roc": roc,
            "precisionRecall": precision_recall_curve,
            "calibration": calibration,

            "governance": {
                "datasetNotice": synthetic_notice,
                "warnings": governance_warnings,
                "evaluationVersion": SCHEMA_VERSION,
            },
        },
    }

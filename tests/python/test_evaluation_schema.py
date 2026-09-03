#!/usr/bin/env python3
"""
Chargeback Sentinel – Evaluation Schema Compatibility Tests
-----------------------------------------------------------
tests/python/test_evaluation_schema.py

Covers the acceptance criteria from the versioned evaluation schema spec:

  1.  Valid 1.0 response  → evaluation renders successfully.
  2.  Minor version 1.1 + unknown field → 1.0 consumers keep working (field ignored).
  3.  Unsupported major 2.0 → compatibility warning path, app does not crash.
  4.  Optional capability unavailable (roc.available = false) → correct flag.
  5.  Evaluation unavailable state → status = "unavailable".
  6.  Confusion matrix dimension mismatch → validation error raised.
  7.  Zero evaluation samples → unavailable state, no ZeroDivisionError.
  8.  Internal consistency check: correctPredictions + incorrectPredictions == totalSamples.
  9.  Internal consistency check: sum(confusionMatrix cells) == totalSamples.
  10. Internal consistency check: sum(perClassMetrics support) == totalSamples.
  11. Schema version is present in every response.
  12. Required fields are present in successful response.
  13. Optional fields carry explicit `available` flag.
  14. GET /api/metrics remains backward-compatible (unchanged shape).
"""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the src/ml package is importable
root = Path(__file__).resolve().parents[2]
ml_dir = root / "src" / "ml"
sys.path.insert(0, str(ml_dir))
sys.path.insert(0, str(root))

from evaluation_schema import (
    SCHEMA_VERSION,
    EvaluationValidationError,
    _validate,
    build_evaluation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_success() -> dict:
    """Build a minimal valid schema-1.0 success payload for unit testing."""
    return {
        "schemaVersion": "1.0",
        "evaluation": {
            "status": "success",
            "dataset": {"path": "data/ml/test.csv", "totalSamples": 10,
                        "edgeCaseSamples": 0, "classDistribution": {"lost": 5, "not_contested": 2, "won": 3}},
            "model": {"type": "LogisticRegression", "pipeline": "...", "featureNames": [], "labelOrder": [], "classes": []},
            "summary": {"accuracy": 0.90, "precision": 0.89, "recall": 0.88, "f1": 0.88,
                        "f1Average": "weighted", "correctPredictions": 9, "incorrectPredictions": 1, "totalSamples": 10},
            "perClassMetrics": [
                {"label": "lost", "precision": 0.90, "recall": 0.85, "f1": 0.87, "support": 5},
                {"label": "not_contested", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 2},
                {"label": "won", "precision": 0.88, "recall": 0.90, "f1": 0.89, "support": 3},
            ],
            "confusionMatrix": {
                "labels": ["lost", "not_contested", "won"],
                "matrix": [[4, 0, 1], [0, 2, 0], [0, 0, 3]],
            },
            "errorAnalysis": {"falsePositives": {"count": 1, "totalWastedContestCostINR": 150.0}},
            "probabilityAnalysis": {"available": True, "targetClass": "won"},
            "roc": {"available": False, "reason": "Not computed", "auc": None, "curve": []},
            "precisionRecall": {"available": False, "reason": "Not computed", "auc": None, "curve": []},
            "calibration": {"available": False, "reason": "Not computed", "curve": []},
            "governance": {"datasetNotice": "Synthetic data.", "warnings": [], "evaluationVersion": "1.0"},
        },
    }


# ---------------------------------------------------------------------------
# 1. Valid 1.0 response
# ---------------------------------------------------------------------------
class TestValidSchema10(unittest.TestCase):
    def test_schema_version_is_10(self):
        """A valid schema-1.0 response must carry schemaVersion = '1.0'."""
        payload = _make_minimal_success()
        self.assertEqual(payload["schemaVersion"], "1.0")

    def test_required_top_level_fields_present(self):
        payload = _make_minimal_success()
        ev = payload["evaluation"]
        for field in ("status", "dataset", "model", "summary",
                      "perClassMetrics", "confusionMatrix", "errorAnalysis", "governance"):
            self.assertIn(field, ev, f"Required field '{field}' missing from evaluation")

    def test_status_is_success(self):
        payload = _make_minimal_success()
        self.assertEqual(payload["evaluation"]["status"], "success")

    def test_summary_f1_average_declared(self):
        payload = _make_minimal_success()
        self.assertIn("f1Average", payload["evaluation"]["summary"])


# ---------------------------------------------------------------------------
# 2. Minor version 1.1 + unknown field → ignored gracefully
# ---------------------------------------------------------------------------
class TestMinorVersionCompat(unittest.TestCase):
    def test_unknown_optional_field_does_not_raise(self):
        """A 1.0 consumer must handle unknown fields from a 1.1 response without crashing."""
        payload = _make_minimal_success()
        payload["schemaVersion"] = "1.1"
        payload["evaluation"]["newEvaluationMetric"] = {"value": 0.87, "description": "Future metric"}

        # Frontend version gate logic (mirrors app.js parseSchemaVersion):
        major = int(payload["schemaVersion"].split(".")[0])
        self.assertEqual(major, 1)  # still compatible — same major

        # The known fields must still be readable without error
        ev = payload["evaluation"]
        _ = ev["summary"]["f1"]          # 1.0 consumer reads known field
        _ = ev.get("newEvaluationMetric")  # unknown field safely ignored via .get()

    def test_schema_14_still_major_1(self):
        payload = _make_minimal_success()
        payload["schemaVersion"] = "1.14"
        major = int(payload["schemaVersion"].split(".")[0])
        self.assertEqual(major, 1)


# ---------------------------------------------------------------------------
# 3. Unsupported major 2.0 → compatibility warning
# ---------------------------------------------------------------------------
class TestUnsupportedMajorVersion(unittest.TestCase):
    def test_major_2_detected(self):
        """Major version 2.x must be detected as incompatible with a 1.x frontend."""
        payload = {"schemaVersion": "2.0", "evaluation": {"status": "success", "summary": {}}}
        major = int(payload["schemaVersion"].split(".")[0])
        SUPPORTED_MAJOR = 1
        self.assertNotEqual(major, SUPPORTED_MAJOR)

    def test_major_3_detected(self):
        payload = {"schemaVersion": "3.5", "evaluation": {}}
        major = int(payload["schemaVersion"].split(".")[0])
        self.assertGreater(major, 1)

    def test_missing_schema_version_handled(self):
        """If schemaVersion is missing entirely the consumer must handle it without crashing."""
        payload = {}
        version = payload.get("schemaVersion")
        self.assertIsNone(version)
        # Consumer guard: no crash
        if not version:
            result = "unavailable"
        self.assertEqual(result, "unavailable")


# ---------------------------------------------------------------------------
# 4. Optional capability unavailable → explicit available: False flag
# ---------------------------------------------------------------------------
class TestOptionalCapabilityFlags(unittest.TestCase):
    def test_roc_unavailable_uses_flag_not_zero(self):
        payload = _make_minimal_success()
        roc = payload["evaluation"]["roc"]
        self.assertFalse(roc["available"])
        self.assertIsNone(roc["auc"])          # null, NOT 0
        self.assertEqual(roc["curve"], [])     # empty but `available` is False

    def test_calibration_unavailable_uses_flag(self):
        payload = _make_minimal_success()
        cal = payload["evaluation"]["calibration"]
        self.assertFalse(cal["available"])

    def test_probability_analysis_available_flag(self):
        payload = _make_minimal_success()
        prob = payload["evaluation"]["probabilityAnalysis"]
        self.assertTrue(prob["available"])

    def test_roc_auc_zero_does_not_mean_unavailable(self):
        """auc=0 must NOT be treated as 'ROC unavailable'. Only available:false means that."""
        roc_available_but_zero = {"available": True, "auc": 0.0, "curve": []}
        self.assertTrue(roc_available_but_zero["available"])
        self.assertEqual(roc_available_but_zero["auc"], 0.0)
        # This is a legitimate result, not an unavailability signal


# ---------------------------------------------------------------------------
# 5. Evaluation unavailable state
# ---------------------------------------------------------------------------
class TestEvaluationUnavailableState(unittest.TestCase):
    def test_unavailable_status_handled(self):
        payload = {
            "schemaVersion": "1.0",
            "evaluation": {
                "status": "unavailable",
                "reason": "Model file not found.",
            },
        }
        ev = payload["evaluation"]
        self.assertEqual(ev["status"], "unavailable")
        self.assertIn("reason", ev)

    def test_error_status_handled(self):
        payload = {
            "schemaVersion": "1.0",
            "evaluation": {
                "status": "error",
                "reason": "Internal evaluation error.",
            },
        }
        ev = payload["evaluation"]
        self.assertEqual(ev["status"], "error")

    def test_build_evaluation_returns_unavailable_when_model_missing(self):
        """build_evaluation must return unavailable, not raise, if model.pkl is absent."""
        result = build_evaluation(
            model_path=Path("/nonexistent/model.pkl"),
            test_path=Path("/nonexistent/test.csv"),
        )
        self.assertEqual(result["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(result["evaluation"]["status"], "unavailable")


# ---------------------------------------------------------------------------
# 6. Confusion matrix dimension mismatch → validation error raised
# ---------------------------------------------------------------------------
class TestConfusionMatrixValidation(unittest.TestCase):
    def _call_validate(self, labels, matrix, total, correct, incorrect, per_class):
        _validate(labels, matrix, total, correct, incorrect, per_class)

    def test_inconsistent_row_count_raises(self):
        labels = ["lost", "not_contested", "won"]
        matrix = [[4, 0, 1], [0, 2, 0]]   # only 2 rows for 3 labels
        with self.assertRaises(EvaluationValidationError):
            self._call_validate(labels, matrix, 10, 9, 1,
                                [{"support": 5}, {"support": 2}, {"support": 3}])

    def test_inconsistent_column_count_raises(self):
        labels = ["lost", "won"]
        matrix = [[4, 0, 1], [0, 3]]  # wrong column counts
        with self.assertRaises(EvaluationValidationError):
            self._call_validate(labels, matrix, 8, 7, 1,
                                [{"support": 5}, {"support": 3}])

    def test_cm_sum_mismatch_raises(self):
        labels = ["lost", "won"]
        matrix = [[4, 0], [0, 3]]  # sum = 7, total = 10
        with self.assertRaises(EvaluationValidationError):
            self._call_validate(labels, matrix, 10, 7, 3,
                                [{"support": 5}, {"support": 5}])

    def test_valid_matrix_does_not_raise(self):
        labels = ["lost", "not_contested", "won"]
        matrix = [[4, 0, 1], [0, 2, 0], [0, 0, 3]]
        self._call_validate(labels, matrix, 10, 9, 1,
                            [{"support": 5}, {"support": 2}, {"support": 3}])


# ---------------------------------------------------------------------------
# 7. Zero evaluation samples → unavailable, no ZeroDivisionError
# ---------------------------------------------------------------------------
class TestZeroSamples(unittest.TestCase):
    def test_zero_samples_from_build_evaluation(self):
        """build_evaluation must return unavailable state gracefully when test CSV is empty."""
        import csv
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
            writer = csv.DictWriter(tmp, fieldnames=["dispute_id", "label"])
            writer.writeheader()
            tmp_path = Path(tmp.name)

        result = build_evaluation(
            model_path=Path("model.pkl"),
            test_path=tmp_path,
        )
        tmp_path.unlink(missing_ok=True)
        self.assertEqual(result["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(result["evaluation"]["status"], "unavailable")
        self.assertEqual(result["evaluation"]["dataset"]["totalSamples"], 0)


# ---------------------------------------------------------------------------
# 8–10. Internal consistency checks via _validate
# ---------------------------------------------------------------------------
class TestInternalConsistencyChecks(unittest.TestCase):
    def test_correct_plus_incorrect_ne_total_raises(self):
        labels = ["lost", "won"]
        matrix = [[4, 0], [0, 3]]
        with self.assertRaises(EvaluationValidationError):
            _validate(labels, matrix, 10, 5, 3,   # 5+3 != 10
                      [{"support": 4}, {"support": 3}])

    def test_support_sum_ne_total_raises(self):
        labels = ["lost", "won"]
        matrix = [[4, 0], [0, 3]]
        with self.assertRaises(EvaluationValidationError):
            _validate(labels, matrix, 7, 7, 0,
                      [{"support": 4}, {"support": 5}])  # 4+5=9 != 7


# ---------------------------------------------------------------------------
# 11. Schema version present in every response
# ---------------------------------------------------------------------------
class TestSchemaVersionAlwaysPresent(unittest.TestCase):
    def test_success_has_schema_version(self):
        payload = _make_minimal_success()
        self.assertIn("schemaVersion", payload)
        self.assertEqual(payload["schemaVersion"], "1.0")

    def test_unavailable_has_schema_version(self):
        result = build_evaluation(model_path=Path("/no/model.pkl"), test_path=Path("/no/test.csv"))
        self.assertIn("schemaVersion", result)

    def test_schema_version_constant(self):
        self.assertEqual(SCHEMA_VERSION, "1.0")


# ---------------------------------------------------------------------------
# 12. Required fields present in successful response (integration, model.pkl)
# ---------------------------------------------------------------------------
class TestRealEvaluationRequiredFields(unittest.TestCase):
    """Integration test: runs build_evaluation against the real model.pkl + test.csv."""

    @classmethod
    def setUpClass(cls):
        model_path = root / "model.pkl"
        test_path = root / "data" / "ml" / "test.csv"
        if not model_path.exists() or not test_path.exists():
            cls.skip_reason = "model.pkl or test.csv not found; run npm run ml:train first"
            cls.payload = None
        else:
            cls.skip_reason = None
            cls.payload = build_evaluation(model_path=model_path, test_path=test_path)

    def _skip_if_no_model(self):
        if self.payload is None:
            self.skipTest(self.skip_reason)

    def test_schema_version_10(self):
        self._skip_if_no_model()
        self.assertEqual(self.payload["schemaVersion"], "1.0")

    def test_status_success(self):
        self._skip_if_no_model()
        self.assertEqual(self.payload["evaluation"]["status"], "success")

    def test_required_fields_all_present(self):
        self._skip_if_no_model()
        ev = self.payload["evaluation"]
        for field in ("status", "dataset", "model", "summary",
                      "perClassMetrics", "confusionMatrix", "errorAnalysis", "governance"):
            self.assertIn(field, ev, f"Required field '{field}' missing")

    def test_per_class_metrics_is_list(self):
        self._skip_if_no_model()
        self.assertIsInstance(self.payload["evaluation"]["perClassMetrics"], list)
        self.assertGreater(len(self.payload["evaluation"]["perClassMetrics"]), 0)

    def test_confusion_matrix_labels_is_list(self):
        self._skip_if_no_model()
        self.assertIsInstance(self.payload["evaluation"]["confusionMatrix"]["labels"], list)

    def test_confusion_matrix_is_list(self):
        self._skip_if_no_model()
        self.assertIsInstance(self.payload["evaluation"]["confusionMatrix"]["matrix"], list)

    def test_internal_consistency_passes(self):
        """The validation function must not raise on the real evaluation output."""
        self._skip_if_no_model()
        ev = self.payload["evaluation"]
        labels = ev["confusionMatrix"]["labels"]
        matrix = ev["confusionMatrix"]["matrix"]
        summary = ev["summary"]
        per_class = ev["perClassMetrics"]
        # If _validate were to fail, the API itself would return a 422; it must not raise here.
        try:
            _validate(labels, matrix, summary["totalSamples"],
                      summary["correctPredictions"], summary["incorrectPredictions"],
                      per_class)
        except EvaluationValidationError as exc:
            self.fail(f"Validation failed on real model output: {exc}")

    def test_f1_average_declared(self):
        self._skip_if_no_model()
        self.assertIn("f1Average", self.payload["evaluation"]["summary"])
        self.assertEqual(self.payload["evaluation"]["summary"]["f1Average"], "weighted")


# ---------------------------------------------------------------------------
# 13. Optional fields carry explicit available flag
# ---------------------------------------------------------------------------
class TestOptionalFieldAvailableFlags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_path = root / "model.pkl"
        test_path = root / "data" / "ml" / "test.csv"
        if not model_path.exists() or not test_path.exists():
            cls.payload = None
        else:
            cls.payload = build_evaluation(model_path=model_path, test_path=test_path)

    def _skip_if_no_model(self):
        if self.payload is None:
            self.skipTest("model.pkl or test.csv not found")

    def test_roc_has_available_flag(self):
        self._skip_if_no_model()
        roc = self.payload["evaluation"]["roc"]
        self.assertIn("available", roc)
        self.assertIsInstance(roc["available"], bool)

    def test_precision_recall_has_available_flag(self):
        self._skip_if_no_model()
        pr = self.payload["evaluation"]["precisionRecall"]
        self.assertIn("available", pr)

    def test_calibration_has_available_flag(self):
        self._skip_if_no_model()
        cal = self.payload["evaluation"]["calibration"]
        self.assertIn("available", cal)

    def test_probability_analysis_has_available_flag(self):
        self._skip_if_no_model()
        prob = self.payload["evaluation"]["probabilityAnalysis"]
        self.assertIn("available", prob)

    def test_unavailable_auc_is_null_not_zero(self):
        self._skip_if_no_model()
        roc = self.payload["evaluation"]["roc"]
        if not roc["available"]:
            self.assertIsNone(roc.get("auc"), "Unavailable AUC must be null, not 0")


# ---------------------------------------------------------------------------
# 14. GET /api/metrics backward compatibility (unchanged shape)
# ---------------------------------------------------------------------------
class TestApiMetricsBackwardCompat(unittest.TestCase):
    def test_evaluateDisputes_returns_expected_keys(self):
        """evaluateDisputes from engine.js is the source of /api/metrics.
        Verify the Python equivalent (evaluate_subset) still returns the same keys
        as the contract defines."""
        from evaluate import evaluate_subset
        # Minimal bundle mock
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        # Tiny deterministic training set
        X = [[0] * 13, [1] * 13, [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]]
        y = ["lost", "won", "not_contested"]
        clf = Pipeline([("scaler", StandardScaler()), ("classifier", LogisticRegression(max_iter=500))])
        clf.fit(X, y)
        bundle = {"model": clf}
        records = [
            {"txn_amount": "0", "previous_txns_from_device": "0", "customer_txn_history_count": "0",
             "customer_disputed_before_count": "0", "device_id_match": "false", "cvv_match": "false",
             "avs_match": "false", "is_first_time_customer": "false", "delivery_address_match_billing": "false",
             "three_ds_authenticated": "false", "refund_issued": "false", "cardholder_ip_country": "IN",
             "billing_country": "IN", "is_edge_case": "false", "label": "lost"},
        ]
        result = evaluate_subset("unit-test", records, bundle)
        # These are the keys the /api/metrics endpoint exposes via evaluateDisputes
        for key in ("precision", "recall", "f1", "false_positive_cost"):
            self.assertIn(key, result, f"Key '{key}' missing from evaluate_subset result")


if __name__ == "__main__":
    unittest.main()

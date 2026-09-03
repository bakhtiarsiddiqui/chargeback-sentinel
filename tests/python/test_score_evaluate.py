import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path for direct execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib

from src.ml.evaluate import false_positive_cost
from src.ml.features import FEATURE_NAMES, record_to_features
from src.ml.generate_data import generate_dataset, write_csv
from src.ml.score_dispute import predict_win_probability, train_model


class ScoreEvaluateTests(unittest.TestCase):
    def test_feature_vector_includes_completeness_score(self) -> None:
        record = {
            "txn_amount": "1000",
            "device_id_match": "true",
            "previous_txns_from_device": "1",
            "cvv_match": "true",
            "avs_match": "true",
            "customer_txn_history_count": "2",
            "is_first_time_customer": "false",
            "delivery_address_match_billing": "true",
            "customer_disputed_before_count": "0",
            "three_ds_authenticated": "true",
            "refund_issued": "false",
            "is_edge_case": "false",
            "cardholder_ip_country": "IN",
            "billing_country": "IN",
            "label": "won",
        }
        features = record_to_features(record)
        self.assertEqual(len(features), len(FEATURE_NAMES))
        self.assertEqual(features[FEATURE_NAMES.index("completeness_score")], 1.0)

    def test_train_model_can_predict_win_probability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            train_path = Path(tmpdir) / "train.csv"
            splits = generate_dataset()
            write_csv(train_path, splits["train"])
            model = train_model(train_path)
            probability = predict_win_probability(model, splits["train"][0])
            self.assertGreaterEqual(probability, 0.0)
            self.assertLessEqual(probability, 1.0)

    def test_false_positive_cost_reports_count_and_flat_waste(self) -> None:
        records = [{"txn_amount": "1000"}, {"txn_amount": "3000"}, {"txn_amount": "900"}]
        actual = ["lost", "lost", "won"]
        predicted = ["won", "lost", "won"]
        result = false_positive_cost(records, actual, predicted)
        self.assertEqual(result["fp_count"], 1)
        self.assertEqual(result["avg_fp_txn_amount"], 1000.0)
        self.assertEqual(result["avg_wasted_contest_cost_per_fp"], 150.0)
        self.assertEqual(result["total_wasted_contest_cost"], 150.0)

    def test_model_bundle_round_trips_with_joblib(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            train_path = Path(tmpdir) / "train.csv"
            model_path = Path(tmpdir) / "model.pkl"
            splits = generate_dataset()
            write_csv(train_path, splits["train"])
            model = train_model(train_path)
            joblib.dump({"model": model, "feature_names": FEATURE_NAMES}, model_path)
            loaded = joblib.load(model_path)
            self.assertEqual(loaded["feature_names"], FEATURE_NAMES)


if __name__ == "__main__":
    unittest.main()

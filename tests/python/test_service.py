import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure project root is in sys.path for direct execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
from fastapi.testclient import TestClient

from src.ml.generate_data import generate_dataset, write_csv
from src.ml.score_dispute import train_model


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        train_path = Path(cls._tmpdir.name) / "train.csv"
        model_path = Path(cls._tmpdir.name) / "model.pkl"

        splits = generate_dataset()
        write_csv(train_path, splits["train"])
        model = train_model(train_path)
        joblib.dump(
            {"model": model, "synthetic_data_notice": "Trained on synthetic test data."},
            model_path,
        )

        cls._model_patch = patch("src.ml.service.MODEL_PATH", model_path)
        cls._model_patch.start()

        import src.ml.service as service_module

        service_module._bundle = joblib.load(model_path)
        cls.client = TestClient(service_module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._model_patch.stop()
        cls._tmpdir.cleanup()

    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "DisputeWinProbabilityAgent")
        self.assertTrue(payload["modelLoaded"])

    def test_score_endpoint_returns_win_probability(self) -> None:
        response = self.client.post(
            "/score",
            json={
                "txn_amount": 4500.0,
                "previous_txns_from_device": 2.0,
                "customer_txn_history_count": 3.0,
                "customer_disputed_before_count": 0.0,
                "device_id_match": True,
                "cvv_match": True,
                "avs_match": True,
                "is_first_time_customer": False,
                "delivery_address_match_billing": True,
                "three_ds_authenticated": True,
                "refund_issued": False,
                "ip_country_matches_billing_country": True,
                "completeness_score": 0.95,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["agent"], "DisputeWinProbabilityAgent")
        self.assertIn("winProbability", payload)
        self.assertGreaterEqual(payload["winProbability"], 0.0)
        self.assertLessEqual(payload["winProbability"], 1.0)
        self.assertIn("modelType", payload)
        self.assertIn("dataNotice", payload)


if __name__ == "__main__":
    unittest.main()

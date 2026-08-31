import unittest

from verify_evidence import verify_evidence


class VerifyEvidenceTests(unittest.TestCase):
    def test_all_evidence_present(self) -> None:
        record = {
            "three_ds_authenticated": True,
            "avs_match": True,
            "cvv_match": True,
            "previous_txns_from_device": 3,
            "cardholder_ip_country": "IN",
            "billing_country": "IN",
            "customer_txn_history_count": 5,
        }
        result = verify_evidence(record)
        self.assertEqual(result["completeness_score"], 1.0)
        self.assertEqual(result["missing_items"], [])
        self.assertEqual(len(result["present_items"]), 5)

    def test_missing_3ds_only(self) -> None:
        record = {
            "three_ds_authenticated": False,
            "avs_match": True,
            "cvv_match": True,
            "previous_txns_from_device": 2,
            "cardholder_ip_country": "IN",
            "billing_country": "IN",
            "customer_txn_history_count": 4,
        }
        result = verify_evidence(record)
        self.assertEqual(result["completeness_score"], 0.8)
        self.assertEqual(result["missing_items"], ["3DS authentication proof"])

    def test_contradictory_avs_cvv_fails_joint_check(self) -> None:
        record = {
            "three_ds_authenticated": True,
            "avs_match": True,
            "cvv_match": False,
            "previous_txns_from_device": 1,
            "cardholder_ip_country": "IN",
            "billing_country": "IN",
            "customer_txn_history_count": 2,
        }
        result = verify_evidence(record)
        self.assertIn("AVS/CVV match", result["missing_items"])
        self.assertEqual(result["completeness_score"], 0.8)

    def test_geo_mismatch_and_no_device_history(self) -> None:
        record = {
            "three_ds_authenticated": True,
            "avs_match": True,
            "cvv_match": True,
            "previous_txns_from_device": 0,
            "cardholder_ip_country": "AE",
            "billing_country": "IN",
            "customer_txn_history_count": 3,
        }
        result = verify_evidence(record)
        self.assertCountEqual(
            result["missing_items"],
            ["Device history", "Geo-consistency"],
        )
        self.assertEqual(result["completeness_score"], 0.6)

    def test_first_time_customer_with_weak_signals(self) -> None:
        record = {
            "three_ds_authenticated": False,
            "avs_match": False,
            "cvv_match": False,
            "previous_txns_from_device": 0,
            "cardholder_ip_country": "US",
            "billing_country": "IN",
            "customer_txn_history_count": 0,
        }
        result = verify_evidence(record)
        self.assertEqual(result["completeness_score"], 0.0)
        self.assertEqual(len(result["present_items"]), 0)
        self.assertEqual(len(result["missing_items"]), 5)


if __name__ == "__main__":
    unittest.main()

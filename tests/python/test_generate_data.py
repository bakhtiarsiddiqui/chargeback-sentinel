import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.ml.generate_data import FIELDNAMES, generate_dataset, write_csv


class GenerateDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.splits = generate_dataset()
        self.all_records = [record for rows in self.splits.values() for record in rows]

    def test_total_record_count_and_split_sizes(self) -> None:
        self.assertEqual(len(self.all_records), 50000)
        total_train = len(self.splits["train"])
        total_val = len(self.splits["val"])
        total_test = len(self.splits["test"])
        self.assertEqual(total_train + total_val + total_test, 50000)
        self.assertTrue(34000 <= total_train <= 36000)
        self.assertTrue(7000 <= total_val <= 8000)
        self.assertTrue(7000 <= total_test <= 8000)

    def test_schema_fields_are_present(self) -> None:
        for record in self.all_records[:10]:
            self.assertEqual(set(record.keys()), set(FIELDNAMES))

    def test_edge_case_count_is_tagged(self) -> None:
        edge_records = [record for record in self.all_records if record["is_edge_case"]]
        self.assertGreaterEqual(len(edge_records), 44)
        self.assertLessEqual(len(edge_records), 50)

    def test_label_distribution_is_close_to_requested_target(self) -> None:
        counts = Counter(record["label"] for record in self.all_records)
        self.assertTrue(13500 <= counts["won"] <= 16500)
        self.assertTrue(25000 <= counts["lost"] <= 30000)
        self.assertTrue(6000 <= counts["not_contested"] <= 9000)

    def test_each_split_contains_edge_cases_and_labels(self) -> None:
        for split_name, records in self.splits.items():
            with self.subTest(split=split_name):
                counts = Counter((record["label"], record["is_edge_case"]) for record in records)
                self.assertGreater(sum(1 for record in records if record["is_edge_case"]), 0)
                self.assertGreater(counts[("won", False)] + counts[("won", True)], 0)
                self.assertGreater(counts[("lost", False)] + counts[("lost", True)], 0)
                self.assertGreater(counts[("not_contested", False)] + counts[("not_contested", True)], 0)

    def test_not_contested_always_has_refund_issued(self) -> None:
        for record in self.all_records:
            if record["label"] == "not_contested":
                self.assertTrue(record["refund_issued"])

    def test_csv_writer_uses_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.csv"
            write_csv(path, self.splits["train"][:3])
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, FIELDNAMES)
                rows = list(reader)
            self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()

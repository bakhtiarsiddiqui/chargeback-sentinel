#!/usr/bin/env python3
"""
Chargeback Sentinel - Model Evaluator
------------------------------------
Evaluates model precision, recall, weighted F1 score, confusion matrix, and cost-benefit metrics.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Sequence

import joblib
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

try:
    from .features import LABEL_ORDER, edge_case_mask, load_csv, matrix_and_labels
except ImportError:
    from features import LABEL_ORDER, edge_case_mask, load_csv, matrix_and_labels


DEFAULT_MODEL_PATH = Path("model.pkl")
DEFAULT_TEST_PATH = Path("data/ml/test.csv")
CONTEST_COST_INR = 150.0


def print_table(title: str, rows: Sequence[Sequence[object]]) -> None:
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    print(f"\n{title}")
    print("-" * len(title))
    for row_index, row in enumerate(rows):
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            print("  ".join("-" * width for width in widths))


def false_positive_cost(records: Sequence[dict], actual: Sequence[str], predicted: Sequence[str]) -> dict:
    false_positive_amounts = [
        float(record["txn_amount"])
        for record, actual_label, predicted_label in zip(records, actual, predicted)
        if predicted_label == "won" and actual_label == "lost"
    ]
    fp_count = len(false_positive_amounts)
    avg_txn_amount = sum(false_positive_amounts) / fp_count if fp_count else 0.0
    total_wasted_contest_cost = fp_count * CONTEST_COST_INR

    return {
        "fp_count": fp_count,
        "avg_fp_txn_amount": avg_txn_amount,
        "avg_wasted_contest_cost_per_fp": CONTEST_COST_INR if fp_count else 0.0,
        "total_wasted_contest_cost": total_wasted_contest_cost,
    }


def evaluate_subset(title: str, records: List[dict], model_bundle: dict) -> dict:
    model = model_bundle["model"]
    features, actual = matrix_and_labels(records)
    predicted = list(model.predict(features))

    precision = precision_score(actual, predicted, average="weighted", zero_division=0)
    recall = recall_score(actual, predicted, average="weighted", zero_division=0)
    f1 = f1_score(actual, predicted, average="weighted", zero_division=0)
    fp_cost = false_positive_cost(records, actual, predicted)

    print_table(
        f"{title} metrics",
        [
            ("metric", "value"),
            ("precision_weighted", f"{precision:.4f}"),
            ("recall_weighted", f"{recall:.4f}"),
            ("f1_weighted", f"{f1:.4f}"),
            ("false_positive_count_pred_won_actual_lost", fp_cost["fp_count"]),
            ("avg_false_positive_txn_amount_inr", f"{fp_cost['avg_fp_txn_amount']:.2f}"),
            ("avg_wasted_contest_cost_per_fp_inr", f"{fp_cost['avg_wasted_contest_cost_per_fp']:.2f}"),
            ("total_wasted_contest_cost_inr", f"{fp_cost['total_wasted_contest_cost']:.2f}"),
        ],
    )

    matrix = confusion_matrix(actual, predicted, labels=LABEL_ORDER)
    matrix_rows = [("actual\\pred", *LABEL_ORDER)]
    for label, row in zip(LABEL_ORDER, matrix):
        matrix_rows.append((label, *row.tolist()))
    print_table(f"{title} confusion matrix", matrix_rows)

    if f1 > 0.97:
        print(
            f"\nWARNING: {title} weighted F1 is {f1:.4f}. "
            "That is suspiciously high for this small synthetic dataset; add more label noise "
            "or reduce feature separability before making demo claims."
        )

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_cost": fp_cost,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate synthetic chargeback scorer on held-out test data.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--test", type=Path, default=DEFAULT_TEST_PATH)
    args = parser.parse_args()

    model_bundle = joblib.load(args.model)
    records = load_csv(args.test)
    edge_mask = edge_case_mask(records)
    edge_records = [record for record, is_edge in zip(records, edge_mask) if is_edge]

    print("Synthetic dataset notice: metrics below are from noisy, rule-derived hackathon labels.")
    print(f"Loaded model: {args.model.resolve()}")
    print(f"Loaded test split: {args.test.resolve()} ({len(records)} rows, {len(edge_records)} edge cases)")

    evaluate_subset("Held-out test", records, model_bundle)
    if edge_records:
        evaluate_subset("Edge-case only", edge_records, model_bundle)
    else:
        print("\nEdge-case only metrics skipped because the test split has no edge cases.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
#Train an explainable logistic-regression win-probability scorer.

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml_features import FEATURE_NAMES, LABEL_ORDER, load_csv, matrix_and_labels


DEFAULT_TRAIN_PATH = Path("data/ml/train.csv")
DEFAULT_MODEL_PATH = Path("model.pkl")


def train_model(train_path: Path = DEFAULT_TRAIN_PATH) -> Pipeline:
    records = load_csv(train_path)
    features, labels = matrix_and_labels(records)
    model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=20260829,
                ),
            ),
        ]
    )
    model.fit(features, labels)
    return model


def sorted_coefficients(model: Pipeline) -> list[tuple[str, str, float]]:
    classifier = model.named_steps["classifier"]
    coefficients = classifier.coef_
    classes = list(classifier.classes_)
    rows = []

    for class_index, class_name in enumerate(classes):
        for feature_index, feature_name in enumerate(FEATURE_NAMES):
            rows.append((class_name, feature_name, float(coefficients[class_index][feature_index])))

    return sorted(rows, key=lambda row: abs(row[2]), reverse=True)


def sanity_check_coefficients(model: Pipeline) -> list[str]:
    classifier = model.named_steps["classifier"]
    classes = list(classifier.classes_)
    warnings = []

    if "won" in classes:
        won_index = classes.index("won")
        won_coefficients = classifier.coef_[won_index]
        by_name = dict(zip(FEATURE_NAMES, won_coefficients))
        expected_positive = ["three_ds_authenticated", "avs_match", "cvv_match", "completeness_score"]
        expected_negative = ["refund_issued", "is_first_time_customer", "customer_disputed_before_count"]

        for feature in expected_positive:
            if by_name.get(feature, 0) <= 0:
                warnings.append(f"Expected positive coefficient for won::{feature}, got {by_name.get(feature, 0):.4f}")
        for feature in expected_negative:
            if by_name.get(feature, 0) >= 0:
                warnings.append(f"Expected negative coefficient for won::{feature}, got {by_name.get(feature, 0):.4f}")

    return warnings


def print_coefficients(model: Pipeline) -> None:
    print("Synthetic dataset notice: trained on noisy, rule-derived hackathon labels, not real chargeback outcomes.")
    print("\nFitted logistic-regression coefficients sorted by absolute magnitude:")
    print(f"{'class':<16} {'feature':<36} {'coefficient':>12}")
    print("-" * 68)
    for class_name, feature_name, coefficient in sorted_coefficients(model):
        print(f"{class_name:<16} {feature_name:<36} {coefficient:>12.4f}")

    warnings = sanity_check_coefficients(model)
    if warnings:
        print("\nCoefficient sanity warnings:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("\nCoefficient sanity check passed for the main win/loss indicators.")


def predict_win_probability(model: Pipeline, record: dict) -> float:
    from ml_features import record_to_features

    probabilities = model.predict_proba([record_to_features(record)])[0]
    class_index = list(model.named_steps["classifier"].classes_).index("won")
    return float(probabilities[class_index])


def main() -> None:
    parser = argparse.ArgumentParser(description="Train synthetic chargeback logistic regression scorer.")
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN_PATH)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()

    model = train_model(args.train)
    joblib.dump(
        {
            "model": model,
            "feature_names": FEATURE_NAMES,
            "label_order": LABEL_ORDER,
            "synthetic_data_notice": "Synthetic noisy labels, not real chargeback outcomes.",
        },
        args.model,
    )
    print(f"Saved model to {args.model.resolve()}")
    print_coefficients(model)


if __name__ == "__main__":
    main()


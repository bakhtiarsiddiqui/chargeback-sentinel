#!/usr/bin/env python3
"""
Chargeback Sentinel – Calibrated XGBoost Model Trainer & Scorer (src/ml/score_dispute.py)
---------------------------------------------------------------------------------------
Trains a production-grade Calibrated XGBoost Classifier for dispute win-probability scoring.

Key Requirements:
  1. Input Schema: 13 snake_case features (FEATURE_NAMES).
  2. Target Labels: ['won', 'lost', 'not_contested'] (LABEL_ORDER).
  3. Model Architecture: CalibratedClassifierCV wrapping XGBClassifier with method='sigmoid' (Platt scaling).
  4. Bundle output: 'model.pkl' joblib bundle with (scaler + calibrated_xgb) pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

try:
    from .features import FEATURE_NAMES, LABEL_ORDER, load_csv, matrix_and_labels
except ImportError:
    from features import FEATURE_NAMES, LABEL_ORDER, load_csv, matrix_and_labels


DEFAULT_TRAIN_PATH = Path("data/ml/train.csv")
DEFAULT_MODEL_PATH = Path("model.pkl")


# ─── Custom scikit-learn wrapper for string labels + XGBoost ──────────────────

class StringLabelXGBClassifier(BaseEstimator, ClassifierMixin):
    """
    Scikit-learn compatible estimator wrapping XGBClassifier to seamlessly handle
    string target labels ('won', 'lost', 'not_contested') inside CalibratedClassifierCV.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 4,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        random_state: int = 20260829,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.random_state = random_state

        self.label_encoder = LabelEncoder()
        self.xgb = XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            random_state=self.random_state,
            eval_metric="mlogloss",
            objective="multi:softprob",
        )

    def fit(self, X: Any, y: Any) -> StringLabelXGBClassifier:
        y_encoded = self.label_encoder.fit_transform(y)
        self.classes_ = self.label_encoder.classes_
        self.xgb.fit(X, y_encoded)
        return self

    def predict(self, X: Any) -> np.ndarray:
        y_pred = self.xgb.predict(X)
        return self.label_encoder.inverse_transform(y_pred)

    def predict_proba(self, X: Any) -> np.ndarray:
        return self.xgb.predict_proba(X)


# ─── Training Pipeline Builder ────────────────────────────────────────────────

def train_model(
    train_path: Path = DEFAULT_TRAIN_PATH,
    calibration_method: str = "sigmoid",
    cv_folds: int = 5,
) -> Pipeline:
    """
    Train a Calibrated XGBoost model wrapped in a StandardScaler pipeline.

    - Calibration method: 'sigmoid' (Platt scaling) or 'isotonic'.
    - 5-fold cross-validation calibration for well-calibrated win probabilities.
    """
    records = load_csv(train_path)
    features, labels = matrix_and_labels(records)

    base_xgb = StringLabelXGBClassifier(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=20260829,
    )

    calibrated_classifier = CalibratedClassifierCV(
        estimator=base_xgb,
        method=calibration_method,
        cv=cv_folds,
    )

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", calibrated_classifier),
        ]
    )

    pipeline.fit(features, labels)
    return pipeline


# ─── Feature Importances Extraction ──────────────────────────────────────────

def feature_importances(model: Pipeline) -> List[Tuple[str, float]]:
    """Extract averaged XGBoost feature importances across calibration folds."""
    classifier = model.named_steps["classifier"]
    if hasattr(classifier, "calibrated_classifiers_"):
        importances_list = [
            cal.estimator.xgb.feature_importances_
            for cal in classifier.calibrated_classifiers_
            if hasattr(cal.estimator, "xgb") and hasattr(cal.estimator.xgb, "feature_importances_")
        ]
        if importances_list:
            avg_importances = np.mean(importances_list, axis=0)
            rows = [(name, float(val)) for name, val in zip(FEATURE_NAMES, avg_importances)]
            return sorted(rows, key=lambda row: row[1], reverse=True)
    return [(name, 0.0) for name in FEATURE_NAMES]


def print_feature_importances(model: Pipeline) -> None:
    print("Synthetic dataset notice: trained on synthetic noisy dispute labels.")
    print("\nCalibrated XGBoost Feature Importances (averaged across 5 calibration folds):")
    print(f"{'Feature Name':<38} {'Gini Importance':>16}")
    print("-" * 56)
    for feature_name, importance in feature_importances(model):
        print(f"{feature_name:<38} {importance:>16.4f}")


def predict_win_probability(model: Pipeline, record: dict) -> float:
    """Predict calibrated win probability for a dispute record."""
    try:
        from .features import record_to_features
    except ImportError:
        from features import record_to_features

    features_vector = record_to_features(record)
    probabilities = model.predict_proba([features_vector])[0]

    if hasattr(model, "named_steps") and "classifier" in model.named_steps:
        classes = list(model.named_steps["classifier"].classes_)
    elif hasattr(model, "classes_"):
        classes = list(model.classes_)
    else:
        classes = LABEL_ORDER

    won_index = classes.index("won") if "won" in classes else 0
    return float(probabilities[won_index])


# ─── Main CLI entrypoint ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Train Calibrated XGBoost dispute win probability scorer.")
    parser.add_argument("--train", type=Path, default=DEFAULT_TRAIN_PATH, help="Path to training CSV")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Output path for model.pkl bundle")
    parser.add_argument("--method", type=str, default="sigmoid", choices=["sigmoid", "isotonic"], help="Calibration method")
    args = parser.parse_args()

    model = train_model(train_path=args.train, calibration_method=args.method)
    joblib.dump(
        {
            "model": model,
            "feature_names": FEATURE_NAMES,
            "label_order": LABEL_ORDER,
            "synthetic_data_notice": "Trained on synthetic noisy dispute labels — Calibrated XGBoost Classifier.",
        },
        args.model,
    )
    print(f"Saved calibrated model bundle to {args.model.resolve()}")
    print_feature_importances(model)


if __name__ == "__main__":
    main()

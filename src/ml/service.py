#!/usr/bin/env python3
"""
Chargeback Sentinel - Dispute Win Probability Microservice
------------------------------------------------------------
FastAPI microservice exposing the trained scikit-learn Logistic Regression model
for real-time win probability inference (DisputeWinProbabilityAgent).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import joblib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Ensure src/ml directory is in sys.path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from features import record_to_features
except ImportError:
    from src.ml.features import record_to_features

app = FastAPI(
    title="Chargeback Sentinel - ML Agent API",
    description="Microservice providing real-time win probability inference for dispute risk scoring.",
    version="1.0.0",
)

MODEL_PATH = Path("model.pkl")

# Load model bundle once at startup
_bundle: Dict[str, Any] = {}


@app.on_event("startup")
def load_model() -> None:
    global _bundle
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"Model artifact {MODEL_PATH.resolve()} not found. Run 'npm run ml:train' first."
        )
    _bundle = joblib.load(MODEL_PATH)


class DisputeFeatures(BaseModel):
    txn_amount: float = Field(..., description="Transaction monetary amount")
    previous_txns_from_device: float = Field(0.0, description="Previous order count from device")
    customer_txn_history_count: float = Field(0.0, description="Customer order history count")
    customer_disputed_before_count: float = Field(0.0, description="Number of prior disputes filed")
    device_id_match: bool = Field(False, description="Device fingerprint match status")
    cvv_match: bool = Field(False, description="CVV match status")
    avs_match: bool = Field(False, description="AVS match status")
    is_first_time_customer: bool = Field(False, description="First time customer flag")
    delivery_address_match_billing: bool = Field(False, description="Delivery matches billing address")
    three_ds_authenticated: bool = Field(False, description="3DS 2.0 authentication status")
    refund_issued: bool = Field(False, description="Refund initiated flag")
    ip_country_matches_billing_country: bool = Field(False, description="IP country matches billing country")
    completeness_score: float = Field(0.0, description="Evidence completeness score [0.0 - 1.0]")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "DisputeWinProbabilityAgent",
        "modelLoaded": "model" in _bundle,
    }


@app.post("/score")
def score(features: DisputeFeatures) -> Dict[str, Any]:
    if "model" not in _bundle:
        raise HTTPException(status_code=500, detail="ML model bundle not loaded.")

    record = features.model_dump()
    model = _bundle["model"]

    feature_vector = record_to_features(record)
    probabilities = model.predict_proba([feature_vector])[0]

    classes = list(model.named_steps["classifier"].classes_)
    if "won" not in classes:
        raise HTTPException(status_code=500, detail="Invalid model classes configuration.")

    win_index = classes.index("won")
    win_probability = float(probabilities[win_index])

    return {
        "winProbability": round(win_probability, 4),
        "agent": "DisputeWinProbabilityAgent",
        "modelType": "LogisticRegression (scikit-learn)",
        "dataNotice": _bundle.get("synthetic_data_notice", "Trained on synthetic data."),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

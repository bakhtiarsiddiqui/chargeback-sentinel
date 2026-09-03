#!/usr/bin/env python3
"""
Chargeback Sentinel - Dispute Win Probability Microservice
------------------------------------------------------------
FastAPI microservice exposing the trained scikit-learn Logistic Regression model
for real-time win probability inference (DisputeWinProbabilityAgent).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import joblib
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Ensure src/ml directory is in sys.path for imports
ml_dir = Path(__file__).parent
if str(ml_dir) not in sys.path:
    sys.path.insert(0, str(ml_dir))

from features import record_to_features
try:
    from .score_dispute import StringLabelXGBClassifier  # noqa: F401
except ImportError:
    from score_dispute import StringLabelXGBClassifier  # noqa: F401

main_mod = sys.modules.get("__main__")
if main_mod:
    setattr(main_mod, "StringLabelXGBClassifier", StringLabelXGBClassifier)
from evaluation_schema import EvaluationValidationError, build_evaluation

MODEL_PATH = Path("model.pkl")

# Load model bundle once at startup
_bundle: Dict[str, Any] = {}


def load_model() -> None:
    global _bundle
    if not MODEL_PATH.exists():
        _bundle = {}
        return
    _bundle = joblib.load(MODEL_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Chargeback Sentinel - ML Agent API",
    description="Microservice providing real-time win probability inference for dispute risk scoring.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    cardholder_ip_country: str = Field("IN", description="Cardholder IP country")
    billing_country: str = Field("IN", description="Billing country")
    ip_country_matches_billing_country: bool | None = Field(None, description="Optional precomputed geo match")
    completeness_score: float | None = Field(None, description="Optional; recomputed from authentication signals")


@app.get("/health")
def health() -> Dict[str, Any]:
    model_loaded = "model" in _bundle
    return {
        "status": "ok" if model_loaded else "model_not_loaded",
        "service": "DisputeWinProbabilityAgent",
        "modelLoaded": model_loaded,
        "modelPath": str(MODEL_PATH.resolve()),
    }


@app.post("/score")
def score(features: DisputeFeatures) -> Dict[str, Any]:
    if "model" not in _bundle:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded — run `npm run ml:train` first, then restart this service.",
        )

    record = features.model_dump()
    model = _bundle["model"]

    feature_vector = record_to_features(record)
    probabilities = model.predict_proba([feature_vector])[0]

    if hasattr(model, "named_steps") and "classifier" in model.named_steps:
        classes = list(model.named_steps["classifier"].classes_)
    elif hasattr(model, "classes_"):
        classes = list(model.classes_)
    else:
        classes = ["lost", "not_contested", "won"]

    if "won" not in classes:
        raise HTTPException(status_code=500, detail="Invalid model classes configuration.")

    win_index = classes.index("won")
    win_probability = float(probabilities[win_index])

    classifier = model.named_steps["classifier"] if hasattr(model, "named_steps") else model
    model_name = type(classifier).__name__

    return {
        "winProbability": round(win_probability, 4),
        "agent": "DisputeWinProbabilityAgent",
        "modelType": f"Calibrated XGBoost ({model_name})" if "Calibrated" in model_name or "XGB" in model_name else "LogisticRegression (scikit-learn)",
        "dataNotice": _bundle.get("synthetic_data_notice", "Trained on synthetic data."),
    }


@app.get("/api/model/evaluation")
def get_model_evaluation() -> JSONResponse:
    """
    Return the versioned ML evaluation payload (schema 1.0).

    Schema versioning policy (MAJOR.MINOR):
      MAJOR bump — breaking: field removal, rename, type change, semantic change.
      MINOR bump — additive: new optional fields/sections; 1.0 consumers ignore them.

    Required sections: status, dataset, model, summary, perClassMetrics,
                       confusionMatrix, errorAnalysis, governance.
    Optional sections carry an explicit `available: true/false` flag.
    """
    try:
        payload = build_evaluation()
        return JSONResponse(content=payload)
    except EvaluationValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "schemaVersion": "1.0",
                "error": "evaluation_validation_failed",
                "detail": str(exc),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=500,
            content={
                "schemaVersion": "1.0",
                "evaluation": {
                    "status": "error",
                    "reason": f"Internal evaluation error: {type(exc).__name__}: {exc}",
                },
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

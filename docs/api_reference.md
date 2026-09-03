# API Reference

The Chargeback Sentinel API runs by default on `http://127.0.0.1:3000`.  
The Python ML microservice runs on `http://127.0.0.1:8000`.

## Node.js Express Endpoints

### 1. `GET /health`
Returns system status and timestamp.
```json
{
  "status": "ok",
  "service": "chargeback-sentinel-api",
  "version": "1.0.0",
  "date": "2026-08-31T15:00:00.000Z"
}
```

### 2. `GET /api/disputes`
Returns priority disputes queued for analyst review with real-time scoring.

### 3. `GET /api/metrics`
Returns global performance metrics (Precision, Recall, F1 score, False Positive cost, Expected Value recovered).

### 4. `GET /api/disputes/:id`
Returns a single dispute with verification, scoring, draft response, and audit trail.

### 5. `POST /api/case/process`
Runs the full multi-agent orchestration pipeline for a dispute.

**Request Body** (dispute fields + optional `mode`):
```json
{
  "id": "FD-00001",
  "amount": 4500,
  "disputeType": "fraudulent_transaction",
  "threeDsAuthenticated": true,
  "ipCountryMatch": true,
  "deviceFingerprintMatch": true,
  "mode": "assistive"
}
```

**Response**:
```json
{
  "caseId": "FD-00001",
  "mode": "assistive",
  "requiresHumanApproval": false,
  "transactionRisk": {
    "agent": "TransactionRiskAgent",
    "riskScore": 0.15,
    "decision": "allow",
    "flags": []
  },
  "evidence": { "sufficient": true, "completenessScore": 0.95, "missingItems": [] },
  "mlScoring": {
    "winProbability": 0.82,
    "agent": "DisputeWinProbabilityAgent",
    "modelType": "LogisticRegression (scikit-learn)"
  },
  "heuristicScoring": { "winProbability": 0.78, "decision": "contest" },
  "draft": { "draftText": "...", "citations": [], "submissionChecklist": [] },
  "auditTrail": [
    {
      "agent": "TransactionRiskAgent",
      "status": "success",
      "summary": "Assessed pre-txn risk score 0.15 (allow).",
      "timestamp": "2026-08-31T15:00:00.000Z"
    }
  ]
}
```

### 6. `POST /score-dispute`
Scores a single dispute record using the JS heuristic engine.

### 7. `POST /verify-evidence`
Returns missing evidence items, risk flags, and evidence completeness score.

### 8. `POST /draft-response`
Generates a merchant defense narrative and submission checklist.

---

## Python FastAPI ML Microservice Endpoints

Start with `npm run start:ml` or `make start-ml`.

### 1. `GET /health`
```json
{
  "status": "ok",
  "service": "DisputeWinProbabilityAgent",
  "modelLoaded": true
}
```

### 2. `POST /score`
Accepts snake_case `DisputeFeatures` and returns win probability from the trained scikit-learn model.

**Request Body**:
```json
{
  "txn_amount": 4500.0,
  "previous_txns_from_device": 2.0,
  "customer_txn_history_count": 3.0,
  "customer_disputed_before_count": 0.0,
  "device_id_match": true,
  "cvv_match": true,
  "avs_match": true,
  "is_first_time_customer": false,
  "delivery_address_match_billing": true,
  "three_ds_authenticated": true,
  "refund_issued": false,
  "ip_country_matches_billing_country": true,
  "completeness_score": 0.95
}
```

**Response**:
```json
{
  "winProbability": 0.8234,
  "agent": "DisputeWinProbabilityAgent",
  "modelType": "LogisticRegression (scikit-learn)",
  "dataNotice": "Trained on synthetic data."
}
```

**Graceful Fallback**: If the ML microservice is offline, `OrchestratorAgent` catches the connection error and falls back to the JS heuristic scorer, logging a warning in the audit trail.

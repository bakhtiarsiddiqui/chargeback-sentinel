# API Reference

The Chargeback Sentinel API runs by default on `http://127.0.0.1:3000`.

## Endpoints

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

### 4. `POST /score-dispute`
Scores a single dispute record.
**Request Body**:
```json
{
  "id": "FD-00001",
  "amount": 4500,
  "disputeType": "fraudulent_transaction",
  "deliveryProof": true,
  "ipCountryMatch": true,
  "three_ds_authenticated": true
}
```

### 5. `POST /verify-evidence`
Returns missing evidence items, risk flags, and evidence completeness score.

### 6. `POST /draft-response`
Generates a merchant defense narrative and submission checklist.

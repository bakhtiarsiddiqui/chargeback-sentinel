# AI Chargeback Risk Manager

This repo now contains two parallel proof-of-concept tracks:

- a lightweight JavaScript demo app from the earlier prototype
- a standalone Python data/ML foundation for **fraudulent-transaction chargeback disputes**

The Python foundation is synthetic by design. It does **not** use real chargeback outcome data. Labels are rule-derived with injected noise for hackathon experimentation.

## Python Data Generator

Run the generator:

```bash
python3 generate_data.py
```

It writes:

- `data/ml/train.csv`
- `data/ml/val.csv`
- `data/ml/test.csv`

Dataset properties:

- 1200 synthetic records
- label space: `won`, `lost`, `not_contested`
- 24 tagged edge cases via `is_edge_case`
- stratified 70/15/15 split by both `label` and `is_edge_case`

Run tests:

```bash
python3 -m unittest tests/test_generate_data.py
python3 -m unittest tests/test_verify_evidence.py
```

Evidence verification:

- `verify_evidence.py` implements the deterministic `verify_evidence(record: dict) -> dict` function
- output keys: `completeness_score`, `missing_items`, `present_items`

## Python ML Scorer

Create a local environment and install the ML dependency:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Train the logistic-regression scorer:

```bash
.venv/bin/python score_dispute.py
```

This writes `model.pkl` and prints coefficients sorted by magnitude so they can later become reason-code candidates.

Evaluate on the held-out test split:

```bash
.venv/bin/python evaluate.py
```

The evaluator reports weighted precision, recall, F1, a confusion matrix, false-positive count, and wasted contest cost. It separately reports the `is_edge_case` subset and warns when synthetic results look suspiciously perfect.

## JavaScript Prototype

The older demo app can still be run with:

```bash
npm install
npm start
```

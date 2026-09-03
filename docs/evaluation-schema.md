# Model Evaluation Schema Specification & Versioning Policy

**Endpoint:** `GET /api/model/evaluation`  
**Current Version:** `1.0`  
**Semantic Versioning Scheme:** `MAJOR.MINOR` (e.g. `1.0`, `1.1`, `2.0`)

---

## 1. Overview & Architectural Pipeline

The ML evaluation pipeline operates according to a strict, single-source-of-truth hierarchy:

```text
src/ml/evaluate.py (or evaluation_schema.py)
        ↓
Authoritative ML Evaluation Calculation
        ↓
Evaluation Schema v1.0
        ↓
GET /api/model/evaluation
        ↓
Validated API Response (Proxy via Node API :3000 or FastAPI :8000)
        ↓
Risk & Model Performance Dashboard UI
```

The frontend performs **formatting and visual layout only**. It does not recalculate precision, recall, F1 scores, confusion matrix cells, or ROC-AUC metrics independently.

---

## 2. Versioning Policy

The evaluation contract uses **`MAJOR.MINOR`** semantic versioning (e.g., `"1.0"`).

### MAJOR Version Bumps (`1.0` → `2.0`)
Incremented only for **breaking changes**, including:
- Removing a required field.
- Renaming an existing required field.
- Changing the data type of an existing field.
- Changing the semantic meaning of an existing field (e.g., reinterpreting `winProbability`).
- Altering response structure in a way that breaks existing consumers.

**Compatibility behavior:** A frontend supporting version `1.x` will **refuse to parse** a major version `2.0` response and will display a non-blocking compatibility warning:
> *"Evaluation data unavailable — Dashboard supports schema 1.x, but API returned 2.0."*

### MINOR Version Bumps (`1.0` → `1.1`)
Incremented for **backward-compatible additive changes**, such as:
- Adding a new optional evaluation section.
- Adding new optional metadata or visualization fields.
- Introducing new optional metrics.

**Compatibility behavior:** A frontend supporting `1.0` will safely render all known fields from a `1.1` response and **ignore unknown fields**, continuing full operations without crashing.

---

## 3. Schema Structure & Specification (v1.0)

Every response from `GET /api/model/evaluation` follows this structure:

```json
{
  "schemaVersion": "1.0",
  "evaluation": {
    "status": "success",
    "dataset": {
      "path": "data/ml/test.csv",
      "totalSamples": 7500,
      "edgeCaseSamples": 6,
      "classDistribution": { "lost": 4125, "not_contested": 1125, "won": 2250 }
    },
    "model": {
      "type": "LogisticRegression (scikit-learn)",
      "pipeline": "StandardScaler → balanced LogisticRegression",
      "featureNames": [ "txn_amount", "..." ],
      "labelOrder": [ "lost", "not_contested", "won" ],
      "classes": [ "lost", "not_contested", "won" ]
    },
    "summary": {
      "accuracy": 0.8875,
      "precision": 0.8881,
      "recall": 0.8875,
      "f1": 0.8878,
      "f1Average": "weighted",
      "correctPredictions": 6656,
      "incorrectPredictions": 844,
      "totalSamples": 7500
    },
    "perClassMetrics": [
      { "label": "lost", "precision": 0.9028, "recall": 0.8914, "f1": 0.8970, "support": 4125 },
      { "label": "not_contested", "precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 1125 },
      { "label": "won", "precision": 0.8054, "recall": 0.8240, "f1": 0.8146, "support": 2250 }
    ],
    "confusionMatrix": {
      "labels": [ "lost", "not_contested", "won" ],
      "matrix": [
        [3677, 0, 448],
        [0, 1125, 0],
        [396, 0, 1854]
      ]
    },
    "errorAnalysis": {
      "falsePositives": {
        "description": "Cases predicted 'won' but actual outcome was 'lost'",
        "count": 448,
        "avgTransactionAmountINR": 8088.91,
        "contestCostPerCaseINR": 150.0,
        "totalWastedContestCostINR": 67200.0
      },
      "edgeCaseSubset": {
        "count": 6,
        "precision": 0.8333,
        "recall": 0.8333,
        "f1": 0.8333
      }
    },
    "probabilityAnalysis": {
      "available": true,
      "targetClass": "won",
      "targetClassNote": "winProbability represents P(class='won') from the Logistic Regression model.",
      "minWinProb": 0.0,
      "maxWinProb": 0.901,
      "scoreBands": { "lt40": 4936, "40to60": 262, "60to80": 603, "gte80": 1699 }
    },
    "roc": {
      "available": false,
      "reason": "Multi-class ROC-AUC curve not computed in this evaluation setup.",
      "auc": null,
      "curve": []
    },
    "precisionRecall": {
      "available": false,
      "reason": "Multi-class PR curve not computed in this evaluation setup.",
      "auc": null,
      "curve": []
    },
    "calibration": {
      "available": false,
      "reason": "Calibration curve not computed in this evaluation setup.",
      "curve": []
    },
    "governance": {
      "datasetNotice": "Trained on synthetic noisy labels — not real chargeback outcomes.",
      "warnings": [ "Trained on synthetic noisy labels — not real chargeback outcomes." ],
      "evaluationVersion": "1.0"
    }
  }
}
```

---

## 4. Required vs. Optional Sections

### Required Sections (`1.0`)
Must always be present in any successful (`status: "success"`) evaluation payload:
1. `schemaVersion`
2. `evaluation.status`
3. `evaluation.dataset`
4. `evaluation.model`
5. `evaluation.summary`
6. `evaluation.perClassMetrics`
7. `evaluation.confusionMatrix`
8. `evaluation.errorAnalysis`
9. `evaluation.governance`

### Optional / Conditional Capabilities
May or may not be computable depending on model architecture or evaluation setup:
- `evaluation.probabilityAnalysis`
- `evaluation.roc`
- `evaluation.precisionRecall`
- `evaluation.calibration`

**Rule:** Every optional capability section MUST carry an explicit `"available": true` or `"available": false` boolean flag.

---

## 5. Explicit Unavailable Metric Behavior

- **No Fabricated Zeroes:** When a metric (e.g. `auc`) cannot be computed, `auc` MUST be `null`, NOT `0.0`.
- **Explicit Availability Flag:** The presence of `"available": false` signals unavailability. An `auc` value of `0.0` is a valid mathematical result (e.g., worst-case predictor) and MUST NOT be used to represent unavailability.
- **Empty Arrays:** `curve: []` alone does not signal unavailability; `"available": false` is authoritative.

---

## 6. Field Semantics & Immutability

1. **`summary.f1`**: Represents the weighted average F1 score across all classes. The averaging scheme is explicitly declared in `summary.f1Average` (`"weighted"`). Silent reinterpretation to macro or micro F1 without a schema version bump is strictly prohibited.
2. **`winProbability`**: Represents the model's posterior probability estimate $P(\text{class} = \text{"won"} \mid x)$. It MUST NOT be reinterpreted as generic model confidence or risk score.
3. **`confusionMatrix.matrix`**: Rows represent actual ground-truth classes; columns represent model-predicted classes. Matrix ordering corresponds to `confusionMatrix.labels`.

---

## 7. Response Validation Rules

Before serving `GET /api/model/evaluation`, the backend enforces the following mathematical consistency rules:

1. `correctPredictions + incorrectPredictions == totalSamples`
2. `sum(confusionMatrix cells) == totalSamples`
3. `sum(perClassMetrics[*].support) == totalSamples`
4. `confusionMatrix.matrix.length == confusionMatrix.labels.length`
5. `confusionMatrix.matrix[i].length == confusionMatrix.labels.length` (for all $i$)

If any rule is violated, the backend aborts response delivery and returns HTTP `422 Unprocessable Entity` with `error: "evaluation_validation_failed"`.

---

## 8. Backward Compatibility with `/api/metrics`

The legacy endpoint `GET /api/metrics` remains **completely untouched and 100% backward compatible**. It returns simple baseline metrics for existing lightweight consumers:

```json
{
  "metrics": {
    "precision": 1.0,
    "recall": 1.0,
    "f1": 1.0,
    "evidenceAccuracy": 0.67,
    "falsePositiveCost": 0,
    "expectedValueRecovered": 17447.9,
    "avgAnalystTimeSaved": 19.67,
    "totalDisputes": 3
  },
  "baseline": {
    "strategy": "contest_all",
    "falsePositiveCost": 374
  }
}
```

---

## 9. Changelog

### `1.0` (Initial Release)
- Initial versioned evaluation schema release.
- Added explicit `schemaVersion: "1.0"` header.
- Established required vs. optional section definitions with `available` boolean flags.
- Defined backend validation rules for confusion matrix dimensions and sample counts.
- Added proxy support in Node API (`/api/model/evaluation`) with graceful fallback when ML service is offline.

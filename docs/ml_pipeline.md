# ML Scorer & Feature Pipeline

## Feature Engineering

The feature vector consists of 13 primary signals extracted by `src/ml/features.py`:

| Feature | Type | Description |
| :--- | :--- | :--- |
| `txn_amount` | Float | Transaction monetary value |
| `previous_txns_from_device` | Float | Historical device order count |
| `customer_txn_history_count` | Float | Total merchant transactions for cardholder |
| `customer_disputed_before_count` | Float | Number of prior disputes initiated |
| `device_id_match` | Boolean (0/1) | Device ID fingerprint verification |
| `cvv_match` | Boolean (0/1) | CVV verification status |
| `avs_match` | Boolean (0/1) | Address Verification System match |
| `is_first_time_customer` | Boolean (0/1) | New customer indicator |
| `delivery_address_match_billing` | Boolean (0/1) | Shipping vs billing address match |
| `three_ds_authenticated` | Boolean (0/1) | 3D-Secure 2.0 protocol status |
| `refund_issued` | Boolean (0/1) | Prior refund status |
| `ip_country_matches_billing_country` | Boolean (0/1) | IP geo-location match |
| `completeness_score` | Float | Deterministic evidence score |

## Model Architecture

- **Classifier**: Balanced Logistic Regression (`sklearn.linear_model.LogisticRegression`)
- **Preprocessing**: Standard Scaling (`StandardScaler`)
- **Target Labels**: `won`, `lost`, `not_contested`
- **Output Artifact**: `model.pkl` (serialized joblib pipeline bundle)

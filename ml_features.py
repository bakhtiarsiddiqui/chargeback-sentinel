#!/usr/bin/env python3
"""
Shared feature preparation for the synthetic chargeback scorer.

The dataset is synthetic, rule-derived, and intentionally noisy. These helpers
keep model training and evaluation aligned without implying real-world chargeback
outcome validity.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from verify_evidence import verify_evidence


BOOL_FIELDS = [
    "device_id_match",
    "cvv_match",
    "avs_match",
    "is_first_time_customer",
    "delivery_address_match_billing",
    "three_ds_authenticated",
    "refund_issued",
]
NUMERIC_FIELDS = [
    "txn_amount",
    "previous_txns_from_device",
    "customer_txn_history_count",
    "customer_disputed_before_count",
]
FEATURE_NAMES = [
    *NUMERIC_FIELDS,
    *BOOL_FIELDS,
    "ip_country_matches_billing_country",
    "completeness_score",
]
LABEL_ORDER = ["lost", "not_contested", "won"]


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def load_csv(path: Path | str) -> List[Dict[str, object]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def coerce_record(record: Dict[str, object]) -> Dict[str, object]:
    coerced = dict(record)
    for field in BOOL_FIELDS + ["is_edge_case"]:
        coerced[field] = parse_bool(coerced.get(field, False))
    for field in NUMERIC_FIELDS:
        coerced[field] = float(coerced.get(field, 0) or 0)
    return coerced


def record_to_features(record: Dict[str, object]) -> List[float]:
    coerced = coerce_record(record)
    verification = verify_evidence(coerced)

    values = [float(coerced[field]) for field in NUMERIC_FIELDS]
    values.extend(1.0 if coerced[field] else 0.0 for field in BOOL_FIELDS)
    values.append(
        1.0
        if coerced.get("cardholder_ip_country") == coerced.get("billing_country")
        else 0.0
    )
    values.append(float(verification["completeness_score"]))
    return values


def matrix_and_labels(records: Sequence[Dict[str, object]]) -> Tuple[List[List[float]], List[str]]:
    return [record_to_features(record) for record in records], [str(record["label"]) for record in records]


def edge_case_mask(records: Iterable[Dict[str, object]]) -> List[bool]:
    return [parse_bool(record.get("is_edge_case", False)) for record in records]


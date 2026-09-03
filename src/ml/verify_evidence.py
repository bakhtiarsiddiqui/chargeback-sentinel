#!/usr/bin/env python3
"""
Chargeback Sentinel - Deterministic Evidence Verifier
------------------------------------------------------
Validates dispute evidence completeness based on risk signals and 3DS authentication protocols.
"""

from __future__ import annotations
from typing import Callable, Dict, List, Tuple

Rule = Tuple[str, Callable[[dict], bool]]

EVIDENCE_RULES: List[Rule] = [
    ("3DS authentication proof", lambda record: bool(record.get("three_ds_authenticated"))),
    ("AVS/CVV match", lambda record: bool(record.get("avs_match")) and bool(record.get("cvv_match"))),
    ("Device history", lambda record: int(record.get("previous_txns_from_device", 0)) >= 1),
    (
        "Geo-consistency",
        lambda record: record.get("cardholder_ip_country") == record.get("billing_country"),
    ),
    ("Customer history", lambda record: int(record.get("customer_txn_history_count", 0)) >= 1),
]


def verify_authentication_signals(record: dict) -> dict:
    """Checks authentication/fraud signal completeness used as an ML input feature."""
    present_items: List[str] = []
    missing_items: List[str] = []

    for label, predicate in EVIDENCE_RULES:
        if predicate(record):
            present_items.append(label)
        else:
            missing_items.append(label)

    completeness_score = len(present_items) / len(EVIDENCE_RULES)
    return {
        "completeness_score": completeness_score,
        "missing_items": missing_items,
        "present_items": present_items,
    }


verify_evidence = verify_authentication_signals

#!/usr/bin/env python3
"""
Chargeback Sentinel - Synthetic Data Generator
----------------------------------------------
Generates stratified synthetic dataset for chargeback dispute outcome prediction with injected noise and edge cases.
"""

from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

TOTAL_RECORDS = 1200
DEFAULT_SEED = 20260829
EDGE_CASE_COUNT = 24
OUTPUT_DIR = Path("data/ml")
LABELS = ("won", "lost", "not_contested")
FIELDNAMES = [
    "dispute_id",
    "txn_amount",
    "txn_currency",
    "txn_timestamp",
    "dispute_filed_date",
    "cardholder_ip_country",
    "billing_country",
    "device_id_match",
    "previous_txns_from_device",
    "cvv_match",
    "avs_match",
    "customer_txn_history_count",
    "is_first_time_customer",
    "delivery_address_match_billing",
    "customer_disputed_before_count",
    "three_ds_authenticated",
    "refund_issued",
    "is_edge_case",
    "label",
]
COUNTRIES = ("IN", "AE", "SG", "US", "GB")


@dataclass(frozen=True)
class LabelTargets:
    won: int
    lost: int
    not_contested: int


def bool_to_csv(value: bool) -> str:
    return "true" if value else "false"


def random_bool(rng: random.Random, probability_true: float) -> bool:
    return rng.random() < probability_true


def format_timestamp(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def weighted_country(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.78:
        return "IN"
    if roll < 0.85:
        return "AE"
    if roll < 0.91:
        return "SG"
    if roll < 0.96:
        return "US"
    return "GB"


def synthetic_label(record: Dict[str, object], rng: random.Random) -> str:
    if record["refund_issued"]:
        return "not_contested"

    if record["three_ds_authenticated"] and record["avs_match"] and record["cvv_match"]:
        return "won" if rng.random() < 0.88 else "lost"

    if (
        not record["device_id_match"]
        and record["cardholder_ip_country"] != record["billing_country"]
        and record["is_first_time_customer"]
    ):
        return "lost" if rng.random() < 0.85 else "won"

    if record["customer_disputed_before_count"] >= 3:
        return "lost" if rng.random() < 0.70 else "won"

    if record["is_first_time_customer"]:
        return "lost" if rng.random() < 0.62 else "won"

    return "won" if rng.random() < 0.50 else "lost"


def generate_base_record(index: int, rng: random.Random) -> Dict[str, object]:
    txn_time = datetime(2026, 1, 1, 0, 0, 0) + timedelta(
        days=rng.randint(0, 210),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
        seconds=rng.randint(0, 59),
    )
    billing_country = weighted_country(rng)
    is_first_time_customer = random_bool(rng, 0.28)
    customer_txn_history_count = 0 if is_first_time_customer else rng.randint(1, 20)
    previous_txns_from_device = min(
        10,
        max(0, int(customer_txn_history_count * rng.uniform(0.25, 0.7)) + rng.randint(-1, 2)),
    )
    device_id_match = random_bool(rng, 0.74)
    cvv_match = random_bool(rng, 0.81)
    avs_match = random_bool(rng, 0.76)
    three_ds_authenticated = random_bool(rng, 0.58)
    refund_issued = random_bool(rng, 0.10)
    cardholder_ip_country = billing_country if random_bool(rng, 0.80) else rng.choice(
        [country for country in COUNTRIES if country != billing_country]
    )

    return {
        "dispute_id": f"FD-{index:05d}",
        "txn_amount": rng.randint(500, 15000),
        "txn_currency": "INR",
        "txn_timestamp": format_timestamp(txn_time),
        "dispute_filed_date": (txn_time + timedelta(days=rng.randint(3, 45))).date().isoformat(),
        "cardholder_ip_country": cardholder_ip_country,
        "billing_country": billing_country,
        "device_id_match": device_id_match,
        "previous_txns_from_device": previous_txns_from_device,
        "cvv_match": cvv_match,
        "avs_match": avs_match,
        "customer_txn_history_count": customer_txn_history_count,
        "is_first_time_customer": is_first_time_customer,
        "delivery_address_match_billing": random_bool(rng, 0.72),
        "customer_disputed_before_count": rng.randint(0, 5),
        "three_ds_authenticated": three_ds_authenticated,
        "refund_issued": refund_issued,
        "is_edge_case": False,
    }


def edge_case_templates() -> List[Dict[str, object]]:
    base_time = datetime(2026, 7, 1, 10, 0, 0)
    templates: List[Dict[str, object]] = []

    def add_template(offset: int, **overrides: object) -> None:
        txn_time = base_time + timedelta(days=offset)
        record = {
            "txn_amount": 5000 + offset * 175,
            "txn_currency": "INR",
            "txn_timestamp": format_timestamp(txn_time),
            "dispute_filed_date": (txn_time + timedelta(days=12)).date().isoformat(),
            "cardholder_ip_country": "IN",
            "billing_country": "IN",
            "device_id_match": True,
            "previous_txns_from_device": 3,
            "cvv_match": True,
            "avs_match": True,
            "customer_txn_history_count": 5,
            "is_first_time_customer": False,
            "delivery_address_match_billing": True,
            "customer_disputed_before_count": 0,
            "three_ds_authenticated": True,
            "refund_issued": False,
            "is_edge_case": True,
        }
        record.update(overrides)
        templates.append(record)

    add_template(0, cvv_match=True, avs_match=False, three_ds_authenticated=True)
    add_template(1, cvv_match=False, avs_match=True, three_ds_authenticated=True)
    add_template(2, cvv_match=False, avs_match=True, device_id_match=False, cardholder_ip_country="SG")
    add_template(3, cvv_match=True, avs_match=False, device_id_match=False, cardholder_ip_country="AE")
    add_template(4, cvv_match=False, avs_match=False, three_ds_authenticated=True, txn_amount=14850)
    add_template(5, cvv_match=True, avs_match=False, customer_disputed_before_count=4)

    add_template(6, customer_disputed_before_count=5, three_ds_authenticated=True, avs_match=True, cvv_match=True)
    add_template(7, customer_disputed_before_count=4, previous_txns_from_device=8, customer_txn_history_count=12)
    add_template(8, customer_disputed_before_count=3, txn_amount=11200, three_ds_authenticated=True)
    add_template(9, customer_disputed_before_count=5, delivery_address_match_billing=False)
    add_template(10, customer_disputed_before_count=4, refund_issued=True)
    add_template(11, customer_disputed_before_count=3, device_id_match=False, cardholder_ip_country="US")

    add_template(12, txn_amount=14999, three_ds_authenticated=False, avs_match=True, cvv_match=True)
    add_template(13, txn_amount=14350, three_ds_authenticated=False, device_id_match=False, previous_txns_from_device=0)
    add_template(14, txn_amount=13800, cardholder_ip_country="GB", billing_country="IN")
    add_template(15, txn_amount=14500, delivery_address_match_billing=False, device_id_match=True)
    add_template(16, txn_amount=13250, is_first_time_customer=True, customer_txn_history_count=0)
    add_template(17, txn_amount=14075, previous_txns_from_device=10, three_ds_authenticated=False)

    add_template(18, three_ds_authenticated=False, avs_match=True, cvv_match=True, txn_amount=9800)
    add_template(19, three_ds_authenticated=False, avs_match=False, cvv_match=True, device_id_match=True)
    add_template(20, three_ds_authenticated=False, avs_match=True, cvv_match=False, device_id_match=False)
    add_template(21, three_ds_authenticated=False, avs_match=False, cvv_match=False, is_first_time_customer=True)
    add_template(22, three_ds_authenticated=False, refund_issued=True, txn_amount=8900)
    add_template(23, three_ds_authenticated=False, cardholder_ip_country="AE", billing_country="IN", is_first_time_customer=True, device_id_match=False)

    return templates


def enforce_targets(records: List[Dict[str, object]], rng: random.Random) -> None:
    targets = LabelTargets(
        won=round(len(records) * 0.30),
        lost=round(len(records) * 0.55),
        not_contested=len(records) - round(len(records) * 0.30) - round(len(records) * 0.55),
    )
    current = Counter(record["label"] for record in records)

    def relabel(candidates: Iterable[Dict[str, object]], new_label: str, limit: int) -> int:
        changed = 0
        pool = list(candidates)
        rng.shuffle(pool)
        for record in pool:
            if changed >= limit:
                break
            old_label = record["label"]
            if old_label == new_label:
                continue
            record["label"] = new_label
            current[old_label] -= 1
            current[new_label] += 1
            changed += 1
        return changed

    if current["not_contested"] < targets.not_contested:
        needed = targets.not_contested - current["not_contested"]
        relabel(
            (
                record
                for record in records
                if not record["refund_issued"] and not record["is_edge_case"] and record["txn_amount"] < 5000
            ),
            "not_contested",
            needed,
        )
        for record in records:
            if record["label"] == "not_contested":
                record["refund_issued"] = True

    if current["won"] > targets.won:
        overflow = current["won"] - targets.won
        relabel(
            (
                record
                for record in records
                if record["label"] == "won"
                and not record["refund_issued"]
                and not (
                    record["three_ds_authenticated"] and record["avs_match"] and record["cvv_match"]
                )
            ),
            "lost",
            overflow,
        )

    if current["lost"] > targets.lost:
        overflow = current["lost"] - targets.lost
        relabel(
            (
                record
                for record in records
                if record["label"] == "lost"
                and not record["refund_issued"]
                and record["three_ds_authenticated"]
                and record["avs_match"]
                and record["cvv_match"]
            ),
            "won",
            overflow,
        )


def stratified_split(
    records: Sequence[Dict[str, object]],
    rng: random.Random,
    ratios: Sequence[float] = (0.70, 0.15, 0.15),
) -> Dict[str, List[Dict[str, object]]]:
    buckets: Dict[tuple[str, bool], List[Dict[str, object]]] = defaultdict(list)
    for record in records:
        buckets[(str(record["label"]), bool(record["is_edge_case"]))].append(record)

    splits = {"train": [], "val": [], "test": []}
    for bucket_records in buckets.values():
        bucket_records = list(bucket_records)
        rng.shuffle(bucket_records)
        count = len(bucket_records)
        train_count = round(count * ratios[0])
        val_count = round(count * ratios[1])
        if train_count + val_count > count:
            val_count = max(0, count - train_count)
        test_count = count - train_count - val_count

        splits["train"].extend(bucket_records[:train_count])
        splits["val"].extend(bucket_records[train_count : train_count + val_count])
        splits["test"].extend(bucket_records[train_count + val_count : train_count + val_count + test_count])

    for split_name in splits:
        rng.shuffle(splits[split_name])
    return splits


def normalize_for_csv(record: Dict[str, object]) -> Dict[str, object]:
    normalized = {}
    for field in FIELDNAMES:
        value = record[field]
        if isinstance(value, bool):
            normalized[field] = bool_to_csv(value)
        else:
            normalized[field] = value
    return normalized


def write_csv(path: Path, records: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(normalize_for_csv(record) for record in records)


def generate_dataset(total_records: int = TOTAL_RECORDS, seed: int = DEFAULT_SEED) -> Dict[str, List[Dict[str, object]]]:
    if total_records < EDGE_CASE_COUNT + 10:
        raise ValueError("total_records is too small to support the requested edge cases and splits")

    rng = random.Random(seed)
    records = [generate_base_record(index + 1, rng) for index in range(total_records - EDGE_CASE_COUNT)]

    start_index = len(records) + 1
    for offset, template in enumerate(edge_case_templates()):
        record = {"dispute_id": f"FD-{start_index + offset:05d}"}
        record.update(template)
        records.append(record)

    for record in records:
        record["label"] = synthetic_label(record, rng)

    enforce_targets(records, rng)
    return stratified_split(records, rng)


def dataset_summary(splits: Dict[str, Sequence[Dict[str, object]]]) -> str:
    all_records = [record for split_records in splits.values() for record in split_records]
    label_counts = Counter(record["label"] for record in all_records)
    edge_count = sum(1 for record in all_records if record["is_edge_case"])
    return (
        f"Generated {len(all_records)} synthetic records "
        f"(won={label_counts['won']}, lost={label_counts['lost']}, not_contested={label_counts['not_contested']}), "
        f"including {edge_count} tagged edge cases."
    )


def main() -> None:
    splits = generate_dataset()
    for split_name, records in splits.items():
        write_csv(OUTPUT_DIR / f"{split_name}.csv", records)
    print(dataset_summary(splits))
    print(f"Wrote train/val/test CSV files to {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()

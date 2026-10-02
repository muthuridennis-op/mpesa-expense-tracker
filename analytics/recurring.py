# analytics/recurring.py
"""Detect recurring monthly payments.

Changes vs the first version:
  * internal movements are excluded
  * median gap (robust to one-off outliers) instead of mean gap
  * token_sort_ratio clustering, so "John" no longer merges into "John Kamau"
  * an ``active`` flag, so subscriptions you stopped months ago are not counted
  * returns the matching ``receipts`` so the Forecast can exclude exactly them
"""
import pandas as pd

from analytics.common import cluster_names, ensure_enriched, spending

COLUMNS = [
    "cluster", "category", "sample_payees", "occurrences", "avg_amount",
    "amount_cv", "avg_gap_days", "last_paid", "next_expected", "total_paid",
    "active", "receipts",
]


def find_recurring(
    df: pd.DataFrame,
    min_gap: int = 25,
    max_gap: int = 35,
    amount_tolerance: float = 0.25,
    fuzzy_threshold: int = 88,
    min_occurrences: int = 3,
) -> pd.DataFrame:
    d = spending(df)
    if d.empty:
        return pd.DataFrame(columns=COLUMNS)

    all_df = ensure_enriched(df)
    data_end = all_df["date"].max()

    # group key: cleaned payee, falling back to the first 40 chars of details
    payee = d["payee_clean"].fillna("")
    d["group_key"] = payee.where(payee != "", d["details"].fillna("").str[:40])
    mapping = cluster_names(tuple(sorted(d["group_key"].unique())), fuzzy_threshold)
    d["cluster"] = d["group_key"].map(mapping).fillna(d["group_key"])

    rows = []
    for cluster, group in d.groupby("cluster"):
        if not cluster or len(group) < min_occurrences:
            continue
        group = group.sort_values("date")
        gaps = group["date"].diff().dt.days.dropna()
        if gaps.empty:
            continue
        median_gap = float(gaps.median())
        if not (min_gap <= median_gap <= max_gap):
            continue
        amounts = group["abs_amount"]
        mean = amounts.mean()
        if mean == 0:
            continue
        cv = amounts.std() / mean
        if cv >= amount_tolerance:
            continue

        last_paid = group["date"].max()
        rows.append({
            "cluster": cluster,
            "category": group["category"].mode().iloc[0],
            "sample_payees": " | ".join(group["group_key"].unique()[:3]),
            "occurrences": len(group),
            "avg_amount": float(mean),
            "amount_cv": float(cv),
            "avg_gap_days": median_gap,
            "last_paid": last_paid,
            "next_expected": last_paid + pd.Timedelta(days=int(round(median_gap))),
            "total_paid": float(amounts.sum()),
            "active": bool((data_end - last_paid).days <= median_gap * 1.5),
            "receipts": group["receipt"].tolist(),
        })

    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(rows).sort_values("total_paid", ascending=False).reset_index(drop=True)
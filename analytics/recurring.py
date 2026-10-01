# analytics/recurring.py
"""Detect recurring monthly payments using fuzzy payee matching."""
import pandas as pd
from rapidfuzz import fuzz


def _cluster_payees(payees: list[str], threshold: int = 85) -> dict:
    reps = []
    mapping = {}
    for payee in payees:
        matched = None
        for rep in reps:
            if fuzz.token_set_ratio(payee.lower(), rep.lower()) >= threshold:
                matched = rep
                break
        if matched is None:
            reps.append(payee)
            mapping[payee] = payee
        else:
            mapping[payee] = matched
    return mapping


def find_recurring(
    df: pd.DataFrame,
    min_gap: int = 25,
    max_gap: int = 35,
    amount_tolerance: float = 0.25,
    fuzzy_threshold: int = 85,
) -> pd.DataFrame:
    expenses = df[df["net_amount"] < 0].copy()
    if expenses.empty:
        return pd.DataFrame()

    expenses["abs_amount"] = expenses["net_amount"].abs()
    expenses["group_key"] = expenses.apply(
        lambda r: r.get("payee") if r.get("payee") else r["details"][:40],
        axis=1,
    )

    unique_keys = expenses["group_key"].dropna().unique().tolist()
    mapping = _cluster_payees(unique_keys, threshold=fuzzy_threshold)
    expenses["cluster"] = expenses["group_key"].map(mapping).fillna(expenses["group_key"])

    rows = []
    for cluster, group in expenses.groupby("cluster"):
        if len(group) < 3:
            continue
        group = group.sort_values("date")
        gaps = group["date"].diff().dt.days.dropna()
        if len(gaps) == 0:
            continue
        avg_gap = gaps.mean()
        if not (min_gap <= avg_gap <= max_gap):
            continue
        amounts = group["abs_amount"]
        if amounts.mean() == 0:
            continue
        cv = amounts.std() / amounts.mean()
        if cv < amount_tolerance:
            rows.append({
                "cluster": cluster,
                "sample_payees": " | ".join(group["group_key"].unique()[:3]),
                "occurrences": len(group),
                "avg_amount": amounts.mean(),
                "amount_cv": cv,
                "avg_gap_days": avg_gap,
                "next_expected": group["date"].max() + pd.Timedelta(days=int(avg_gap)),
                "total_paid": amounts.sum(),
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("total_paid", ascending=False).reset_index(drop=True)
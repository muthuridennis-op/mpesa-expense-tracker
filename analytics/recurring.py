# analytics/recurring.py
"""Detect recurring monthly payments."""
import pandas as pd


def find_recurring(df: pd.DataFrame,
                   min_gap: int = 25,
                   max_gap: int = 35,
                   amount_tolerance: float = 0.2) -> pd.DataFrame:
    expenses = df[df["net_amount"] < 0].copy()
    if expenses.empty:
        return pd.DataFrame()

    expenses["abs_amount"] = expenses["net_amount"].abs()
    expenses["key"] = (
        expenses["details"].str.replace(r"\d+", "", regex=True).str.strip().str[:40]
    )

    rows = []
    for key, group in expenses.groupby("key"):
        if len(group) < 2:
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
        if amounts.std() / amounts.mean() < amount_tolerance:
            rows.append({
                "description": key,
                "occurrences": len(group),
                "avg_amount": amounts.mean(),
                "avg_gap_days": avg_gap,
                "next_expected": group["date"].max() + pd.Timedelta(days=int(avg_gap)),
                "total_paid": amounts.sum(),
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("total_paid", ascending=False).reset_index(drop=True)
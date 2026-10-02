# analytics/anomalies.py
"""Detect unusually large expenses within each category using the IQR method.

Internal movements (Fuliza repayments, M-Shwari, ...) are excluded; they are
large by nature and are not spending.
"""
import pandas as pd

from analytics.categories import UNCATEGORISED
from analytics.common import spending


def find_anomalies(df: pd.DataFrame, iqr_multiplier: float = 2.0) -> pd.DataFrame:
    expenses = spending(df)
    if expenses.empty:
        return pd.DataFrame()

    # "Uncategorised" mixes unrelated things, so split it by transaction type.
    expenses["group"] = expenses["category"].where(
        expenses["category"] != UNCATEGORISED,
        UNCATEGORISED + " (" + expenses["type"] + ")",
    )

    rows = []
    for group_name, group in expenses.groupby("group"):
        if len(group) < 4:
            continue
        q1 = group["abs_amount"].quantile(0.25)
        q3 = group["abs_amount"].quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        upper = q3 + iqr_multiplier * iqr
        for _, row in group[group["abs_amount"] > upper].iterrows():
            rows.append({
                "date": row["date"],
                "category": group_name,
                "payee": row.get("payee_clean") or row.get("payee") or "",
                "details": str(row.get("details") or "")[:80],
                "amount": row["abs_amount"],
                "category_q3": q3,
                "category_iqr": iqr,
                "multiple_of_iqr": (row["abs_amount"] - q3) / iqr,
            })

    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values("multiple_of_iqr", ascending=False)
        .reset_index(drop=True)
    )
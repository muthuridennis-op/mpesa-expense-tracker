# analytics/anomalies.py
"""Detect unusually large transactions per category using IQR."""
import pandas as pd


def find_anomalies(df: pd.DataFrame, iqr_multiplier: float = 2.0) -> pd.DataFrame:
    expenses = df[df["net_amount"] < 0].copy()
    if expenses.empty:
        return pd.DataFrame()

    expenses["abs_amount"] = expenses["net_amount"].abs()
    rows = []
    for txn_type, group in expenses.groupby("type"):
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
                "type": txn_type,
                "payee": row.get("payee", ""),
                "details": row["details"][:80],
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
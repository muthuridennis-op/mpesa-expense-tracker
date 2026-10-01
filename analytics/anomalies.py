# analytics/anomalies.py
"""Detect unusually large transactions per category."""
import pandas as pd


def find_anomalies(df: pd.DataFrame, z_threshold: float = 2.0) -> pd.DataFrame:
    expenses = df[df["net_amount"] < 0].copy()
    if expenses.empty:
        return pd.DataFrame()

    expenses["abs_amount"] = expenses["net_amount"].abs()
    rows = []
    for txn_type, group in expenses.groupby("type"):
        if len(group) < 3:
            continue
        mean = group["abs_amount"].mean()
        std = group["abs_amount"].std()
        if std == 0 or pd.isna(std):
            continue
        threshold = mean + z_threshold * std
        for _, row in group[group["abs_amount"] > threshold].iterrows():
            rows.append({
                "date": row["date"],
                "type": txn_type,
                "details": row["details"][:80],
                "amount": row["abs_amount"],
                "category_mean": mean,
                "z_score": (row["abs_amount"] - mean) / std,
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("z_score", ascending=False).reset_index(drop=True)
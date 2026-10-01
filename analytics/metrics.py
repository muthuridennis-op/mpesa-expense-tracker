# analytics/metrics.py
"""Summary metrics."""
import pandas as pd


def compute_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"income": 0.0, "expenses": 0.0, "net": 0.0, "savings_rate": 0.0}
    income = float(df[df["net_amount"] > 0]["net_amount"].sum())
    expenses = float(df[df["net_amount"] < 0]["net_amount"].sum())
    net = income + expenses
    savings_rate = (net / income * 100) if income > 0 else 0.0
    return {
        "income": income,
        "expenses": expenses,
        "net": net,
        "savings_rate": savings_rate,
    }


def filter_by_month(df: pd.DataFrame, choice: str) -> pd.DataFrame:
    if df.empty or choice == "All":
        return df
    today = pd.Timestamp.today().normalize()
    if choice == "This month":
        start = today.replace(day=1)
    elif choice == "Last month":
        first_this = today.replace(day=1)
        start = (first_this - pd.Timedelta(days=1)).replace(day=1)
    elif choice == "Last 3 months":
        start = today - pd.Timedelta(days=90)
    else:
        return df
    return df[df["date"] >= start]
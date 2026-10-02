# analytics/metrics.py
"""Summary metrics and the month filter."""
import pandas as pd

from analytics.common import ensure_enriched, today_nairobi


def compute_summary(df: pd.DataFrame) -> dict:
    """Income / expenses / net / savings rate, excluding internal movements."""
    empty = {
        "income": 0.0, "expenses": 0.0, "net": 0.0, "savings_rate": 0.0,
        "fees": 0.0, "internal_count": 0, "internal_out": 0.0, "internal_in": 0.0,
    }
    if df is None or df.empty:
        return empty

    d = ensure_enriched(df)
    real = d[~d["is_internal"]]
    internal = d[d["is_internal"]]

    inc = float(real.loc[real["net_amount"] > 0, "net_amount"].sum())
    exp = float(real.loc[real["net_amount"] < 0, "net_amount"].sum())
    net = inc + exp
    fees = abs(float(real.loc[real["net_amount"] < 0, "charge"].sum()))

    return {
        "income": inc,
        "expenses": exp,                      # negative number
        "net": net,
        "savings_rate": (net / inc * 100) if inc > 0 else 0.0,
        "fees": fees,
        "internal_count": int(len(internal)),
        "internal_out": abs(float(internal.loc[internal["net_amount"] < 0, "net_amount"].sum())),
        "internal_in": float(internal.loc[internal["net_amount"] > 0, "net_amount"].sum()),
    }


def filter_by_month(df: pd.DataFrame, choice: str) -> pd.DataFrame:
    """Calendar-based filter (Nairobi time).

    This month     1st of this month -> today
    Last month     1st -> last day of the previous calendar month (upper bound!)
    Last 3 months  1st of the month two months ago -> today (3 calendar months)
    """
    if df is None or df.empty or choice == "All":
        return df

    today = today_nairobi()
    first_this = today.replace(day=1)
    end = None  # exclusive upper bound

    if choice == "This month":
        start = first_this
    elif choice == "Last month":
        start = (first_this - pd.Timedelta(days=1)).replace(day=1)
        end = first_this
    elif choice == "Last 3 months":
        start = (first_this - pd.DateOffset(months=2)).normalize()
    else:
        return df

    mask = df["date"] >= start
    if end is not None:
        mask &= df["date"] < end
    return df[mask]
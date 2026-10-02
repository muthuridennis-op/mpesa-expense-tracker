# analytics/forecast.py
"""Next-month expense forecast = active recurring commitments + average variable spend.

Fixes vs the first version:
  * recurring items are excluded from the variable part by receipt id (exact),
    not by guessing on the first word of a name
  * only complete months are averaged (partial first/last months drag it down)
  * both parts are broken down by *category*, so the table is consistent
  * the forecast month follows the data, not today's date
  * subscriptions that have stopped are not counted
"""
import pandas as pd

from analytics.common import ensure_enriched, partial_months, spending
from analytics.recurring import find_recurring


def build_forecast(df: pd.DataFrame, months_window: int = 3) -> dict | None:
    d = ensure_enriched(df)
    if d is None or d.empty:
        return None
    exp = spending(d)
    if exp.empty:
        return None

    partial = partial_months(d)
    all_months = sorted(exp["month"].unique())
    complete = [m for m in all_months if m not in partial]
    note = ""
    if complete:
        use_months = complete[-months_window:]
    else:
        use_months = all_months[-months_window:]
        note = "No complete month in the data; the average includes partial months."

    # Recurring (active only)
    rec = find_recurring(d)
    active = rec[rec["active"]] if not rec.empty else rec
    recurring_total = float(active["avg_amount"].sum()) if not active.empty else 0.0
    recurring_by_cat = (
        active.groupby("category")["avg_amount"].sum() if not active.empty
        else pd.Series(dtype=float)
    )
    recurring_receipts = (
        {r for lst in rec["receipts"] for r in lst} if not rec.empty else set()
    )

    # Variable spend over the window, excluding anything that belongs to a recurring series
    recent = exp[exp["month"].isin(use_months)]
    variable = recent[~recent["receipt"].isin(recurring_receipts)]
    n = max(len(use_months), 1)
    variable_total = float(variable["abs_amount"].sum() / n)
    variable_by_cat = variable.groupby("category")["abs_amount"].sum() / n

    by_cat = pd.DataFrame({"Recurring": recurring_by_cat, "Variable": variable_by_cat}).fillna(0.0)
    by_cat["Total"] = by_cat["Recurring"] + by_cat["Variable"]
    by_cat = by_cat.sort_values("Total", ascending=False)

    last_period = d["date"].max().to_period("M")
    monthly = (
        exp.groupby("month")["abs_amount"].sum().reset_index().sort_values("month")
    )
    monthly["partial"] = monthly["month"].isin(partial)

    return {
        "recurring_total": recurring_total,
        "variable_total": variable_total,
        "forecast_total": recurring_total + variable_total,
        "by_category": by_cat,
        "forecast_month": str(last_period + 1),
        "months_used": use_months,
        "monthly": monthly,
        "recurring": active,
        "note": note,
    }
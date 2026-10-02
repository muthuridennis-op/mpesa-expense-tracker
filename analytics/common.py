# analytics/common.py
"""Shared analytics helpers.

``enrich(df, rules)`` is the single entry point that turns the raw database
frame into the frame every page uses. It adds:

    abs_amount    absolute value of net_amount
    month         "YYYY-MM"
    payee_clean   normalised + fuzzy-clustered payee name
    category      from user rules, else a type default, else "Uncategorised"
    is_internal   Fuliza repayments, M-Shwari moves, anything categorised "Internal"

Pages should then use ``spending(df)`` / ``income(df)`` / ``real_flows(df)``
instead of re-implementing ``df[df.net_amount < 0]`` everywhere.

This module deliberately has no Streamlit import so it can be unit-tested.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd
from rapidfuzz import fuzz, process

from analytics.categories import (
    INTERNAL_CATEGORY,
    INTERNAL_TYPES,
    TYPE_DEFAULT_CATEGORY,
    UNCATEGORISED,
)


# ------------------------------------------------------------------
# Dates
# ------------------------------------------------------------------
def today_nairobi() -> pd.Timestamp:
    """Today's date in Kenya (servers usually run in UTC, 3 hours behind)."""
    try:
        return pd.Timestamp.now(tz="Africa/Nairobi").tz_localize(None).normalize()
    except Exception:
        return pd.Timestamp.today().normalize()


def partial_months(df: pd.DataFrame, tolerance_days: int = 3) -> set[str]:
    """Months the data does not fully cover (statement starts/ends mid-month)."""
    if df is None or df.empty:
        return set()
    first, last = df["date"].min(), df["date"].max()
    partial = set()
    if first.day > tolerance_days:
        partial.add(first.strftime("%Y-%m"))
    month_end = last.to_period("M").end_time.normalize()
    if (month_end - last.normalize()).days > tolerance_days:
        partial.add(last.strftime("%Y-%m"))
    return partial


# ------------------------------------------------------------------
# Payee normalisation + clustering
# ------------------------------------------------------------------
def normalize_payee(p: str) -> str:
    if not p:
        return ""
    p = re.sub(r"[\d*]{4,}", " ", p)            # phone fragments like 2547****123
    p = re.sub(r"[^\w\s&'.-]", " ", p)
    p = re.sub(r"\s+", " ", p).strip(" -.")
    return p.title()


@lru_cache(maxsize=16)
def cluster_names(names: tuple[str, ...], threshold: int = 90) -> dict[str, str]:
    """Map every name to a representative, merging near-identical spellings.

    token_sort_ratio (not token_set_ratio) so that "John" does not merge into
    "John Kamau".
    """
    reps: list[str] = []
    reps_lower: list[str] = []
    mapping: dict[str, str] = {}
    for name in names:
        if not name:
            mapping[name] = ""
            continue
        hit = None
        if reps_lower:
            hit = process.extractOne(
                name.lower(), reps_lower,
                scorer=fuzz.token_sort_ratio, score_cutoff=threshold,
            )
        if hit is None:
            reps.append(name)
            reps_lower.append(name.lower())
            mapping[name] = name
        else:
            mapping[name] = reps[hit[2]]
    return mapping


def _clean_payees(payees: pd.Series) -> pd.Series:
    raw_unique = payees.unique().tolist()
    norm = {p: normalize_payee(p) for p in raw_unique}
    clusters = cluster_names(tuple(sorted(set(norm.values()))))
    return payees.map(lambda p: clusters.get(norm.get(p, ""), "") if p else "")


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------
def _assign_categories(df: pd.DataFrame, rules: list[dict]) -> pd.Series:
    cat = pd.Series([None] * len(df), index=df.index, dtype=object)
    haystack = (df["payee"] + " " + df["details"]).str.lower()
    for rule in sorted(rules, key=lambda r: len(r.get("pattern") or ""), reverse=True):
        pattern = (rule.get("pattern") or "").strip().lower()
        if not pattern:
            continue
        mask = cat.isna() & haystack.str.contains(pattern, regex=False)
        cat.loc[mask] = rule["category"]
    default = df["type"].map(TYPE_DEFAULT_CATEGORY).fillna(UNCATEGORISED)
    return cat.fillna(default)


# ------------------------------------------------------------------
# Enrichment
# ------------------------------------------------------------------
def enrich(df: pd.DataFrame, rules: list[dict] | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in ("details", "payee", "type", "receipt"):
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"])
    out["net_amount"] = pd.to_numeric(out["net_amount"], errors="coerce").fillna(0.0)
    if "charge" in out.columns:
        out["charge"] = pd.to_numeric(out["charge"], errors="coerce").fillna(0.0)
    else:
        out["charge"] = 0.0

    out["abs_amount"] = out["net_amount"].abs()
    out["month"] = out["date"].dt.strftime("%Y-%m")
    out["payee_clean"] = _clean_payees(out["payee"])
    out["category"] = _assign_categories(out, rules or [])
    out["is_internal"] = out["type"].isin(INTERNAL_TYPES) | (out["category"] == INTERNAL_CATEGORY)
    return out.reset_index(drop=True)


def ensure_enriched(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "is_internal" in df.columns:
        return df
    return enrich(df)


# ------------------------------------------------------------------
# One definition of "income" and "spending" for the whole app
# ------------------------------------------------------------------
def real_flows(df: pd.DataFrame) -> pd.DataFrame:
    """Everything except internal movements."""
    d = ensure_enriched(df)
    if d is None or d.empty:
        return d
    return d[~d["is_internal"]]


def spending(df: pd.DataFrame) -> pd.DataFrame:
    """Real expenses (net_amount < 0, not internal), with abs_amount."""
    r = real_flows(df)
    if r is None or r.empty:
        return pd.DataFrame()
    return r[r["net_amount"] < 0].copy()


def income(df: pd.DataFrame) -> pd.DataFrame:
    r = real_flows(df)
    if r is None or r.empty:
        return pd.DataFrame()
    return r[r["net_amount"] > 0].copy()
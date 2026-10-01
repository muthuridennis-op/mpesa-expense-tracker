# db.py
"""Supabase persistence layer for M-Pesa transactions."""
import os
import streamlit as st
import pandas as pd
from supabase import create_client


@st.cache_resource
def get_client():
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        url = key = None
    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def save_transactions(df: pd.DataFrame, source: str = "mpesa") -> int:
    """Upsert transactions. Returns count of rows sent."""
    client = get_client()
    if client is None:
        return 0

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "receipt": r["receipt"],
            "txn_date": r["date"].date().isoformat() if hasattr(r["date"], "date") else str(r["date"]),
            "txn_time": r.get("time", ""),
            "details": r.get("details", ""),
            "payee": r.get("payee", ""),
            "txn_type": r.get("type", ""),
            "direction": r.get("direction", ""),
            "amount": float(r.get("amount", 0) or 0),
            "charge": float(r.get("charge", 0) or 0),
            "net_amount": float(r.get("net_amount", 0) or 0),
            "status": r.get("status", "Completed"),
            "source": source,
        })

    BATCH = 500
    inserted = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        try:
            client.table("mpesa_transactions").upsert(
                batch, on_conflict="receipt,txn_date"
            ).execute()
            inserted += len(batch)
        except Exception as e:
            st.warning(f"Batch {i} failed: {e}")
    return inserted


def load_transactions() -> pd.DataFrame:
    """Load all transactions from Supabase."""
    client = get_client()
    if client is None:
        return pd.DataFrame()
    try:
        resp = client.table("mpesa_transactions").select("*").order("txn_date").execute()
    except Exception as e:
        st.warning(f"Could not load from database: {e}")
        return pd.DataFrame()
    if not resp.data:
        return pd.DataFrame()
    df = pd.DataFrame(resp.data)
    df = df.rename(columns={"txn_date": "date", "txn_time": "time", "txn_type": "type"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["net_amount"] = pd.to_numeric(df["net_amount"], errors="coerce")
    return df


def delete_all() -> bool:
    """Delete every transaction. Use with caution."""
    client = get_client()
    if client is None:
        return False
    try:
        client.table("mpesa_transactions").delete().neq("receipt", "").execute()
        return True
    except Exception:
        return False
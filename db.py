# db.py
"""Supabase persistence layer with auth, budgets, and transaction editing.

IMPORTANT: Do NOT decorate load_transactions() or load_budgets() with
@st.cache_data. Streamlit's cache_data is keyed only by function arguments
and is shared across ALL user sessions. Since these functions take no
user-identifying argument, caching them would serve one user's rows to
another. Queries to Supabase are fast enough that skipping the cache is
the correct choice for a multi-user app.
"""
import os
import streamlit as st
import pandas as pd
from supabase import create_client


# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------
@st.cache_resource
def get_client():
    """Return a Supabase client (resource cache is safe — no user data inside)."""
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


def _authed_client():
    """Return client with the current user's JWT attached (so RLS applies)."""
    client = get_client()
    if client is None:
        return None
    token = st.session_state.get("access_token")
    if token:
        try:
            client.postgrest.auth(token)
        except Exception:
            pass
    return client


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
def sign_in(email: str, password: str):
    """Sign in with email + password. Returns (success, message)."""
    client = get_client()
    if client is None:
        return False, "Supabase not configured."
    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
        if resp.user:
            st.session_state["user"] = {"id": resp.user.id, "email": resp.user.email}
            st.session_state["access_token"] = resp.session.access_token
            client.postgrest.auth(resp.session.access_token)
            return True, "Signed in."
        return False, "Sign-in failed."
    except Exception as e:
        return False, str(e)


def sign_out():
    """Clear the current session."""
    client = get_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    for k in ["user", "access_token", "df", "working_df", "last_file"]:
        st.session_state.pop(k, None)


def current_user():
    return st.session_state.get("user")


# ------------------------------------------------------------------
# Transactions
# ------------------------------------------------------------------
def save_transactions(df: pd.DataFrame, source: str = "mpesa") -> int:
    """Upsert transactions for the current user. Returns count sent."""
    client = _authed_client()
    user = current_user()
    if client is None or user is None:
        return 0

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "user_id": user["id"],
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
                batch, on_conflict="user_id,receipt,txn_date"
            ).execute()
            inserted += len(batch)
        except Exception as e:
            st.warning(f"Batch {i} failed: {e}")
    return inserted


def load_transactions() -> pd.DataFrame:
    """
    Load all transactions for the currently logged-in user.

    NOTE: No @st.cache_data here on purpose. See module docstring.
    """
    client = _authed_client()
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


def update_transaction(receipt: str, txn_date: str, updates: dict) -> bool:
    """Update one transaction. RLS ensures only the owner can."""
    client = _authed_client()
    if client is None:
        return False
    try:
        client.table("mpesa_transactions").update(updates).eq(
            "receipt", receipt
        ).eq("txn_date", txn_date).execute()
        return True
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False


def delete_transaction(receipt: str, txn_date: str) -> bool:
    """Delete one transaction. RLS ensures only the owner can."""
    client = _authed_client()
    if client is None:
        return False
    try:
        client.table("mpesa_transactions").delete().eq(
            "receipt", receipt
        ).eq("txn_date", txn_date).execute()
        return True
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False


def delete_all() -> bool:
    """Delete every transaction for the current user."""
    client = _authed_client()
    if client is None:
        return False
    try:
        client.table("mpesa_transactions").delete().neq("receipt", "").execute()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------
# Budgets
# ------------------------------------------------------------------
def load_budgets(month_key: str) -> dict:
    """
    Return {category: budget_amount} for a given month for the current user.

    NOTE: No @st.cache_data here on purpose. See module docstring.
    """
    client = _authed_client()
    if client is None:
        return {}
    try:
        resp = client.table("mpesa_budgets").select("*").eq("month_key", month_key).execute()
    except Exception:
        return {}
    return {r["category"]: float(r["budget_amount"]) for r in (resp.data or [])}


def save_budget(category: str, month_key: str, amount: float) -> bool:
    """Upsert a single budget for the current user."""
    client = _authed_client()
    user = current_user()
    if client is None or user is None:
        return False
    try:
        client.table("mpesa_budgets").upsert({
            "user_id": user["id"],
            "category": category,
            "month_key": month_key,
            "budget_amount": float(amount),
        }, on_conflict="user_id,category,month_key").execute()
        return True
    except Exception as e:
        st.error(f"Budget save failed: {e}")
        return False
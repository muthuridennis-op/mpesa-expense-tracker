# db.py
"""Supabase persistence layer with auth, budgets, and transaction editing.

IMPORTANT:
1. Do NOT decorate load_transactions() or load_budgets() with @st.cache_data.
   cache_data is shared across sessions and would leak data between users.
2. Every write operation re-attaches the user's JWT before the query, because
   Supabase access tokens expire (default 1 hour) and the PostgREST client
   caches the last-attached token. Without re-attaching, writes can silently
   affect 0 rows while returning 200 OK.
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
    """Return a Supabase client. Safe to cache — it holds no user data."""
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
    """
    Return a Supabase client with the current user's JWT freshly attached.

    Re-attaching on every call is important:
    - The Supabase Python client caches the last auth token on the postgrest
      sub-client. If we only set it once at login, the token may expire and
      the client will keep sending the stale token.
    - When the token is stale, PostgREST treats the request as `anon`.
      RLS blocks the row, and DELETE/UPDATE reports success but affects 0 rows.
    """
    client = get_client()
    if client is None:
        return None

    token = st.session_state.get("access_token")
    if not token:
        return None

    try:
        # Refresh the session if we can; this updates the access_token in place
        # if the refresh_token is still valid.
        try:
            session = client.auth.get_session()
            if session and session.access_token:
                token = session.access_token
                st.session_state["access_token"] = token
        except Exception:
            # Refresh failed — keep using the existing token and hope it's valid.
            pass

        client.postgrest.auth(token)
        return client
    except Exception as e:
        st.error(f"Failed to attach auth token: {e}")
        return None


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
def sign_in(email: str, password: str):
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
            # Re-attach JWT for every batch in case it changed mid-loop
            client = _authed_client()
            if client is None:
                st.warning(f"Auth lost mid-upload at batch {i}. Stopping.")
                break
            client.table("mpesa_transactions").upsert(
                batch, on_conflict="user_id,receipt,txn_date"
            ).execute()
            inserted += len(batch)
        except Exception as e:
            st.warning(f"Batch {i} failed: {e}")
    return inserted


def load_transactions() -> pd.DataFrame:
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


def count_transactions() -> int:
    """Return the number of transactions for the current user."""
    client = _authed_client()
    if client is None:
        return -1
    try:
        resp = client.table("mpesa_transactions").select("id", count="exact").execute()
        return resp.count or 0
    except Exception:
        return -1


def delete_all() -> tuple[bool, str]:
    """
    Delete every transaction for the current user.

    Uses a fresh JWT-attached client, verifies the delete actually removed
    rows, and reports exactly how many rows were affected.
    """
    user = current_user()
    if user is None:
        return False, "Not signed in."

    # Count before
    before = count_transactions()
    if before < 0:
        return False, "Could not count rows before delete. Check your session."
    if before == 0:
        return True, "Nothing to delete."

    # Delete — MUST use a freshly authed client
    client = _authed_client()
    if client is None:
        return False, "Auth token missing. Please log out and log in again."

    try:
        resp = (
            client.table("mpesa_transactions")
            .delete()
            .eq("user_id", user["id"])
            .execute()
        )
    except Exception as e:
        return False, f"Delete request failed: {e}"

    # Count after
    after = count_transactions()
    if after < 0:
        return False, f"Delete sent but could not verify. Before={before}."

    deleted = before - after

    if deleted == 0:
        return False, (
            f"Delete returned success but affected 0 rows. "
            f"Likely an expired auth token. "
            f"Log out and log in again, then retry."
        )
    if after == 0:
        return True, f"Deleted all {deleted} transactions."
    return True, f"Deleted {deleted} of {before} transactions. {after} remain."


def delete_by_range(from_date_iso: str, to_date_iso: str) -> tuple[bool, str]:
    """
    Delete transactions in a date range for the current user.
    Dates are ISO strings (YYYY-MM-DD), inclusive.
    """
    user = current_user()
    if user is None:
        return False, "Not signed in."

    client = _authed_client()
    if client is None:
        return False, "Auth token missing. Please log out and log in again."

    # Count matching rows first
    try:
        before = (
            client.table("mpesa_transactions")
            .select("id", count="exact")
            .eq("user_id", user["id"])
            .gte("txn_date", from_date_iso)
            .lte("txn_date", to_date_iso)
            .execute()
        )
        count_before = before.count or 0
    except Exception as e:
        return False, f"Count failed: {e}"

    if count_before == 0:
        return True, "No transactions in that range."

    # Delete
    try:
        client.table("mpesa_transactions").delete().eq(
            "user_id", user["id"]
        ).gte("txn_date", from_date_iso).lte("txn_date", to_date_iso).execute()
    except Exception as e:
        return False, f"Delete failed: {e}"

    # Verify
    try:
        after = (
            client.table("mpesa_transactions")
            .select("id", count="exact")
            .eq("user_id", user["id"])
            .gte("txn_date", from_date_iso)
            .lte("txn_date", to_date_iso)
            .execute()
        )
        count_after = after.count or 0
    except Exception:
        count_after = -1

    deleted = count_before - count_after

    if deleted <= 0:
        return False, (
            f"Delete affected 0 rows out of {count_before}. "
            f"Likely an expired auth token."
        )
    return True, f"Deleted {deleted} transactions in range."


# ------------------------------------------------------------------
# Budgets
# ------------------------------------------------------------------
def load_budgets(month_key: str) -> dict:
    client = _authed_client()
    if client is None:
        return {}
    try:
        resp = client.table("mpesa_budgets").select("*").eq("month_key", month_key).execute()
    except Exception:
        return {}
    return {r["category"]: float(r["budget_amount"]) for r in (resp.data or [])}


def save_budget(category: str, month_key: str, amount: float) -> bool:
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
# db.py
"""Supabase persistence layer: auth, transactions, budgets, category rules.

Design rules (read before editing)
----------------------------------
1. ONE SUPABASE CLIENT PER BROWSER SESSION, stored in st.session_state.
   Never use @st.cache_resource for the client: it is shared by every visitor,
   so one user's JWT/session would leak into another user's requests.
2. Never decorate load_* functions with @st.cache_data (shared across sessions).
3. The JWT is refreshed before it expires and re-attached before every query.
4. Every query also filters on user_id. RLS is the real guard; this is defence
   in depth and makes the intent explicit.
5. Writes verify that rows were actually affected (RLS / expired tokens make
   PostgREST return 200 with 0 rows).
6. Reads are paginated: PostgREST returns at most ~1000 rows per request.
"""
from __future__ import annotations

import base64
import json
import os
import time

import pandas as pd
import streamlit as st
from supabase import create_client

TXN_TABLE = "mpesa_transactions"
BUDGET_TABLE = "mpesa_budgets"
RULES_TABLE = "mpesa_category_rules"
PAGE_SIZE = 1000

# Everything we put in session_state that belongs to the signed-in user.
_USER_STATE_KEYS = [
    "user", "access_token", "refresh_token", "_sb_client",
    "df", "full_df", "working_df", "rules", "last_file",
    "parse_reports", "upload_summary", "_flash",
]


# ------------------------------------------------------------------
# Client (per session)
# ------------------------------------------------------------------
def _config() -> tuple[str | None, str | None]:
    url = key = None
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        pass
    return (url or os.environ.get("SUPABASE_URL"), key or os.environ.get("SUPABASE_KEY"))


def get_client():
    """Return this browser session's Supabase client (created on first use)."""
    client = st.session_state.get("_sb_client")
    if client is None:
        url, key = _config()
        if not url or not key:
            return None
        client = create_client(url, key)
        st.session_state["_sb_client"] = client
    return client


def _jwt_exp(token: str) -> float | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp"))
    except Exception:
        return None


def _clear_auth(message: str | None = None) -> None:
    for k in _USER_STATE_KEYS:
        st.session_state.pop(k, None)
    if message:
        st.session_state["_auth_msg"] = message


def _authed_client():
    """Client with a valid, freshly attached JWT for the current user, or None."""
    client = get_client()
    token = st.session_state.get("access_token")
    if client is None or not token:
        return None

    exp = _jwt_exp(token)
    if exp is not None and exp - time.time() < 60:  # expired or about to
        refresh = st.session_state.get("refresh_token")
        try:
            if not refresh:
                raise RuntimeError("no refresh token")
            resp = client.auth.refresh_session(refresh)
            session = getattr(resp, "session", None)
            if session is None:
                raise RuntimeError("no session returned")
            token = session.access_token
            st.session_state["access_token"] = token
            st.session_state["refresh_token"] = session.refresh_token
        except Exception:
            _clear_auth("Your session expired. Please sign in again.")
            return None

    try:
        client.postgrest.auth(token)
    except Exception as e:
        st.error(f"Failed to attach auth token: {e}")
        return None
    return client


def _user_id() -> str | None:
    user = st.session_state.get("user")
    return user["id"] if user else None


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
def sign_in(email: str, password: str):
    client = get_client()
    if client is None:
        return False, "Supabase not configured."
    try:
        resp = client.auth.sign_in_with_password({"email": email, "password": password})
        if resp.user and resp.session:
            st.session_state["user"] = {"id": resp.user.id, "email": resp.user.email}
            st.session_state["access_token"] = resp.session.access_token
            st.session_state["refresh_token"] = resp.session.refresh_token
            client.postgrest.auth(resp.session.access_token)
            return True, "Signed in."
        return False, "Sign-in failed."
    except Exception as e:
        return False, str(e)


def sign_out():
    client = st.session_state.get("_sb_client")
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    _clear_auth()


def current_user():
    return st.session_state.get("user")


# ------------------------------------------------------------------
# Small conversion helpers (NaN-safe: NaN is truthy, so `x or 0` is not enough)
# ------------------------------------------------------------------
def _num(x, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return default if v != v else v


def _num_or_none(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _txt(x) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return ""
    return str(x)


# ------------------------------------------------------------------
# Transactions
# ------------------------------------------------------------------
def _row_payload(r, user_id: str, source: str) -> dict:
    d = r["date"]
    return {
        "user_id": user_id,
        "receipt": _txt(r.get("receipt")),
        "txn_date": d.date().isoformat() if hasattr(d, "date") else str(d),
        "txn_time": _txt(r.get("time")),
        "details": _txt(r.get("details")),
        "payee": _txt(r.get("payee")),
        "txn_type": _txt(r.get("type")),
        "direction": _txt(r.get("direction")),
        "amount": _num(r.get("amount")),
        "charge": _num(r.get("charge")),
        "net_amount": _num(r.get("net_amount")),
        "balance": _num_or_none(r.get("balance")),
        "status": _txt(r.get("status")) or "Completed",
        "source": source,
    }


def save_transactions(df: pd.DataFrame, source: str = "mpesa", overwrite: bool = False) -> int:
    """Insert transactions. Returns the number of rows actually written.

    overwrite=False (default): rows that already exist are left untouched, so
        edits you made in the Explorer survive re-uploading a statement.
    overwrite=True: existing rows are replaced with the freshly parsed data.
    """
    user_id = _user_id()
    if user_id is None or df is None or df.empty:
        return 0

    rows = [_row_payload(r, user_id, source) for _, r in df.iterrows()]
    written = 0
    warned_balance = False

    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        client = _authed_client()  # re-attach / refresh before every batch
        if client is None:
            st.warning(f"Auth lost mid-upload at batch {i}. Stopping.")
            break

        def _upsert(b):
            return (
                client.table(TXN_TABLE)
                .upsert(b, on_conflict="user_id,receipt,txn_date", ignore_duplicates=not overwrite)
                .execute()
            )

        try:
            try:
                resp = _upsert(batch)
            except Exception as e:
                if "balance" in str(e).lower():  # migration not run yet
                    if not warned_balance:
                        st.warning("The `balance` column is missing. Run schema.sql in Supabase.")
                        warned_balance = True
                    batch = [{k: v for k, v in row.items() if k != "balance"} for row in batch]
                    resp = _upsert(batch)
                else:
                    raise
            written += len(resp.data or [])
        except Exception as e:
            st.warning(f"Batch {i} failed: {e}")
    return written


def load_transactions() -> pd.DataFrame:
    """Load ALL of the user's transactions (paginated)."""
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return pd.DataFrame()

    rows: list[dict] = []
    start = 0
    try:
        while True:
            resp = (
                client.table(TXN_TABLE).select("*")
                .eq("user_id", uid)
                .order("txn_date").order("receipt")
                .range(start, start + PAGE_SIZE - 1)
                .execute()
            )
            batch = resp.data or []
            if not batch:
                break
            rows.extend(batch)
            start += len(batch)
    except Exception as e:
        st.warning(f"Could not load from database: {e}")
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).rename(
        columns={"txn_date": "date", "txn_time": "time", "txn_type": "type"}
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("amount", "charge", "net_amount", "balance"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("details", "payee", "type", "time", "direction"):
        if col in df.columns:
            df[col] = df[col].fillna("")
    return df


def update_transaction(receipt: str, txn_date: str, updates: dict) -> bool:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return False
    try:
        resp = (
            client.table(TXN_TABLE).update(updates)
            .eq("user_id", uid).eq("receipt", receipt).eq("txn_date", txn_date)
            .execute()
        )
    except Exception as e:
        st.error(f"Update failed: {e}")
        return False
    if not (resp.data or []):
        st.error("No rows were updated (expired session or blocked by policy). Sign in again.")
        return False
    return True


def delete_transaction(receipt: str, txn_date: str) -> bool:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return False
    try:
        resp = (
            client.table(TXN_TABLE).delete()
            .eq("user_id", uid).eq("receipt", receipt).eq("txn_date", txn_date)
            .execute()
        )
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False
    if not (resp.data or []):
        st.error("No rows were deleted (expired session or blocked by policy). Sign in again.")
        return False
    return True


def count_transactions() -> int:
    """Number of transactions for the current user, or -1 on error."""
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return -1
    try:
        resp = client.table(TXN_TABLE).select("id", count="exact").eq("user_id", uid).limit(1).execute()
        return resp.count or 0
    except Exception:
        return -1


def count_in_range(from_iso: str, to_iso: str) -> int:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return -1
    try:
        resp = (
            client.table(TXN_TABLE).select("id", count="exact")
            .eq("user_id", uid).gte("txn_date", from_iso).lte("txn_date", to_iso)
            .limit(1).execute()
        )
        return resp.count or 0
    except Exception:
        return -1


def date_bounds():
    """(first_date, last_date) of the user's data as datetime.date, or None."""
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return None
    try:
        lo = (client.table(TXN_TABLE).select("txn_date").eq("user_id", uid)
              .order("txn_date").limit(1).execute())
        hi = (client.table(TXN_TABLE).select("txn_date").eq("user_id", uid)
              .order("txn_date", desc=True).limit(1).execute())
        if not lo.data or not hi.data:
            return None
        return (pd.Timestamp(lo.data[0]["txn_date"]).date(),
                pd.Timestamp(hi.data[0]["txn_date"]).date())
    except Exception:
        return None


def delete_all() -> tuple[bool, str]:
    """Delete every transaction for the current user and verify the result."""
    uid = _user_id()
    if uid is None:
        return False, "Not signed in."

    before = count_transactions()
    if before < 0:
        return False, "Could not count rows before delete. Check your session."
    if before == 0:
        return True, "Nothing to delete."

    client = _authed_client()
    if client is None:
        return False, "Auth token missing. Please log out and log in again."
    try:
        client.table(TXN_TABLE).delete().eq("user_id", uid).execute()
    except Exception as e:
        return False, f"Delete request failed: {e}"

    after = count_transactions()
    if after < 0:
        return False, f"Delete sent but could not verify. Before={before}."
    deleted = before - after
    if deleted <= 0:
        return False, ("Delete returned success but affected 0 rows. "
                       "Likely an expired session. Log out, log in again, then retry.")
    if after == 0:
        return True, f"Deleted all {deleted} transactions."
    return True, f"Deleted {deleted} of {before} transactions. {after} remain."


def delete_by_range(from_iso: str, to_iso: str) -> tuple[bool, str]:
    """Delete transactions in an inclusive date range for the current user."""
    uid = _user_id()
    if uid is None:
        return False, "Not signed in."

    before = count_in_range(from_iso, to_iso)
    if before < 0:
        return False, "Could not count rows. Check your session."
    if before == 0:
        return True, "No transactions in that range."

    client = _authed_client()
    if client is None:
        return False, "Auth token missing. Please log out and log in again."
    try:
        (client.table(TXN_TABLE).delete().eq("user_id", uid)
         .gte("txn_date", from_iso).lte("txn_date", to_iso).execute())
    except Exception as e:
        return False, f"Delete failed: {e}"

    after = count_in_range(from_iso, to_iso)
    deleted = before - max(after, 0)
    if deleted <= 0:
        return False, f"Delete affected 0 rows out of {before}. Likely an expired session."
    return True, f"Deleted {deleted} transactions in range."


# ------------------------------------------------------------------
# Budgets
# ------------------------------------------------------------------
def load_budgets(month_key: str) -> dict:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return {}
    try:
        resp = (client.table(BUDGET_TABLE).select("*")
                .eq("user_id", uid).eq("month_key", month_key).execute())
    except Exception:
        return {}
    return {r["category"]: float(r["budget_amount"]) for r in (resp.data or [])}


def save_budget(category: str, month_key: str, amount: float) -> bool:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return False
    try:
        client.table(BUDGET_TABLE).upsert({
            "user_id": uid,
            "category": category,
            "month_key": month_key,
            "budget_amount": float(amount),
        }, on_conflict="user_id,category,month_key").execute()
        return True
    except Exception as e:
        st.error(f"Budget save failed: {e}")
        return False


# ------------------------------------------------------------------
# Category rules  (pattern -> category)
# ------------------------------------------------------------------
def load_rules() -> list[dict]:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None:
        return []
    try:
        resp = (client.table(RULES_TABLE).select("pattern,category")
                .eq("user_id", uid).execute())
    except Exception as e:
        if not st.session_state.get("_rules_warned"):
            st.session_state["_rules_warned"] = True
            st.warning(f"Category rules unavailable (did you run schema.sql?): {e}")
        return []
    return [{"pattern": r["pattern"], "category": r["category"]} for r in (resp.data or [])]


def save_rules(rules: list[dict]) -> bool:
    """Upsert one or many rules: [{"pattern": ..., "category": ...}, ...]."""
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None or not rules:
        return False
    payload = [
        {"user_id": uid, "pattern": r["pattern"].strip().lower(), "category": r["category"].strip()}
        for r in rules if r.get("pattern", "").strip() and r.get("category", "").strip()
    ]
    if not payload:
        return False
    try:
        client.table(RULES_TABLE).upsert(payload, on_conflict="user_id,pattern").execute()
        return True
    except Exception as e:
        st.error(f"Saving rules failed: {e}")
        return False


def delete_rules(patterns: list[str]) -> bool:
    client = _authed_client()
    uid = _user_id()
    if client is None or uid is None or not patterns:
        return False
    try:
        client.table(RULES_TABLE).delete().eq("user_id", uid).in_("pattern", patterns).execute()
        return True
    except Exception as e:
        st.error(f"Deleting rules failed: {e}")
        return False
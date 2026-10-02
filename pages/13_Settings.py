# pages/13_Settings.py
import streamlit as st

from db import (
    count_in_range, count_transactions, current_user, date_bounds,
    delete_all, delete_by_range, get_client,
)
from ui_helpers import flash, show_df, show_flash, sk

st.title("⚙️ Settings")
show_flash()

if get_client() is None:
    st.warning("Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY to your Streamlit secrets.")
    st.code('SUPABASE_URL = "https://xxxx.supabase.co"\nSUPABASE_KEY = "your-ANON-key"', language="toml")
    st.stop()

st.success("✅ Connected to Supabase.")

# ------------------------------------------------------------------
# Live stats (asked of the database: no full download, no 1000-row cap)
# ------------------------------------------------------------------
live_count = count_transactions()
if live_count < 0:
    st.error("Could not read the transaction count. Try logging out and in again.")
else:
    st.metric("Transactions in database", live_count)

bounds = date_bounds()
if bounds:
    st.metric("Date range", f"{bounds[0]} → {bounds[1]}")


def _after_delete():
    for k in ("df", "full_df", "working_df", "del_from", "del_to",
              "del_range_confirm", "del_all_confirm"):
        st.session_state.pop(k, None)
    st.rerun()


# ------------------------------------------------------------------
# Delete by date range
# ------------------------------------------------------------------
st.divider()
st.subheader("🗓️ Delete transactions by date range")

if not bounds:
    st.caption("No transactions to delete.")
else:
    min_date, max_date = bounds
    for k in ("del_from", "del_to"):  # stale values outside the new bounds would raise
        v = st.session_state.get(k)
        if v is not None and not (min_date <= v <= max_date):
            st.session_state.pop(k)

    c1, c2 = st.columns(2)
    from_date = c1.date_input("From", value=min_date, min_value=min_date, max_value=max_date, key="del_from")
    to_date = c2.date_input("To", value=max_date, min_value=min_date, max_value=max_date, key="del_to")

    if from_date > to_date:
        st.error("From date must be before or equal to To date.")
    else:
        n = count_in_range(from_date.isoformat(), to_date.isoformat())
        st.info(f"This will delete **{n}** transactions between **{from_date}** and **{to_date}**.")

        full = st.session_state.get("full_df")
        if full is not None and not full.empty and n > 0:
            preview = full[(full["date"].dt.date >= from_date) & (full["date"].dt.date <= to_date)]
            with st.expander("Preview transactions to be deleted"):
                show_df(preview[["date", "payee", "type", "net_amount", "receipt"]]
                        .sort_values("date", ascending=False).head(300))

        confirm = st.checkbox("I understand this will permanently delete these transactions.",
                              key="del_range_confirm")
        if st.button("🗑️ Delete transactions in this range", disabled=not confirm or n <= 0, **sk("button")):
            ok, msg = delete_by_range(from_date.isoformat(), to_date.isoformat())
            if ok:
                flash(msg)
                _after_delete()
            else:
                st.error(msg)

# ------------------------------------------------------------------
# Delete all
# ------------------------------------------------------------------
st.divider()
st.subheader("⚠️ Danger zone")
st.caption("These actions are irreversible.")
confirm_all = st.checkbox("I understand this will delete ALL my transactions.", key="del_all_confirm")
if st.button("🗑️ Delete ALL transactions", disabled=not confirm_all, **sk("button")):
    ok, msg = delete_all()
    if ok:
        flash(msg)
        _after_delete()
    else:
        st.error(msg)

# ------------------------------------------------------------------
# Session info (no token material is displayed)
# ------------------------------------------------------------------
with st.expander("🔎 Session info"):
    user = current_user()
    st.write(f"**User email:** {user['email'] if user else 'not signed in'}")
    st.write(f"**Access token present:** {'yes' if st.session_state.get('access_token') else 'NO'}")
    st.write(f"**Refresh token present:** {'yes' if st.session_state.get('refresh_token') else 'NO'}")
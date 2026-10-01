# pages/13_Settings.py
import streamlit as st
from db import (
    get_client, delete_all, delete_by_range,
    load_transactions, current_user, count_transactions,
)

st.title("⚙️ Settings")

client = get_client()
if client is None:
    st.warning(
        "Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY to your "
        "Streamlit secrets to enable persistence."
    )
    st.code(
        """
# In Streamlit Cloud → Settings → Secrets:
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "your-anon-key"
        """,
        language="toml",
    )
    st.stop()

st.success("✅ Connected to Supabase.")

# ------------------------------------------------------------------
# Current database stats
# ------------------------------------------------------------------
live_count = count_transactions()
if live_count < 0:
    st.error("Could not read the transaction count. Try logging out and in again.")
else:
    st.metric("Transactions in database (live count)", live_count)

df = load_transactions()
if not df.empty:
    st.metric("Date range", f"{df['date'].min().date()} → {df['date'].max().date()}")

st.divider()

# ------------------------------------------------------------------
# Delete by date range
# ------------------------------------------------------------------
st.subheader("🗓️ Delete transactions by date range")

if df.empty:
    st.caption("No transactions to delete.")
else:
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input(
            "From", value=min_date,
            min_value=min_date, max_value=max_date, key="del_from",
        )
    with col2:
        to_date = st.date_input(
            "To", value=max_date,
            min_value=min_date, max_value=max_date, key="del_to",
        )

    if from_date > to_date:
        st.error("From date must be before or equal to To date.")
    else:
        in_range = df[
            (df["date"].dt.date >= from_date) & (df["date"].dt.date <= to_date)
        ]
        st.info(
            f"This will delete **{len(in_range)}** transactions "
            f"between **{from_date}** and **{to_date}**."
        )

        if not in_range.empty:
            with st.expander("Preview transactions to be deleted"):
                st.dataframe(
                    in_range[["date", "payee", "type", "net_amount", "receipt"]]
                    .sort_values("date", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )

        confirm_range = st.checkbox(
            "I understand this will permanently delete these transactions.",
            key="del_range_confirm",
        )

        if st.button(
            "🗑️ Delete transactions in this range",
            type="secondary",
            disabled=not confirm_range or in_range.empty,
        ):
            ok, msg = delete_by_range(
                from_date.isoformat(), to_date.isoformat()
            )
            if ok:
                st.session_state.pop("df", None)
                st.session_state.pop("working_df", None)
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

st.divider()

# ------------------------------------------------------------------
# Delete all (nuclear)
# ------------------------------------------------------------------
st.subheader("⚠️ Danger zone")
st.caption("These actions are irreversible.")

confirm_all = st.checkbox(
    "I understand this will delete ALL my transactions.",
    key="del_all_confirm",
)

if st.button(
    "🗑️ Delete ALL transactions from the database",
    type="secondary",
    disabled=not confirm_all,
):
    ok, msg = delete_all()
    if ok:
        st.session_state.pop("df", None)
        st.session_state.pop("working_df", None)
        st.success(msg)
        st.rerun()
    else:
        st.error(msg)
        st.info(
            "If this keeps failing, open the Supabase SQL editor and run:\n\n"
            "```sql\n"
            "delete from mpesa_transactions where user_id = 'YOUR-UUID';\n"
            "```"
        )

st.divider()

# ------------------------------------------------------------------
# Debug info
# ------------------------------------------------------------------
with st.expander("🔎 Session debug info"):
    user = current_user()
    st.write(f"**User email:** {user['email'] if user else 'not signed in'}")
    st.write(f"**User ID:** {user['id'] if user else '—'}")
    st.write(
        f"**Access token present:** "
        f"{'yes' if st.session_state.get('access_token') else 'NO'}"
    )
    token = st.session_state.get("access_token")
    if token:
        st.write(f"**Token prefix:** `{token[:30]}...`")
    st.write(f"**Live transaction count:** {live_count}")

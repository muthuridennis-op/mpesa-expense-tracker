# pages/13_Settings.py
import streamlit as st
from db import get_client, delete_all, load_transactions

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

df = load_transactions()
st.metric("Transactions in database", len(df))
if not df.empty:
    st.metric("Date range", f"{df['date'].min().date()} → {df['date'].max().date()}")

st.divider()
st.subheader("Danger zone")
st.caption("These actions are irreversible.")
if st.button("🗑️ Delete ALL transactions from the database", type="secondary"):
    confirm = st.checkbox("I understand this will delete everything.")
    if confirm:
        if delete_all():
            st.session_state.pop("df", None)
            st.success("All transactions deleted.")
            st.rerun()
        else:
            st.error("Delete failed.")
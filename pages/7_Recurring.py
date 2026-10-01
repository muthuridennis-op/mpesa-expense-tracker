# pages/7_Recurring.py
import streamlit as st
from analytics.recurring import find_recurring

st.title("🔁 Recurring Payments")
st.caption("Transactions that repeat roughly monthly with similar amounts.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

rec_df = find_recurring(df)
if rec_df.empty:
    st.info("No recurring patterns detected.")
else:
    st.dataframe(
        rec_df, use_container_width=True, hide_index=True,
        column_config={
            "avg_amount": st.column_config.NumberColumn("Avg KES", format="%.2f"),
            "total_paid": st.column_config.NumberColumn("Total KES", format="%.2f"),
            "avg_gap_days": st.column_config.NumberColumn("Every (days)", format="%.0f"),
            "next_expected": st.column_config.DateColumn("Next expected", format="YYYY-MM-DD"),
        },
    )
    st.metric(
        "Estimated monthly commitments",
        f"{rec_df['avg_amount'].sum():,.0f} KES",
    )
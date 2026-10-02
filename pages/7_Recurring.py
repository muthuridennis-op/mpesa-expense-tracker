# pages/7_Recurring.py
import streamlit as st

from analytics.recurring import find_recurring
from ui_helpers import get_df, show_df

st.title("🔁 Recurring Payments")
st.caption("Repeating monthly payments, grouped with fuzzy matching. Always uses your full history.")

df = get_df(use_filter=False)  # a month filter would leave nothing to detect
rec = find_recurring(df)

if rec.empty:
    st.info("No recurring patterns detected (needs 3+ payments roughly a month apart).")
    st.stop()

show_ended = st.checkbox("Also show ended / inactive series", value=False)
view = rec if show_ended else rec[rec["active"]]

if view.empty:
    st.info("No active recurring payments. Tick the box above to see ended ones.")
else:
    show_df(
        view.drop(columns=["receipts"]),
        column_config={
            "avg_amount": st.column_config.NumberColumn("Avg KES", format="%.2f"),
            "amount_cv": st.column_config.NumberColumn("Amount variance", format="%.2f"),
            "total_paid": st.column_config.NumberColumn("Total KES", format="%.2f"),
            "avg_gap_days": st.column_config.NumberColumn("Every (days)", format="%.0f"),
            "last_paid": st.column_config.DateColumn("Last paid", format="YYYY-MM-DD"),
            "next_expected": st.column_config.DateColumn("Next expected", format="YYYY-MM-DD"),
        },
    )

active = rec[rec["active"]]
st.metric("Estimated monthly commitments (active)", f"{active['avg_amount'].sum():,.0f} KES")
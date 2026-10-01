# pages/6_Anomalies.py
import streamlit as st
from analytics.anomalies import find_anomalies

st.title("🚨 Anomalies")
st.caption("Transactions flagged as unusually large for their category.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

anom_df = find_anomalies(df)
if anom_df.empty:
    st.success("✅ No unusual transactions detected.")
else:
    st.warning(f"⚠️ {len(anom_df)} unusual transactions detected")
    st.dataframe(
        anom_df, use_container_width=True, hide_index=True,
        column_config={
            "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            "category_mean": st.column_config.NumberColumn("Category avg", format="%.2f"),
            "z_score": st.column_config.NumberColumn("Z-score", format="%.2f"),
        },
    )
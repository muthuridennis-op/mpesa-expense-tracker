# pages/6_Anomalies.py
import streamlit as st
from analytics.anomalies import find_anomalies

st.title("🚨 Anomalies")
st.caption("Unusually large transactions within each category (IQR method).")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

multiplier = st.slider("Sensitivity (lower = more sensitive)", 1.0, 4.0, 2.0, 0.5)
anom_df = find_anomalies(df, iqr_multiplier=multiplier)

if anom_df.empty:
    st.success("✅ No unusual transactions detected at this sensitivity.")
else:
    st.warning(f"⚠️ {len(anom_df)} unusual transactions detected")
    st.dataframe(
        anom_df, use_container_width=True, hide_index=True,
        column_config={
            "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            "category_q3": st.column_config.NumberColumn("Category Q3", format="%.2f"),
            "category_iqr": st.column_config.NumberColumn("IQR", format="%.2f"),
            "multiple_of_iqr": st.column_config.NumberColumn("IQR multiples", format="%.2f"),
        },
    )
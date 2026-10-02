# pages/6_Anomalies.py
import streamlit as st

from analytics.anomalies import find_anomalies
from ui_helpers import get_df, show_df

st.title("🚨 Anomalies")
st.caption("Unusually large expenses within each category (IQR method). Internal movements are excluded.")

df = get_df()
multiplier = st.slider("Sensitivity (lower = more sensitive)", 1.0, 4.0, 2.0, 0.5)
anom = find_anomalies(df, iqr_multiplier=multiplier)

if anom.empty:
    st.success("✅ No unusual transactions detected at this sensitivity.")
else:
    st.warning(f"⚠️ {len(anom)} unusual transactions detected")
    show_df(
        anom,
        column_config={
            "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            "category_q3": st.column_config.NumberColumn("Category Q3", format="%.2f"),
            "category_iqr": st.column_config.NumberColumn("IQR", format="%.2f"),
            "multiple_of_iqr": st.column_config.NumberColumn("IQR multiples", format="%.2f"),
        },
    )
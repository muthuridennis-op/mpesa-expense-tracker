# app.py
"""M-Pesa & Bank Statement Expense Tracker — entrypoint."""
import io
from datetime import datetime

import streamlit as st
import pandas as pd

from parsers.mpesa import extract_text_from_pdf, parse_mpesa_text
from analytics.metrics import filter_by_month

st.set_page_config(
    page_title="Expense Tracker",
    page_icon="💰",
    layout="wide",
)

# ------------------------------------------------------------------
# Sidebar: upload, password, month filter
# ------------------------------------------------------------------
with st.sidebar:
    st.header("📄 Upload Statement")
    uploaded_file = st.file_uploader("PDF statement", type=["pdf"])
    password = st.text_input("PDF password (if required)", type="password")

    st.divider()
    st.header("⚙️ Settings")
    month_filter = st.selectbox(
        "Filter by month",
        ["All", "This month", "Last month", "Last 3 months"],
    )
    st.divider()
    st.caption("M-Pesa statements are usually 6 months long.")


# ------------------------------------------------------------------
# Parse & cache into session_state
# ------------------------------------------------------------------
if uploaded_file is not None:
    if st.session_state.get("last_file") != uploaded_file.name:
        try:
            text = extract_text_from_pdf(uploaded_file.read(), password or None)
        except Exception as e:
            st.error(f"Could not open PDF: {e}")
            st.stop()

        df = parse_mpesa_text(text)
        if df.empty:
            st.warning(
                "No transactions detected. Check the password, or the PDF "
                "layout may differ from the standard M-Pesa format."
            )
            with st.expander("🔍 Show raw extracted text (first 2000 chars)"):
                st.text(text[:2000])
            st.stop()

        st.session_state["df"] = df
        st.session_state["last_file"] = uploaded_file.name


# ------------------------------------------------------------------
# Load, filter, store working df
# ------------------------------------------------------------------
raw_df = st.session_state.get("df")
if raw_df is None or raw_df.empty:
    st.info("👈 Upload a PDF statement from the sidebar to get started.")
    st.stop()

working_df = filter_by_month(raw_df, month_filter)
st.session_state["working_df"] = working_df


# ------------------------------------------------------------------
# Navigation
# ------------------------------------------------------------------
pages = [
    st.Page("pages/1_Overview.py", title="Overview", icon="📈", default=True),
    st.Page("pages/2_Categories.py", title="Categories", icon="🥧"),
    st.Page("pages/3_Top_Spenders.py", title="Top Spenders", icon="🏆"),
    st.Page("pages/4_Explorer.py", title="Explorer", icon="🔍"),
    st.Page("pages/5_Heatmap.py", title="Heatmap", icon="🗓️"),
    st.Page("pages/6_Anomalies.py", title="Anomalies", icon="🚨"),
    st.Page("pages/7_Recurring.py", title="Recurring", icon="🔁"),
    st.Page("pages/8_Compare.py", title="Compare", icon="📊"),
    st.Page("pages/9_Budgets.py", title="Budgets", icon="🎯"),
    st.Page("pages/10_Sankey.py", title="Money Flow", icon="🌊"),
    st.Page("pages/11_Report.py", title="Report", icon="📄"),
]

pg = st.navigation(pages)
pg.run()
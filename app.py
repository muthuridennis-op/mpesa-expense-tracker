# app.py
"""M-Pesa & Bank Statement Expense Tracker — entrypoint with auth."""
import io
from datetime import datetime

import streamlit as st
import pandas as pd

from parsers.mpesa import extract_text_from_pdf, parse_mpesa_text
from analytics.metrics import filter_by_month
from db import (
    get_client, sign_in, sign_out, current_user,
    save_transactions, load_transactions,
)

st.set_page_config(
    page_title="Expense Tracker",
    page_icon="💰",
    layout="wide",
)

# ------------------------------------------------------------------
# Mobile viewport + small-screen tweaks
# ------------------------------------------------------------------
st.markdown(
    """
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <style>
        @media (max-width: 640px) {
            .stDataFrame { font-size: 12px !important; }
            .stMetric label { font-size: 11px !important; }
            .stMetric div[data-testid="stMetricValue"] { font-size: 18px !important; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# Authentication gate
# ------------------------------------------------------------------
if current_user() is None:
    st.title("🔒 M-Pesa Expense Tracker")
    st.caption("Sign in to access your data. Press Enter after your password.")

    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")

    # Submit button (primary path)
    clicked = st.button("Sign in", use_container_width=True, type="primary")

    # Enter-to-submit:
    # Streamlit reruns when you press Enter in a text_input.
    # We debounce with a session key so we don't re-attempt on every rerun.
    submitted_by_enter = False
    if email and password:
        last = st.session_state.get("_last_login_attempt", ("", ""))
        if (email, password) != last:
            st.session_state["_last_login_attempt"] = (email, password)
            submitted_by_enter = True

    if clicked or submitted_by_enter:
        if not email or not password:
            st.warning("Please enter both email and password.")
        else:
            ok, msg = sign_in(email, password)
            if ok:
                st.session_state.pop("_last_login_attempt", None)
                st.rerun()
            else:
                st.error(f"Login failed: {msg}")

    st.stop()

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.header("📄 Upload Statement")
    uploaded_files = st.file_uploader(
        "PDF statement(s)",
        type=["pdf"],
        accept_multiple_files=True,
    )
    pdf_password = st.text_input(
        "PDF password (if required)",
        type="password",
        key="pdf_password",
        help="The code Safaricom emailed you. Press Enter to apply.",
    )

    st.divider()
    st.header("⚙️ Settings")
    month_filter = st.selectbox(
        "Filter by month",
        ["All", "This month", "Last month", "Last 3 months"],
    )
    compact = st.toggle("📱 Compact mode", value=False)
    st.session_state["compact"] = compact

    st.divider()
    user = current_user()
    if user:
        st.caption(f"Signed in as **{user['email']}**")
        if st.button("Log out", use_container_width=True):
            sign_out()
            st.rerun()

    st.divider()
    st.caption("M-Pesa statements are usually 6 months long.")

# ------------------------------------------------------------------
# Parse & save
# Signature now includes the PDF password, so pressing Enter
# in the password field re-triggers parsing.
# ------------------------------------------------------------------
if uploaded_files:
    signature = (
        ",".join(sorted(f.name for f in uploaded_files))
        + f"|{pdf_password or ''}"
    )

    if st.session_state.get("last_file") != signature:
        all_dfs = []
        failed = []
        for f in uploaded_files:
            try:
                # Rewind the file pointer in case it was read before
                f.seek(0)
                text = extract_text_from_pdf(f.read(), pdf_password or None)
                part = parse_mpesa_text(text)
                if part.empty:
                    failed.append(f.name)
                else:
                    all_dfs.append(part)
            except Exception as e:
                failed.append(f"{f.name}: {e}")

        if not all_dfs:
            st.error(
                "No transactions parsed from any uploaded PDF. "
                "Check the password, or the file may be a scanned image."
            )
            if failed:
                with st.expander("Failed files"):
                    for f in failed:
                        st.write(f"- {f}")
            st.stop()

        merged = pd.concat(all_dfs, ignore_index=True)
        merged = merged.drop_duplicates(subset=["receipt"], keep="first")
        merged = merged.sort_values("date").reset_index(drop=True)

        n = save_transactions(merged, source="mpesa")
        if n:
            st.success(f"Saved {n} transactions to the database.")

        st.session_state["df"] = load_transactions()
        st.session_state["last_file"] = signature

        if failed:
            st.warning(f"Skipped {len(failed)} file(s): {', '.join(failed)}")

# ------------------------------------------------------------------
# Load from database
# ------------------------------------------------------------------
if "df" not in st.session_state:
    st.session_state["df"] = load_transactions()

raw_df = st.session_state["df"]
if raw_df is None or raw_df.empty:
    st.info(
        "👈 Upload a PDF statement to get started. "
        "Transactions are saved automatically."
    )
    st.stop()

working_df = filter_by_month(raw_df, month_filter)
st.session_state["working_df"] = working_df

# ------------------------------------------------------------------
# Navigation
# ------------------------------------------------------------------
pages = [
    st.Page("pages/1_Overview.py", title="Overview", icon="📈", default=True),
    st.Page("pages/2_Categories.py", title="Categories", icon="🥧"),
    st.Page("pages/12_Payees.py", title="Payees", icon="👥"),
    st.Page("pages/3_Top_Spenders.py", title="Top Spenders", icon="🏆"),
    st.Page("pages/4_Explorer.py", title="Explorer", icon="🔍"),
    st.Page("pages/5_Heatmap.py", title="Heatmap", icon="🗓️"),
    st.Page("pages/6_Anomalies.py", title="Anomalies", icon="🚨"),
    st.Page("pages/7_Recurring.py", title="Recurring", icon="🔁"),
    st.Page("pages/14_Forecast.py", title="Forecast", icon="🔮"),
    st.Page("pages/8_Compare.py", title="Compare", icon="📊"),
    st.Page("pages/9_Budgets.py", title="Budgets", icon="🎯"),
    st.Page("pages/10_Sankey.py", title="Money Flow", icon="🌊"),
    st.Page("pages/11_Report.py", title="Report", icon="📄"),
    st.Page("pages/13_Settings.py", title="Settings", icon="⚙️"),
]

pg = st.navigation(pages)
pg.run()
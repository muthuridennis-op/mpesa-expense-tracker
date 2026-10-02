# app.py
"""M-Pesa Expense Tracker: entrypoint (auth, upload -> parse -> save -> load, navigation)."""
import hashlib
import time

import pandas as pd
import streamlit as st

from analytics.common import enrich
from analytics.metrics import filter_by_month
from db import (
    current_user, load_rules, load_transactions, save_transactions,
    sign_in, sign_out,
)
from parsers.mpesa import extract_text_from_pdf, parse_statement
from ui_helpers import show_flash, sk

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="wide")

# Small-screen tweaks (a <meta viewport> tag cannot be injected from st.markdown).
st.markdown(
    """
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
MAX_FAILS, LOCK_SECONDS = 5, 60

if current_user() is None or not st.session_state.get("access_token"):
    st.title("🔒 M-Pesa Expense Tracker")

    msg = st.session_state.pop("_auth_msg", None)
    if msg:
        st.warning(msg)

    locked_for = max(0, int(st.session_state.get("_locked_until", 0) - time.time()))
    if locked_for:
        st.error(f"Too many failed attempts. Try again in {locked_for}s.")

    # st.form gives native Enter-to-submit; no manual debouncing needed.
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(
            "Sign in", type="primary", disabled=locked_for > 0, **sk("form_submit_button")
        )

    if submitted:
        email = email.strip()
        if not email or not password:
            st.warning("Please enter both email and password.")
        else:
            ok, message = sign_in(email, password)
            if ok:
                st.session_state.pop("_login_fails", None)
                st.rerun()
            fails = st.session_state.get("_login_fails", 0) + 1
            st.session_state["_login_fails"] = fails
            if fails >= MAX_FAILS:
                st.session_state["_locked_until"] = time.time() + LOCK_SECONDS
                st.session_state["_login_fails"] = 0
            st.error(f"Login failed: {message}")
    st.stop()

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.header("📄 Upload Statement")
    uploaded_files = st.file_uploader("PDF statement(s)", type=["pdf"], accept_multiple_files=True)
    pdf_password = st.text_input(
        "PDF password (if required)", type="password", key="pdf_password",
        help="The code Safaricom emailed you. Press Enter to apply.",
    )
    overwrite = st.checkbox(
        "Overwrite existing rows",
        value=False,
        help="Off: rows already saved (and any edits you made) are kept. "
             "On: re-parsed data replaces them. Turn on once after a parser upgrade.",
    )

    st.divider()
    st.header("⚙️ Settings")
    month_filter = st.selectbox(
        "Filter by month",
        ["All", "This month", "Last month", "Last 3 months"],
        key="month_filter",
        help="Last 3 months = this month plus the two before it. "
             "Recurring, Forecast, Compare and Budgets always use all history.",
    )
    st.toggle("📱 Compact mode", value=False, key="compact")

    st.divider()
    user = current_user()
    if user:
        st.caption(f"Signed in as **{user['email']}**")
        if st.button("Log out", **sk("button")):
            sign_out()
            st.rerun()
    st.divider()
    st.caption("M-Pesa statements are usually 6 months long.")

# ------------------------------------------------------------------
# Parse & save (re-runs only when the files' CONTENT, password or mode change)
# ------------------------------------------------------------------
if uploaded_files:
    blobs = sorted(((f.name, f.getvalue()) for f in uploaded_files), key=lambda x: x[0])
    signature = "|".join(hashlib.sha256(b).hexdigest() for _, b in blobs)
    signature += "|" + hashlib.sha256((pdf_password or "").encode()).hexdigest()[:12]
    signature += f"|{overwrite}"

    if st.session_state.get("last_file") != signature:
        reports, frames = [], []
        for name, data in blobs:
            try:
                text = extract_text_from_pdf(data, pdf_password or None)
                result = parse_statement(text)
                if result.df.empty:
                    reports.append({"file": name, "ok": False,
                                    "error": "No transactions found (wrong password, or a scanned image?)"})
                else:
                    frames.append(result.df)
                    reports.append({"file": name, "ok": True, "rows": len(result.df),
                                    "reconciliation": result.reconciliation})
            except Exception as e:
                reports.append({"file": name, "ok": False, "error": str(e)})

        if frames:
            merged = (
                pd.concat(frames, ignore_index=True)
                .drop_duplicates(subset=["receipt"], keep="first")
                .sort_values(["date", "time"], kind="stable")
                .reset_index(drop=True)
            )
            written = save_transactions(merged, source="mpesa", overwrite=overwrite)
            already = len(merged) - written if not overwrite else 0
            st.session_state["df"] = load_transactions()
            st.session_state["upload_summary"] = (
                f"Parsed {len(merged)} transactions: "
                + (f"{written} replaced/written." if overwrite else f"{written} new, {already} already saved.")
            )
        else:
            st.session_state.pop("upload_summary", None)

        st.session_state["parse_reports"] = reports
        st.session_state["last_file"] = signature  # also on failure, so we don't loop

# ------------------------------------------------------------------
# Upload report (stays visible across reruns; a failed parse never hides your data)
# ------------------------------------------------------------------
reports = st.session_state.get("parse_reports")
if reports:
    with st.sidebar:
        with st.expander("🧾 Last upload report", expanded=any(not r["ok"] for r in reports)):
            if st.session_state.get("upload_summary"):
                st.success(st.session_state["upload_summary"])
            for r in reports:
                if not r["ok"]:
                    st.error(f"**{r['file']}**: {r['error']}")
                    continue
                rec = r["reconciliation"]
                if rec["ok"] is None:
                    st.info(f"**{r['file']}**: {r['rows']} rows. No balance column to verify.")
                elif rec["ok"]:
                    st.success(f"**{r['file']}**: {r['rows']} rows. Balance reconciled "
                               f"({rec['checked']} checks) ✅")
                else:
                    st.warning(f"**{r['file']}**: {r['rows']} rows, but "
                               f"{rec['mismatches']} of {rec['checked']} balance checks failed. "
                               "Totals may be off; see examples below.")
                    st.dataframe(pd.DataFrame(rec["examples"]), hide_index=True)

# ------------------------------------------------------------------
# Load from database, enrich, filter
# ------------------------------------------------------------------
if "df" not in st.session_state:
    st.session_state["df"] = load_transactions()
if current_user() is None:  # the session expired during a load
    st.rerun()

raw_df = st.session_state["df"]
if raw_df is None or raw_df.empty:
    show_flash()
    st.info("👈 Upload a PDF statement to get started. Transactions are saved automatically.")
    st.stop()

if "rules" not in st.session_state:
    st.session_state["rules"] = load_rules()

full_df = enrich(raw_df, st.session_state["rules"])
st.session_state["full_df"] = full_df
st.session_state["working_df"] = filter_by_month(full_df, month_filter)

# ------------------------------------------------------------------
# Navigation
# ------------------------------------------------------------------
pages = [
    st.Page("pages/1_Overview.py", title="Overview", icon="📈", default=True),
    st.Page("pages/2_Categories.py", title="Categories", icon="🥧"),
    st.Page("pages/15_Rules.py", title="Category Rules", icon="🏷️"),
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
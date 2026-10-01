# app.py
"""
M-Pesa & Bank Statement Expense Tracker
Parses multi-line M-Pesa statements (2-3 lines per transaction).
"""
import io
import re
from datetime import datetime
from collections import defaultdict

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pdfplumber

st.set_page_config(
    page_title="Expense Tracker",
    page_icon="💰",
    layout="wide",
)

st.title("💰 M-Pesa & Bank Expense Tracker")
st.caption("Upload a PDF statement to analyze your spending, income, and savings.")


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
with st.sidebar:
    st.header("📄 Upload Statement")
    uploaded_file = st.file_uploader(
        "PDF statement",
        type=["pdf"],
        help="M-Pesa statements are password-protected. Bank statements usually are not.",
    )
    password = st.text_input(
        "PDF password (if required)",
        type="password",
    )

    st.divider()
    st.header("⚙️ Settings")
    month_filter = st.selectbox(
        "Filter by month",
        ["All", "This month", "Last month", "Last 3 months"],
    )

    st.divider()
    st.caption("Tip: M-Pesa statements are usually 6 months long.")


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------
# Matches the START of a transaction row:
#   UJ19M8OFOU 2026-10-01 08:07:56 OverDraft of Credit Party Completed 50.00 0.00
# Capture groups:
#   1. Receipt No.
#   2. Date (YYYY-MM-DD)
#   3. Time (HH:MM:SS)
#   4. Details (may continue on following lines)
#   5. Transaction Status (Completed / Failed / Pending)
#   6. Amount 1 (Paid In OR Withdrawn — sign tells which)
#   7. Amount 2 (Balance, optional)
TX_START = re.compile(
    r"^([A-Z0-9]{10})\s+"                 # receipt
    r"(\d{4}-\d{2}-\d{2})\s+"              # date
    r"(\d{2}:\d{2}:\d{2})\s+"              # time
    r"(.+?)\s+"                            # details (greedy up to status)
    r"(Completed|Failed|Pending)\s+"       # status
    r"(-?[\d,]+\.\d{2})"                   # amount
    r"(?:\s+(-?[\d,]+\.\d{2}))?"           # optional balance
)

# Continuation line: starts with "-" or is a short description fragment
CONTINUATION_HINT = re.compile(r"^[\-\u2013]")


def extract_text_from_pdf(file_bytes: bytes, password: str | None) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes), password=password) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def parse_mpesa_text(text: str) -> pd.DataFrame:
    """
    Parse multi-line M-Pesa statement text into a tidy DataFrame.

    Strategy:
    - Scan line-by-line.
    - When a line matches TX_START, begin a new transaction record.
    - Lines that follow and don't match TX_START are appended to the
      previous transaction's description (continuation lines).
    - All raw rows are collected (including overDraft/charge rows), then
      grouped by receipt number so each logical transaction appears once.
    """
    lines = text.splitlines()
    raw_rows = []
    current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        m = TX_START.match(stripped)
        if m:
            # Flush previous
            if current:
                raw_rows.append(current)

            receipt, date_str, time_str, details, status, amount_str, balance_str = m.groups()
            try:
                amount = float(amount_str.replace(",", ""))
            except ValueError:
                amount = None

            current = {
                "receipt": receipt,
                "date": date_str,
                "time": time_str,
                "details": details.strip(),
                "status": status,
                "amount": amount,
                "balance": float(balance_str.replace(",", "")) if balance_str else None,
            }
        else:
            # Continuation of previous transaction's description
            if current:
                current["details"] += " " + stripped
            # else: ignore stray lines (page headers, etc.)

    if current:
        raw_rows.append(current)

    if not raw_rows:
        return pd.DataFrame()

    raw_df = pd.DataFrame(raw_rows)

    # Clean up details: collapse whitespace, strip trailing " to -" artifacts
    raw_df["details"] = raw_df["details"].str.replace(r"\s+", " ", regex=True).str.strip()

    # Convert date, drop rows with unparseable amounts
    raw_df["date"] = pd.to_datetime(raw_df["date"], errors="coerce")
    raw_df = raw_df.dropna(subset=["date", "amount"])

    # Filter: keep only Completed (drop Failed/Pending unless you want them)
    raw_df = raw_df[raw_df["status"] == "Completed"].copy()

    # Classify transaction type from details
    raw_df["type"] = raw_df["details"].apply(classify_type)

    # Drop the internal Fuliza/OverDraft mirror rows — they're noise:
    #   "OverDraft of Credit Party"  → the credit injection side of a Fuliza tx
    #   "OD Loan Repayment to 232323" → repayment of Fuliza (real expense, keep!)
    # We drop only the "OverDraft of Credit Party" rows.
    raw_df = raw_df[raw_df["type"] != "Fuliza OverDraft"].copy()

    # Group by receipt: aggregate charges + main transaction into one row
    grouped = group_by_receipt(raw_df)

    return grouped.sort_values("date").reset_index(drop=True)


def classify_type(details: str) -> str:
    """Return a transaction category/type based on the details string."""
    d = details.lower()

    if "overdraft of credit party" in d:
        return "Fuliza OverDraft"
    if "od loan repayment" in d:
        return "Fuliza Repayment"
    if "pay bill charge" in d:
        return "Paybill Charge"
    if "customer transfer of funds charge" in d:
        return "Transfer Charge"
    if "withdrawal charge" in d or "withdraw charge" in d:
        return "Withdrawal Charge"
    if "bundle purchase" in d:
        return "Data/Airtime"
    if "airtime" in d:
        return "Data/Airtime"
    if "pay bill" in d or "paybill" in d:
        return "Paybill"
    if "buy goods" in d or "merchant payment" in d:
        return "Merchant"
    if "customer transfer" in d or "transfer to" in d or "transfer from" in d:
        return "Transfer"
    if "funds received" in d or "received from" in d:
        return "Received"
    if "agent deposit" in d or "deposit" in d:
        return "Deposit"
    if "agent withdrawal" in d or "withdrawal" in d or "withdraw" in d:
        return "Withdrawal"
    if "m-shwari" in d or "mshwari" in d:
        return "M-Shwari"
    return "Other"


def group_by_receipt(df: pd.DataFrame) -> pd.DataFrame:
    """
    Combine rows that share a receipt number.

    A single M-Pesa transaction can appear as:
      - The main transaction (e.g. "Pay Bill ... -200.00")
      - A separate "Pay Bill Charge" row (-5.00)
      - A mirror "OverDraft of Credit Party" row (already dropped)

    We aggregate:
      - sum of negative amounts → expenses
      - sum of positive amounts → income
      - concatenate distinct types
      - keep date, time, first receipt
    """
    out = []
    for receipt, group in df.groupby("receipt", sort=False):
        # Merge details strings
        details = " | ".join(sorted(set(group["details"].tolist())))
        types = sorted(set(group["type"].tolist()))
        status = group["status"].iloc[0]
        date = group["date"].iloc[0]
        time = group["time"].iloc[0]
        amounts = group["amount"].tolist()

        # The "main" transaction is the one with the largest absolute amount
        main_idx = max(range(len(amounts)), key=lambda i: abs(amounts[i]))
        main_amount = amounts[main_idx]
        main_type = group["type"].iloc[main_idx]

        # Charges: sum all other amounts
        charge_total = sum(a for i, a in enumerate(amounts) if i != main_idx)

        out.append({
            "receipt": receipt,
            "date": date,
            "time": time,
            "details": details,
            "amount": main_amount,
            "charge": charge_total,
            "net_amount": main_amount + charge_total,
            "type": main_type,
            "status": status,
        })

    result = pd.DataFrame(out)
    result["direction"] = result["net_amount"].apply(
        lambda x: "Income" if x > 0 else "Expense"
    )
    return result


def filter_by_month(df: pd.DataFrame, choice: str) -> pd.DataFrame:
    if df.empty or choice == "All":
        return df
    today = pd.Timestamp.today().normalize()
    if choice == "This month":
        start = today.replace(day=1)
    elif choice == "Last month":
        first_this = today.replace(day=1)
        start = (first_this - pd.Timedelta(days=1)).replace(day=1)
    elif choice == "Last 3 months":
        start = today - pd.Timedelta(days=90)
    else:
        return df
    return df[df["date"] >= start]


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
if uploaded_file is None:
    st.info("👈 Upload a PDF statement from the sidebar to get started.")
    st.stop()

file_bytes = uploaded_file.read()

try:
    text = extract_text_from_pdf(file_bytes, password or None)
except Exception as e:
    st.error(f"Could not open PDF: {e}")
    st.stop()

df = parse_mpesa_text(text)

if df.empty:
    st.warning(
        "No transactions were detected. This can happen if:\n"
        "- The PDF password was wrong\n"
        "- The statement layout differs from the standard format\n"
        "- The PDF is a scanned image rather than text-based"
    )
    with st.expander("🔍 Show raw extracted text (first 3000 chars)"):
        st.text(text[:3000])
    st.stop()

df = filter_by_month(df, month_filter)

# Use net_amount (main + charge) for income/expense totals
income = df[df["net_amount"] > 0]["net_amount"].sum()
expenses = df[df["net_amount"] < 0]["net_amount"].sum()
net = income + expenses
savings_rate = (net / income * 100) if income > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Income (KES)", f"{income:,.0f}")
col2.metric("Expenses (KES)", f"{abs(expenses):,.0f}")
col3.metric("Net Savings (KES)", f"{net:,.0f}")
col4.metric("Savings Rate", f"{savings_rate:.1f}%")

st.divider()

# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------
tab_overview, tab_categories, tab_top, tab_data = st.tabs(
    ["📈 Overview", "🥧 Categories", "🏆 Top Spenders", "📋 All Transactions"]
)


with tab_overview:
    st.subheader("Daily Cash Flow")
    daily = df.groupby("date")["net_amount"].sum().reset_index().sort_values("date")
    daily["cumulative"] = daily["net_amount"].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["net_amount"],
        name="Daily net",
        marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in daily["net_amount"]],
    ))
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["cumulative"],
        name="Cumulative", mode="lines+markers",
        line=dict(color="#1f77b4", width=2),
        yaxis="y2",
    ))
    fig.update_layout(
        template="plotly_dark",
        height=400,
        yaxis=dict(title="Daily Net (KES)"),
        yaxis2=dict(title="Cumulative (KES)", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)


with tab_categories:
    st.subheader("Spending by Category")
    expense_df = df[df["net_amount"] < 0].copy()
    expense_df["abs_amount"] = expense_df["net_amount"].abs()

    if expense_df.empty:
        st.info("No expenses in this period.")
    else:
        cat = (
            expense_df.groupby("type")["abs_amount"]
            .sum().sort_values(ascending=False).reset_index()
        )
        fig = px.pie(cat, values="abs_amount", names="type", hole=0.4,
                     title="Expense Breakdown")
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            cat.sort_values("abs_amount"),
            x="abs_amount", y="type", orientation="h",
            title="Category Totals (KES)",
            color="abs_amount", color_continuous_scale="Reds",
        )
        fig2.update_layout(template="plotly_dark", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)


with tab_top:
    st.subheader("Top Spenders")
    expense_df = df[df["net_amount"] < 0].copy()
    expense_df["abs_amount"] = expense_df["net_amount"].abs()

    if expense_df.empty:
        st.info("No expenses in this period.")
    else:
        st.markdown("**Largest individual transactions**")
        top_txns = (
            expense_df.nlargest(10, "abs_amount")
            [["date", "details", "type", "abs_amount"]]
            .rename(columns={"abs_amount": "amount_kes"})
        )
        st.dataframe(top_txns, use_container_width=True, hide_index=True)

        st.markdown("**Top payees (aggregated by description)**")
        by_payee = (
            expense_df.groupby("details")["abs_amount"]
            .sum().sort_values(ascending=False).head(10).reset_index()
        )
        fig = px.bar(
            by_payee.sort_values("abs_amount"),
            x="abs_amount", y="details", orientation="h",
            title="Where your money went",
        )
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)


with tab_data:
    st.subheader("All Transactions")
    st.dataframe(
        df[["date", "time", "details", "type", "net_amount", "direction", "status"]],
        use_container_width=True,
        hide_index=True,
    )
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download as CSV",
        csv,
        file_name="mpesa_transactions.csv",
        mime="text/csv",
    )


st.divider()
st.caption("Expense Tracker • Built with Streamlit • Not financial advice")
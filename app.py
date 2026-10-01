# app.py
"""
M-Pesa & Bank Statement Expense Tracker
Upload a PDF statement, extract transactions, and visualize spending.
"""
import io
import re
from datetime import datetime

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
# Sidebar: upload + password + settings
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
        help="For M-Pesa: the code Safaricom emailed you when you requested the statement.",
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
# Parsing helpers
# ------------------------------------------------------------------
# Matches a line like:
#   QGH7XXXXXX Completed 12/5/24 14:23 Paid to JOHN DOE -100.00 0.00
# Or:
#   QGH7XXXXXX Completed 12/5/24 Paid to JOHN DOE -100.00
MPESA_PATTERN = re.compile(
    r"([A-Z0-9]{10})\s+"            # receipt number
    r"(Completed|Failed|Pending)\s+" # status
    r"(\d{1,2}/\d{1,2}/\d{2,4})\s+"  # date
    r"(\d{1,2}:\d{2}(?::\d{2})?)?\s*"  # optional time
    r"(.+?)\s+"                      # description
    r"(-?[\d,]+\.\d{2})\s*"          # amount
    r"(-?[\d,]+\.\d{2})?"            # optional balance
)


def extract_text_from_pdf(file_bytes: bytes, password: str | None) -> str:
    """Return the full concatenated text of a PDF."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes), password=password) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def parse_mpesa_text(text: str) -> pd.DataFrame:
    """Parse M-Pesa statement text into a tidy DataFrame."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = MPESA_PATTERN.search(line)
        if not m:
            continue

        receipt, status, date_str, time_str, description, amount_str, balance_str = m.groups()

        # Parse date (handle 2-digit and 4-digit years)
        for fmt in ("%d/%m/%y", "%d/%m/%Y"):
            try:
                txn_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                txn_date = None
        if not txn_date:
            continue

        # Parse amount
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            continue

        # Categorize the description
        category = categorize(description, amount)

        rows.append({
            "receipt": receipt,
            "status": status,
            "date": txn_date,
            "time": time_str or "",
            "description": description.strip(),
            "amount": amount,
            "category": category,
            "type": "Income" if amount > 0 else "Expense",
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
    return df


def categorize(description: str, amount: float) -> str:
    """Very simple rule-based categorizer. Extend as needed."""
    desc = description.lower()
    if amount > 0:
        return "Income"
    if "pay bill" in desc or "paybill" in desc:
        return "Paybill"
    if "buy goods" in desc:
        return "Merchant"
    if "withdraw" in desc:
        return "Withdrawal"
    if "m-shwari" in desc or "mshwari" in desc:
        return "M-Shwari"
    if "fuliza" in desc:
        return "Fuliza"
    if "airtime" in desc:
        return "Airtime"
    if "paid to" in desc:
        return "Transfer to Person"
    if "received from" in desc:
        return "Received from Person"
    return "Other"


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
    return df[df["date"] >= start.date()]


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
        "- The PDF password was wrong (try again)\n"
        "- The statement layout differs from the standard M-Pesa format\n"
        "- The PDF is a scanned image rather than text-based"
    )
    with st.expander("🔍 Show raw extracted text (for debugging)"):
        st.text(text[:3000])
    st.stop()

df = filter_by_month(df, month_filter)

# ------------------------------------------------------------------
# Top-level metrics
# ------------------------------------------------------------------
income = df[df["amount"] > 0]["amount"].sum()
expenses = df[df["amount"] < 0]["amount"].sum()
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
    daily = (
        df.groupby("date")["amount"]
        .sum()
        .reset_index()
        .sort_values("date")
    )
    daily["cumulative"] = daily["amount"].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["amount"],
        name="Daily net", marker_color=[
            "#2ca02c" if v >= 0 else "#d62728" for v in daily["amount"]
        ],
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
    expense_df = df[df["amount"] < 0].copy()
    expense_df["abs_amount"] = expense_df["amount"].abs()

    if expense_df.empty:
        st.info("No expenses in this period.")
    else:
        cat = (
            expense_df.groupby("category")["abs_amount"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        fig = px.pie(
            cat, values="abs_amount", names="category",
            hole=0.4, title="Expense Breakdown",
        )
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            cat.sort_values("abs_amount"),
            x="abs_amount", y="category", orientation="h",
            title="Category Totals (KES)",
            color="abs_amount", color_continuous_scale="Reds",
        )
        fig2.update_layout(template="plotly_dark", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)


with tab_top:
    st.subheader("Top Spenders")
    expense_df = df[df["amount"] < 0].copy()
    expense_df["abs_amount"] = expense_df["amount"].abs()

    if expense_df.empty:
        st.info("No expenses in this period.")
    else:
        # Top individual transactions
        st.markdown("**Largest individual transactions**")
        top_txns = (
            expense_df.nlargest(10, "abs_amount")
            [["date", "description", "category", "abs_amount"]]
            .rename(columns={"abs_amount": "amount_kes"})
        )
        st.dataframe(top_txns, use_container_width=True, hide_index=True)

        # Top payees (aggregated by description)
        st.markdown("**Top payees (aggregated)**")
        by_payee = (
            expense_df.groupby("description")["abs_amount"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
        )
        fig = px.bar(
            by_payee.sort_values("abs_amount"),
            x="abs_amount", y="description", orientation="h",
            title="Where your money went",
        )
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)


with tab_data:
    st.subheader("All Transactions")
    st.dataframe(
        df[["date", "time", "description", "category", "amount", "type", "status"]],
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
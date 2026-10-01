# pages/11_Report.py
import streamlit as st

st.title("📄 Download Report")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

income = float(df[df["net_amount"] > 0]["net_amount"].sum())
expenses = float(df[df["net_amount"] < 0]["net_amount"].sum())
net = income + expenses
savings_rate = (net / income * 100) if income > 0 else 0.0

top_txns_html = df.nlargest(20, "net_amount").to_html(index=False) if not df.empty else ""

html_report = f"""
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, sans-serif; padding: 24px; color: #222; }}
h1 {{ color: #2ca02c; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; }}
th {{ background: #f4f4f4; }}
</style></head><body>
<h1>M-Pesa Expense Report</h1>
<p><strong>Period:</strong> {df['date'].min().date()} to {df['date'].max().date()}</p>
<h2>Summary</h2>
<ul>
  <li>Income: {income:,.2f} KES</li>
  <li>Expenses: {abs(expenses):,.2f} KES</li>
  <li>Net: {net:,.2f} KES</li>
  <li>Savings rate: {savings_rate:.1f}%</li>
</ul>
<h2>Top 20 Transactions</h2>
{top_txns_html}
</body></html>
"""

st.download_button(
    "⬇️ Download HTML report",
    html_report.encode("utf-8"),
    file_name="mpesa_report.html",
    mime="text/html",
)

st.divider()
st.subheader("CSV export")
st.download_button(
    "⬇️ Download all transactions (CSV)",
    df.to_csv(index=False).encode("utf-8"),
    file_name="mpesa_all_transactions.csv",
    mime="text/csv",
)
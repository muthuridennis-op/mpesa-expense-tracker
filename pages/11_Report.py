# pages/11_Report.py
import html

import streamlit as st

from analytics.common import spending
from analytics.metrics import compute_summary
from ui_helpers import get_df

st.title("📄 Download Report")

df = get_df()
s = compute_summary(df)
exp = spending(df)

EXPORT_COLS = ["date", "time", "receipt", "details", "payee_clean", "type", "category",
               "amount", "charge", "net_amount", "balance", "direction", "is_internal"]
export_cols = [c for c in EXPORT_COLS if c in df.columns]  # never leak id / user_id / created_at


def table_html(frame, float_cols=()):
    return frame.to_html(
        index=False, escape=True,
        formatters={c: (lambda x: f"{x:,.2f}") for c in float_cols},
    )


top = exp.nlargest(20, "abs_amount")[["date", "details", "payee_clean", "category", "abs_amount"]].copy()
top["date"] = top["date"].dt.strftime("%Y-%m-%d")
top = top.rename(columns={"payee_clean": "payee", "abs_amount": "amount_kes"})

by_cat = (
    exp.groupby("category")["abs_amount"].sum().sort_values(ascending=False).reset_index()
    .rename(columns={"abs_amount": "total_kes"})
) if not exp.empty else exp

period = f"{df['date'].min().date()} to {df['date'].max().date()}"
html_report = f"""<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, sans-serif; padding: 24px; color: #222; }}
h1 {{ color: #2ca02c; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 20px; }}
th, td {{ border: 1px solid #ccc; padding: 6px; text-align: left; }}
th {{ background: #f4f4f4; }}
</style></head><body>
<h1>M-Pesa Expense Report</h1>
<p><strong>Period:</strong> {html.escape(period)}</p>
<p style="color:#666">Internal movements (Fuliza repayments, M-Shwari, items marked Internal) are excluded.</p>
<h2>Summary</h2>
<ul>
  <li>Income: {s['income']:,.2f} KES</li>
  <li>Expenses: {abs(s['expenses']):,.2f} KES (of which fees: {s['fees']:,.2f})</li>
  <li>Net: {s['net']:,.2f} KES</li>
  <li>Savings rate: {s['savings_rate']:.1f}%</li>
</ul>
<h2>Spending by category</h2>
{table_html(by_cat, ['total_kes']) if not exp.empty else '<p>No expenses.</p>'}
<h2>Top 20 expenses</h2>
{table_html(top, ['amount_kes']) if not exp.empty else '<p>No expenses.</p>'}
</body></html>"""

st.download_button("⬇️ Download HTML report", html_report.encode("utf-8"),
                   file_name="mpesa_report.html", mime="text/html")

st.divider()
st.subheader("CSV export")
st.download_button("⬇️ Download transactions (CSV)", df[export_cols].to_csv(index=False).encode("utf-8"),
                   file_name="mpesa_transactions.csv", mime="text/csv")
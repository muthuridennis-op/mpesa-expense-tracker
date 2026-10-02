# pages/1_Overview.py
import plotly.graph_objects as go
import streamlit as st

from analytics.common import real_flows
from analytics.metrics import compute_summary
from ui_helpers import get_df, is_compact, metric_row, show_chart

st.title("📈 Overview")

df = get_df()
s = compute_summary(df)

metric_row([
    ("Income (KES)", f"{s['income']:,.0f}"),
    ("Expenses (KES)", f"{abs(s['expenses']):,.0f}"),
    ("Net Savings (KES)", f"{s['net']:,.0f}"),
    ("Savings Rate", f"{s['savings_rate']:.1f}%"),
    ("Fees paid (KES)", f"{s['fees']:,.0f}"),
])
if s["internal_count"]:
    st.caption(
        f"Excludes {s['internal_count']} internal movements "
        f"({s['internal_out']:,.0f} out / {s['internal_in']:,.0f} in): Fuliza repayments, "
        "M-Shwari, and anything you categorised as Internal."
    )

st.divider()
st.subheader("Daily Cash Flow")

flows = real_flows(df)
daily = flows.groupby("date")["net_amount"].sum().reset_index().sort_values("date")
daily["cumulative"] = daily["net_amount"].cumsum()

fig = go.Figure()
fig.add_trace(go.Bar(
    x=daily["date"], y=daily["net_amount"], name="Daily net",
    marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in daily["net_amount"]],
))
fig.add_trace(go.Scatter(
    x=daily["date"], y=daily["cumulative"], name="Cumulative net",
    mode="lines+markers", line=dict(color="#1f77b4", width=2), yaxis="y2",
))
fig.update_layout(
    height=300 if is_compact() else 450,
    yaxis=dict(title="Daily Net (KES)"),
    yaxis2=dict(title="Cumulative net (KES)", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.1),
)
show_chart(fig)
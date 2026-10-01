# pages/1_Overview.py
import streamlit as st
import plotly.graph_objects as go
from analytics.metrics import compute_summary
from ui_helpers import is_compact, metric_row

st.title("📈 Overview")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data. Upload a statement from the sidebar.")
    st.stop()

summary = compute_summary(df)

metric_row([
    ("Income (KES)", f"{summary['income']:,.0f}"),
    ("Expenses (KES)", f"{abs(summary['expenses']):,.0f}"),
    ("Net Savings (KES)", f"{summary['net']:,.0f}"),
    ("Savings Rate", f"{summary['savings_rate']:.1f}%"),
])

st.divider()

st.subheader("Daily Cash Flow")
daily = df.groupby("date")["net_amount"].sum().reset_index().sort_values("date")
daily["cumulative"] = daily["net_amount"].cumsum()

fig = go.Figure()
fig.add_trace(go.Bar(
    x=daily["date"], y=daily["net_amount"], name="Daily net",
    marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in daily["net_amount"]],
))
fig.add_trace(go.Scatter(
    x=daily["date"], y=daily["cumulative"], name="Cumulative",
    mode="lines+markers", line=dict(color="#1f77b4", width=2), yaxis="y2",
))
fig.update_layout(
    template="plotly_dark",
    height=300 if is_compact() else 450,
    yaxis=dict(title="Daily Net (KES)"),
    yaxis2=dict(title="Cumulative (KES)", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)
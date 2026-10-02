# pages/14_Forecast.py
import plotly.graph_objects as go
import streamlit as st

from analytics.forecast import build_forecast
from ui_helpers import get_df, is_compact, show_chart, show_df

st.title("🔮 Forecast")
st.caption("Next month = active recurring payments + average variable spend over recent complete months.")

df = get_df(use_filter=False)  # forecasting needs history, not the sidebar filter
fc = build_forecast(df)
if fc is None:
    st.info("No expenses to forecast.")
    st.stop()

if fc["note"]:
    st.warning(fc["note"])

st.subheader(f"Forecast for {fc['forecast_month']}")
c1, c2, c3 = st.columns(3)
c1.metric("Recurring commitments", f"{fc['recurring_total']:,.0f} KES")
c2.metric(f"Variable spend (avg of {len(fc['months_used'])} month(s))", f"{fc['variable_total']:,.0f} KES")
c3.metric("Total forecast", f"{fc['forecast_total']:,.0f} KES")
st.caption(f"Months averaged: {', '.join(fc['months_used'])}. Partial months are left out.")

st.divider()
st.subheader("Forecast by category")
by_cat = fc["by_category"]
fig = go.Figure()
fig.add_trace(go.Bar(x=by_cat.index, y=by_cat["Recurring"], name="Recurring", marker_color="#1f77b4"))
fig.add_trace(go.Bar(x=by_cat.index, y=by_cat["Variable"], name="Variable", marker_color="#ff7f0e"))
fig.update_layout(barmode="stack", height=350 if is_compact() else 450,
                  xaxis_title="Category", yaxis_title="Forecast (KES)")
show_chart(fig)
show_df(by_cat.round(0).reset_index().rename(columns={"index": "category"}))

if not fc["recurring"].empty:
    with st.expander("Recurring payments included"):
        show_df(fc["recurring"].drop(columns=["receipts"])[
            ["cluster", "category", "avg_amount", "last_paid", "next_expected"]])

st.divider()
st.subheader("Historical vs forecast")
m = fc["monthly"]
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=m["month"], y=m["abs_amount"], mode="lines+markers",
                          name="Historical", line=dict(color="#1f77b4")))
p = m[m["partial"]]
if not p.empty:
    fig2.add_trace(go.Scatter(x=p["month"], y=p["abs_amount"], mode="markers", name="Partial month",
                              marker=dict(color="rgba(0,0,0,0)", size=12, line=dict(color="#d62728", width=2))))
fig2.add_trace(go.Scatter(x=[fc["forecast_month"]], y=[fc["forecast_total"]], mode="markers", name="Forecast",
                          marker=dict(color="#ff7f0e", size=14, symbol="diamond")))
fig2.update_layout(height=350 if is_compact() else 450, xaxis_title="Month", yaxis_title="Spend (KES)")
show_chart(fig2)
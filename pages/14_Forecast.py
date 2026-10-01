# pages/14_Forecast.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from analytics.recurring import find_recurring
from ui_helpers import is_compact

st.title("🔮 Forecast")
st.caption("Predicted expenses for the next month based on your history.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

expenses = df[df["net_amount"] < 0].copy()
if expenses.empty:
    st.info("No expenses to forecast.")
    st.stop()

expenses["abs_amount"] = expenses["net_amount"].abs()
expenses["month_str"] = expenses["date"].dt.strftime("%Y-%m")

# --- Component 1: Recurring commitments ---
recurring = find_recurring(df)
recurring_total = recurring["avg_amount"].sum() if not recurring.empty else 0.0

# --- Component 2: Variable spend estimate ---
last_3 = sorted(expenses["month_str"].unique())[-3:]
recent = expenses[expenses["month_str"].isin(last_3)]

recurring_receipts = set()
if not recurring.empty:
    for cluster in recurring["cluster"].tolist():
        matches = expenses[
            expenses["payee"].fillna("").str.contains(cluster.split()[0], case=False, na=False)
        ]
        recurring_receipts.update(matches["receipt"].tolist())

variable_recent = recent[~recent["receipt"].isin(recurring_receipts)]
variable_monthly = variable_recent.groupby("month_str")["abs_amount"].sum()
variable_avg = variable_monthly.mean() if not variable_monthly.empty else 0.0

forecast_total = recurring_total + variable_avg

# --- Display ---
st.subheader("Next month's forecast")
col1, col2, col3 = st.columns(3)
col1.metric("Recurring commitments", f"{recurring_total:,.0f} KES")
col2.metric("Variable spend (avg of last 3 months)", f"{variable_avg:,.0f} KES")
col3.metric("Total forecast", f"{forecast_total:,.0f} KES")

st.divider()

# --- Breakdown by category ---
st.subheader("Forecast by category")

cat_recurring = (
    recurring.groupby("cluster")["avg_amount"].sum().rename("recurring")
    if not recurring.empty else pd.Series(dtype=float)
)

variable_by_cat = (
    variable_recent.groupby("type")["abs_amount"].sum() / max(len(variable_monthly), 1)
)

forecast_cat = pd.DataFrame({
    "Recurring": cat_recurring,
    "Variable": variable_by_cat,
}).fillna(0)
forecast_cat["Total"] = forecast_cat["Recurring"] + forecast_cat["Variable"]
forecast_cat = forecast_cat.sort_values("Total", ascending=False)

fig = go.Figure()
fig.add_trace(go.Bar(
    x=forecast_cat.index, y=forecast_cat["Recurring"],
    name="Recurring", marker_color="#1f77b4",
))
fig.add_trace(go.Bar(
    x=forecast_cat.index, y=forecast_cat["Variable"],
    name="Variable", marker_color="#ff7f0e",
))
fig.update_layout(
    template="plotly_dark",
    barmode="stack",
    height=350 if is_compact() else 450,
    xaxis_title="Category",
    yaxis_title="Forecast (KES)",
)
st.plotly_chart(fig, use_container_width=True)

st.dataframe(forecast_cat.round(0), use_container_width=True)

st.divider()

# --- Trend chart: last 6 months + forecast ---
st.subheader("Historical vs forecast")

monthly = expenses.groupby("month_str")["abs_amount"].sum().reset_index()
monthly = monthly.sort_values("month_str")

next_month = (pd.Timestamp.today().replace(day=1) + pd.DateOffset(months=1)).strftime("%Y-%m")

fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=monthly["month_str"], y=monthly["abs_amount"],
    mode="lines+markers", name="Historical",
    line=dict(color="#1f77b4"),
))
fig2.add_trace(go.Scatter(
    x=[next_month], y=[forecast_total],
    mode="markers", name="Forecast",
    marker=dict(color="#ff7f0e", size=14, symbol="diamond"),
))
fig2.update_layout(
    template="plotly_dark",
    height=350 if is_compact() else 450,
    xaxis_title="Month",
    yaxis_title="Spend (KES)",
)
st.plotly_chart(fig2, use_container_width=True)
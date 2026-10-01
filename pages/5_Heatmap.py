# pages/5_Heatmap.py
import streamlit as st
import plotly.express as px
from ui_helpers import is_compact

st.title("🗓️ Spending Heatmap")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

daily = df[df["net_amount"] < 0].copy()
if daily.empty:
    st.info("No expenses.")
    st.stop()

daily["abs_amount"] = daily["net_amount"].abs()
daily["dow"] = daily["date"].dt.dayofweek
daily["week"] = daily["date"].dt.isocalendar().week.astype(int)
daily["month"] = daily["date"].dt.strftime("%b %Y")

agg = daily.groupby(["month", "dow", "week"])["abs_amount"].sum().reset_index()

fig = px.density_heatmap(
    agg, x="week", y="dow", z="abs_amount",
    facet_col="month", facet_col_wrap=2 if is_compact() else 3,
    color_continuous_scale="Reds",
    labels={"abs_amount": "Spent (KES)", "week": "Week", "dow": "Day"},
)
fig.update_yaxes(
    tickmode="array", tickvals=[0, 1, 2, 3, 4, 5, 6],
    ticktext=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
)
fig.update_layout(
    template="plotly_dark",
    height=400 if is_compact() else 500,
)
st.plotly_chart(fig, use_container_width=True)
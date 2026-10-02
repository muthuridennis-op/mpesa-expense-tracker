# pages/3_Top_Spenders.py
"""Individual big-ticket items. (Totals per payee live on the Payees page.)"""
import plotly.express as px
import streamlit as st

from analytics.common import spending
from ui_helpers import get_df, is_compact, show_chart, show_df

st.title("🏆 Top Spenders")

df = get_df()
exp = spending(df)
if exp.empty:
    st.info("No expenses.")
    st.stop()

st.subheader("Largest individual transactions")
top = (
    exp.nlargest(15, "abs_amount")[["date", "details", "payee_clean", "category", "abs_amount"]]
    .rename(columns={"abs_amount": "amount_kes", "payee_clean": "payee"})
)
show_df(top)

st.divider()
st.subheader("Biggest spending days")
by_day = (
    exp.groupby(exp["date"].dt.normalize())["abs_amount"].agg(total="sum", transactions="count")
    .sort_values("total", ascending=False).head(10).reset_index()
)
fig = px.bar(by_day.sort_values("total"), x="total", y=by_day.sort_values("total")["date"].dt.strftime("%Y-%m-%d"),
             orientation="h", hover_data=["transactions"], labels={"total": "KES", "y": "Day"})
fig.update_layout(height=350 if is_compact() else 450, yaxis_title="")
show_chart(fig)
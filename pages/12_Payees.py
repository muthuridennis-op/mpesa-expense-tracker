# pages/12_Payees.py
import streamlit as st
import plotly.express as px
from ui_helpers import is_compact

st.title("👥 Payees")
st.caption("Who you paid, ranked by total amount.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

expense_df = df[(df["net_amount"] < 0) & (df["payee"] != "")].copy()
if expense_df.empty:
    st.info("No payee data extracted from this statement.")
    st.stop()

expense_df["abs_amount"] = expense_df["net_amount"].abs()

top_payees = (
    expense_df.groupby("payee")
    .agg(total=("abs_amount", "sum"), count=("abs_amount", "count"))
    .sort_values("total", ascending=False)
    .head(30)
    .reset_index()
)

c1, c2 = st.columns(2)
c1.metric("Unique payees", expense_df["payee"].nunique())
c2.metric("Total to top 30", f"{top_payees['total'].sum():,.0f} KES")

fig = px.bar(
    top_payees.sort_values("total"),
    x="total", y="payee", orientation="h",
    color="count", color_continuous_scale="Blues",
    labels={"total": "Total (KES)", "count": "Transactions"},
)
fig.update_layout(
    template="plotly_dark",
    height=400 if is_compact() else max(400, 25 * len(top_payees)),
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Full payee breakdown")
st.dataframe(top_payees, use_container_width=True, hide_index=True)
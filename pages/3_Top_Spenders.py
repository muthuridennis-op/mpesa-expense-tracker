# pages/3_Top_Spenders.py
import streamlit as st
import plotly.express as px

st.title("🏆 Top Spenders")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

expense_df = df[df["net_amount"] < 0].copy()
if expense_df.empty:
    st.info("No expenses.")
    st.stop()

expense_df["abs_amount"] = expense_df["net_amount"].abs()

st.subheader("Largest individual transactions")
top_txns = (
    expense_df.nlargest(10, "abs_amount")
    [["date", "details", "type", "abs_amount"]]
    .rename(columns={"abs_amount": "amount_kes"})
)
st.dataframe(top_txns, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Top payees (aggregated)")
by_payee = (
    expense_df.groupby("details")["abs_amount"]
    .sum().sort_values(ascending=False).head(15).reset_index()
)
fig = px.bar(
    by_payee.sort_values("abs_amount"),
    x="abs_amount", y="details", orientation="h",
)
fig.update_layout(template="plotly_dark", height=500)
st.plotly_chart(fig, use_container_width=True)
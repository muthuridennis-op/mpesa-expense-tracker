# pages/2_Categories.py
import streamlit as st
import plotly.express as px

st.title("🥧 Categories")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

expense_df = df[df["net_amount"] < 0].copy()
if expense_df.empty:
    st.info("No expenses in this period.")
    st.stop()

expense_df["abs_amount"] = expense_df["net_amount"].abs()
cat = (
    expense_df.groupby("type")["abs_amount"]
    .sum().sort_values(ascending=False).reset_index()
)

st.subheader("Click a bar to drill into transactions")

fig = px.bar(
    cat, x="type", y="abs_amount",
    color="abs_amount", color_continuous_scale="Reds",
)
fig.update_layout(template="plotly_dark", height=400)
event = st.plotly_chart(fig, use_container_width=True, on_select="rerun")

st.divider()
col1, col2 = st.columns(2)
with col1:
    st.subheader("Expense Breakdown")
    pie = px.pie(cat, values="abs_amount", names="type", hole=0.4)
    pie.update_layout(template="plotly_dark")
    st.plotly_chart(pie, use_container_width=True)
with col2:
    st.subheader("Category Totals")
    st.dataframe(cat, use_container_width=True, hide_index=True)

if event and event.get("selection", {}).get("points"):
    clicked = event["selection"]["points"][0]["x"]
    st.divider()
    st.subheader(f"Transactions in **{clicked}**")
    drill = expense_df[expense_df["type"] == clicked].sort_values("abs_amount", ascending=False)
    st.dataframe(
        drill[["date", "details", "abs_amount"]],
        use_container_width=True, hide_index=True,
    )
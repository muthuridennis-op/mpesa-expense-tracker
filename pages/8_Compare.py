# pages/8_Compare.py
import streamlit as st
import pandas as pd
import plotly.express as px

st.title("📊 Compare Months")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

df = df.copy()
df["month_str"] = df["date"].dt.strftime("%Y-%m")
months = sorted(df["month_str"].unique(), reverse=True)

if len(months) < 2:
    st.info("Need at least two months of data to compare.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    m1 = st.selectbox("Month A", months, index=1, key="cmp_m1")
with c2:
    m2 = st.selectbox("Month B", months, index=0, key="cmp_m2")

a = df[df["month_str"] == m1]
b = df[df["month_str"] == m2]

a_spend = abs(a[a["net_amount"] < 0]["net_amount"].sum())
b_spend = abs(b[b["net_amount"] < 0]["net_amount"].sum())

col1, col2, col3 = st.columns(3)
col1.metric(f"Month A ({m1}) spend", f"{a_spend:,.0f} KES")
col2.metric(f"Month B ({m2}) spend", f"{b_spend:,.0f} KES")
delta = b_spend - a_spend
col3.metric("Difference", f"{delta:,.0f} KES",
            delta=f"{delta:+,.0f}", delta_color="inverse")

a_cat = a[a["net_amount"] < 0].groupby("type")["net_amount"].sum().abs()
b_cat = b[b["net_amount"] < 0].groupby("type")["net_amount"].sum().abs()
compare = pd.DataFrame({"Month A": a_cat, "Month B": b_cat}).fillna(0)
compare["Change"] = compare["Month B"] - compare["Month A"]

fig = px.bar(
    compare.reset_index().melt(id_vars="type", var_name="Month", value_name="Amount"),
    x="type", y="Amount", color="Month", barmode="group",
    title=f"{m1} vs {m2}",
)
fig.update_layout(template="plotly_dark", height=450)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Change by category")
st.dataframe(
    compare.reset_index().sort_values("Change", ascending=False),
    use_container_width=True, hide_index=True,
)
# pages/10_Sankey.py
import streamlit as st
import plotly.graph_objects as go
from ui_helpers import is_compact

st.title("🌊 Money Flow")
st.caption("How income flows into and out of your M-Pesa wallet.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

income_df = df[df["net_amount"] > 0].copy()
expense_df = df[df["net_amount"] < 0].copy()

if income_df.empty and expense_df.empty:
    st.info("No flows to display.")
    st.stop()

expense_df["abs_amount"] = expense_df["net_amount"].abs()


def simplify_income(d: str) -> str:
    d = d.lower()
    if "funds received" in d or "received from" in d:
        return "Received from people"
    if "agent deposit" in d or "deposit" in d:
        return "Agent deposit"
    return "Other income"


income_df["source"] = income_df["details"].apply(simplify_income)

income_groups = income_df.groupby("source")["net_amount"].sum().reset_index()
expense_groups = expense_df.groupby("type")["abs_amount"].sum().reset_index()

labels = ["Wallet"] + income_groups["source"].tolist() + expense_groups["type"].tolist()
idx = {label: i for i, label in enumerate(labels)}

sources, targets, values, colors = [], [], [], []
for _, row in income_groups.iterrows():
    sources.append(idx[row["source"]])
    targets.append(idx["Wallet"])
    values.append(row["net_amount"])
    colors.append("#2ca02c")
for _, row in expense_groups.iterrows():
    sources.append(idx["Wallet"])
    targets.append(idx[row["type"]])
    values.append(row["abs_amount"])
    colors.append("#d62728")

fig = go.Figure(go.Sankey(
    node=dict(label=labels, pad=20, thickness=20, color="#444"),
    link=dict(source=sources, target=targets, value=values, color=colors),
))
fig.update_layout(
    template="plotly_dark",
    height=450 if is_compact() else 600,
    title_text="Income sources → Wallet → Expense categories",
)
st.plotly_chart(fig, use_container_width=True)
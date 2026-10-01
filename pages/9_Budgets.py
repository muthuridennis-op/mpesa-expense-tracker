# pages/9_Budgets.py
import streamlit as st

st.title("🎯 Budgets")
st.caption("Set monthly targets per category. Progress resets each month.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

if "budgets" not in st.session_state:
    st.session_state.budgets = {}

expenses = df[df["net_amount"] < 0].copy()
if expenses.empty:
    st.info("No expenses to budget against.")
    st.stop()

expenses["abs_amount"] = expenses["net_amount"].abs()
expenses["month_str"] = expenses["date"].dt.strftime("%Y-%m")
current_month = sorted(expenses["month_str"].unique())[-1]
st.caption(f"Showing budgets for **{current_month}**")
month_exp = expenses[expenses["month_str"] == current_month]

categories = sorted(expenses["type"].unique())
for cat in categories:
    spent = month_exp[month_exp["type"] == cat]["abs_amount"].sum()
    default_budget = st.session_state.budgets.get(cat, 5000.0)
    budget = st.number_input(
        f"{cat} budget (KES)",
        min_value=0.0, value=float(default_budget), step=500.0,
        key=f"budget_{cat}",
    )
    st.session_state.budgets[cat] = budget

    if budget > 0:
        progress = min(spent / budget, 1.0)
        st.progress(progress, text=f"{spent:,.0f} / {budget:,.0f} KES")
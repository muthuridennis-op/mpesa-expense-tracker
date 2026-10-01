# pages/9_Budgets.py
import streamlit as st
from db import load_budgets, save_budget

st.title("🎯 Budgets")
st.caption("Set a monthly budget per category. Saved to the database.")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

expenses = df[df["net_amount"] < 0].copy()
if expenses.empty:
    st.info("No expenses to budget against.")
    st.stop()

expenses["abs_amount"] = expenses["net_amount"].abs()
expenses["month_str"] = expenses["date"].dt.strftime("%Y-%m")

months = sorted(expenses["month_str"].unique(), reverse=True)
selected_month = st.selectbox("Budget month", months)
month_exp = expenses[expenses["month_str"] == selected_month]

saved = load_budgets(selected_month)

st.divider()

categories = sorted(expenses["type"].unique())
for cat in categories:
    spent = month_exp[month_exp["type"] == cat]["abs_amount"].sum()
    current = saved.get(cat, 0.0)

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**{cat}** — spent {spent:,.0f} KES")
        if current > 0:
            progress = min(spent / current, 1.0)
            st.progress(progress, text=f"{spent:,.0f} / {current:,.0f} KES")
    with col2:
        new_budget = st.number_input(
            "Budget (KES)",
            min_value=0.0,
            value=float(current),
            step=500.0,
            key=f"budget_{selected_month}_{cat}",
            label_visibility="collapsed",
        )
        if new_budget != current:
            if save_budget(cat, selected_month, new_budget):
                st.toast(f"Saved {cat} budget")

st.divider()
total_budget = sum(load_budgets(selected_month).values())
total_spent = month_exp["abs_amount"].sum()
st.metric("Total budget", f"{total_budget:,.0f} KES")
st.metric("Total spent", f"{total_spent:,.0f} KES")
st.metric("Remaining", f"{total_budget - total_spent:,.0f} KES")
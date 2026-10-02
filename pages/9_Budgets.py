# pages/9_Budgets.py
import streamlit as st

from analytics.common import partial_months, spending
from db import load_budgets, save_budget
from ui_helpers import flash, get_df, metric_row, show_flash, sk

st.title("🎯 Budgets")
st.caption("Set a monthly budget per category. Internal movements are not counted as spending.")
show_flash()

df = get_df(use_filter=False)  # budgets are per month; the sidebar filter must not hide months
exp = spending(df)
if exp.empty:
    st.info("No expenses to budget against.")
    st.stop()

months = sorted(exp["month"].unique(), reverse=True)
selected = st.selectbox("Budget month", months)
if selected in partial_months(df):
    st.caption("⚠️ This month is only partly covered by your statements.")

month_exp = exp[exp["month"] == selected]
saved = load_budgets(selected)
spent_by_cat = month_exp.groupby("category")["abs_amount"].sum()

# every category with spend or a saved budget, biggest spend first
cats = sorted(set(spent_by_cat.index) | set(saved), key=lambda c: -float(spent_by_cat.get(c, 0.0)))

st.divider()
with st.form(f"budgets_{selected}"):
    new_values = {}
    for cat in cats:
        spent = float(spent_by_cat.get(cat, 0.0))
        current = float(saved.get(cat, 0.0))
        left, right = st.columns([3, 1])
        with left:
            st.markdown(f"**{cat}**: spent {spent:,.0f} KES")
            if current > 0:
                ratio = spent / current
                st.progress(min(ratio, 1.0), text=f"{spent:,.0f} / {current:,.0f} KES ({ratio:.0%})")
                if ratio > 1:
                    st.error(f"Over budget by {spent - current:,.0f} KES")
        with right:
            new_values[cat] = st.number_input(
                "Budget (KES)", min_value=0.0, value=current, step=500.0,
                key=f"budget_{selected}_{cat}", label_visibility="collapsed",
            )
    submitted = st.form_submit_button("💾 Save budgets", type="primary", **sk("form_submit_button"))

if submitted:
    changed = {c: v for c, v in new_values.items() if abs(v - float(saved.get(c, 0.0))) > 0.001}
    if not changed:
        st.info("No changes to save.")
    else:
        ok = all(save_budget(c, selected, v) for c, v in changed.items())
        flash(f"Saved {len(changed)} budget(s)." if ok else "Some budgets failed to save.",
              "success" if ok else "warning")
        st.rerun()

st.divider()
budgeted = [c for c in cats if saved.get(c, 0.0) > 0]
total_budget = sum(saved[c] for c in budgeted)
spent_budgeted = sum(float(spent_by_cat.get(c, 0.0)) for c in budgeted)
unbudgeted = float(spent_by_cat.sum()) - spent_budgeted

metric_row([
    ("Total budget", f"{total_budget:,.0f} KES"),
    ("Spent (budgeted categories)", f"{spent_budgeted:,.0f} KES"),
    ("Remaining", f"{total_budget - spent_budgeted:,.0f} KES"),
    ("Spent with no budget", f"{unbudgeted:,.0f} KES"),
])
# pages/15_Rules.py
"""Payee -> category rules. This is what turns 'Paybill/Merchant' into real categories."""
import pandas as pd
import streamlit as st

from analytics.categories import (
    DEFAULT_CATEGORIES, INTERNAL_CATEGORY, STARTER_RULES, UNCATEGORISED,
)
from analytics.common import spending
from db import delete_rules, save_rules
from ui_helpers import flash, get_df, metric_row, show_df, show_flash, sk

st.title("🏷️ Category Rules")
st.caption(
    "A rule says: if the payee or details contain this text, use this category. "
    "Matching ignores case; longer patterns win. Rules apply to all your history instantly."
)
show_flash()

df = get_df(use_filter=False)
rules = st.session_state.get("rules", [])
exp = spending(df)

unc = exp[exp["category"] == UNCATEGORISED] if not exp.empty else exp
share = (unc["abs_amount"].sum() / exp["abs_amount"].sum() * 100) if not exp.empty and exp["abs_amount"].sum() else 0
metric_row([
    ("Rules", str(len(rules))),
    (f"Spending still “{UNCATEGORISED}”", f"{share:.0f}%"),
])

st.info(
    f"**{INTERNAL_CATEGORY}** is special: transactions in that category (your own bank paybill, "
    "transfers between your own numbers) are excluded from income, expenses and savings rate."
)


def _refresh():
    st.session_state.pop("rules", None)  # reloaded by app.py on the next run
    st.rerun()


# ---- Quick-label the biggest uncategorised payees --------------------
st.subheader("Label your biggest unlabeled payees")
top_unc = pd.DataFrame()
if not unc.empty:
    named = unc[unc["payee_clean"] != ""]
    top_unc = (
        named.groupby("payee_clean")["abs_amount"].agg(total="sum", count="count")
        .sort_values("total", ascending=False).head(15).reset_index()
    )
if top_unc.empty:
    st.success("Nothing left to label 🎉")
else:
    show_df(top_unc)

picked = st.selectbox("Pick a payee (optional)", [""] + top_unc.get("payee_clean", pd.Series(dtype=str)).tolist())
existing_cats = sorted({r["category"] for r in rules} | set(DEFAULT_CATEGORIES))
NEW = "➕ New category…"

with st.form("add_rule"):
    pattern = st.text_input("Text to match", value=picked, key=f"pattern_{picked}",
                            help="e.g. 'naivas', 'kplc', or part of a name")
    choice = st.selectbox("Category", existing_cats + [NEW])
    new_cat = st.text_input("New category name (only if you chose ➕)")
    submitted = st.form_submit_button("Save rule", type="primary", **sk("form_submit_button"))
if submitted:
    category = new_cat.strip() if choice == NEW else choice
    if not pattern.strip() or not category:
        st.warning("Enter the text to match and a category.")
    elif save_rules([{"pattern": pattern, "category": category}]):
        flash(f"Saved: “{pattern.strip().lower()}” → {category}")
        _refresh()

# ---- Existing rules ---------------------------------------------------
st.divider()
st.subheader("Your rules")
if rules:
    rules_df = pd.DataFrame(rules).sort_values(["category", "pattern"])
    show_df(rules_df)
    to_delete = st.multiselect("Delete rules", rules_df["pattern"].tolist())
    if st.button("🗑️ Delete selected", disabled=not to_delete, **sk("button")):
        if delete_rules(to_delete):
            flash(f"Deleted {len(to_delete)} rule(s).")
            _refresh()
else:
    st.caption("No rules yet.")

# ---- Starter pack ----------------------------------------------------
st.divider()
with st.expander("Starter rules for common Kenyan merchants"):
    have = {r["pattern"] for r in rules}
    missing = [{"pattern": p, "category": c} for p, c in STARTER_RULES if p not in have]
    show_df(pd.DataFrame(missing) if missing else pd.DataFrame({"info": ["All starter rules already added."]}))
    if st.button("Add starter rules", disabled=not missing, **sk("button")):
        if save_rules(missing):
            flash(f"Added {len(missing)} starter rules.")
            _refresh()
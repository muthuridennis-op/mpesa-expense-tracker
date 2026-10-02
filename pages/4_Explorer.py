# pages/4_Explorer.py
import streamlit as st

from db import delete_transaction, update_transaction
from parsers.mpesa import KNOWN_TYPES
from ui_helpers import cols, flash, get_df, show_df, show_flash, sk

st.title("🔍 Transaction Explorer")
show_flash()

all_df = get_df(use_filter=False)  # editing must find any transaction, whatever the filter

mode = st.radio("Mode", ["View & filter", "Find & edit by receipt"], horizontal=True)

# ============ View & filter ============
if mode == "View & filter":
    df = st.session_state.get("working_df")
    if df is None or df.empty:
        st.info("No transactions for the current month filter.")
        st.stop()

    c1, c2, c3 = cols(3)
    search = c1.text_input("Search description, payee or receipt", "")
    types = sorted(t for t in df["type"].unique() if t)
    type_filter = c2.multiselect("Types (empty = all)", types)
    categories = sorted(df["category"].unique())
    cat_filter = c3.multiselect("Categories (empty = all)", categories)

    d1, d2, d3 = cols(3)
    direction = d1.radio("Direction", ["All", "Income", "Expense"], horizontal=True)
    hide_internal = d2.checkbox("Hide internal movements", value=False)
    lo, hi = float(df["net_amount"].min()), float(df["net_amount"].max())
    if lo < hi:
        amt_range = d3.slider("Amount range (KES)", lo, hi, (lo, hi))
    else:
        amt_range = (lo, hi)

    f = df.copy()
    if search:
        s = search.strip()
        f = f[
            f["details"].str.contains(s, case=False, na=False, regex=False)
            | f["receipt"].str.contains(s, case=False, na=False, regex=False)
            | f["payee"].str.contains(s, case=False, na=False, regex=False)
            | f["payee_clean"].str.contains(s, case=False, na=False, regex=False)
        ]
    if type_filter:
        f = f[f["type"].isin(type_filter)]
    if cat_filter:
        f = f[f["category"].isin(cat_filter)]
    if direction != "All":
        f = f[f["direction"] == direction]
    if hide_internal:
        f = f[~f["is_internal"]]
    f = f[(f["net_amount"] >= amt_range[0]) & (f["net_amount"] <= amt_range[1])]

    st.caption(f"Showing **{len(f)}** of {len(df)} transactions · Total: **{f['net_amount'].sum():,.2f} KES**")

    show_cols = ["date", "time", "details", "payee_clean", "type", "category", "net_amount", "direction", "is_internal"]
    show_df(
        f[show_cols].sort_values("date", ascending=False),
        column_config={
            "net_amount": st.column_config.NumberColumn("Amount (KES)", format="%.2f"),
            "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "payee_clean": "Payee",
        },
    )
    export = f[["date", "time", "receipt", "details", "payee_clean", "type", "category",
                "amount", "charge", "net_amount", "direction", "is_internal"]]
    st.download_button("⬇️ Download filtered transactions", export.to_csv(index=False).encode("utf-8"),
                       file_name="mpesa_filtered.csv", mime="text/csv")

# ============ Find & edit ============
else:
    st.subheader("Find a transaction by receipt number")
    q = st.text_input("Receipt number (or partial)", "").strip().upper()

    if q:
        matches = all_df[all_df["receipt"].str.upper().str.contains(q, na=False, regex=False)]
        if matches.empty:
            st.warning("No transaction found with that receipt.")
            st.stop()

        show_df(matches[["date", "details", "payee", "type", "category", "net_amount"]])
        selected = st.selectbox("Select a receipt to edit", matches["receipt"].tolist())
        row = matches[matches["receipt"] == selected].iloc[0]
        txn_date = str(row["date"].date())

        type_options = list(dict.fromkeys(KNOWN_TYPES + sorted(t for t in all_df["type"].unique() if t)))
        if row["type"] and row["type"] not in type_options:
            type_options.append(row["type"])

        with st.form("edit_txn"):
            st.text_input("Receipt", value=row["receipt"], disabled=True)
            st.text_input("Date", value=txn_date, disabled=True)
            new_payee = st.text_input("Payee", value=row["payee"] or "")
            current_type = row["type"] if row["type"] in type_options else "Other"
            new_type = st.selectbox("Type", type_options, index=type_options.index(current_type))
            new_details = st.text_area("Details", value=row["details"] or "", height=80)
            saved = st.form_submit_button("💾 Save changes", **sk("form_submit_button"))

        if saved:
            # only send fields that actually changed (never silently overwrite the rest)
            updates = {}
            if new_payee != (row["payee"] or ""):
                updates["payee"] = new_payee
            if new_type != row["type"]:
                updates["txn_type"] = new_type
            if new_details != (row["details"] or ""):
                updates["details"] = new_details
            if not updates:
                st.info("Nothing changed.")
            elif update_transaction(row["receipt"], txn_date, updates):
                flash("Saved.")
                st.session_state.pop("df", None)
                st.rerun()

        st.divider()
        st.caption("⚠️ Deleting is permanent.")
        confirm = st.checkbox("I understand this deletes the transaction", key=f"confirm_del_{selected}")
        if st.button("🗑️ Delete this transaction", disabled=not confirm, **sk("button")):
            if delete_transaction(row["receipt"], txn_date):
                flash("Deleted.")
                st.session_state.pop("df", None)
                st.rerun()
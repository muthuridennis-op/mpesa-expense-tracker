# pages/4_Explorer.py
import streamlit as st
from ui_helpers import is_compact
from db import update_transaction, delete_transaction

st.title("🔍 Transaction Explorer")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

mode = st.radio(
    "Mode",
    ["View & filter", "Find & edit by receipt"],
    horizontal=True,
)

# ============ View & filter mode ============
if mode == "View & filter":
    if is_compact():
        search = st.text_input("Search description or receipt", "")
        types = ["All"] + sorted(df["type"].unique().tolist())
        type_filter = st.multiselect("Types", types, default=["All"])
        direction = st.radio("Direction", ["All", "Income", "Expense"], horizontal=True)
        amt_min = float(df["net_amount"].min())
        amt_max = float(df["net_amount"].max())
        amt_range = st.slider("Amount range (KES)", amt_min, amt_max, (amt_min, amt_max))
    else:
        fcol1, fcol2, fcol3, fcol4 = st.columns([2, 2, 2, 2])
        with fcol1:
            search = st.text_input("Search description or receipt", "")
        with fcol2:
            types = ["All"] + sorted(df["type"].unique().tolist())
            type_filter = st.multiselect("Types", types, default=["All"])
        with fcol3:
            direction = st.radio("Direction", ["All", "Income", "Expense"], horizontal=True)
        with fcol4:
            amt_min = float(df["net_amount"].min())
            amt_max = float(df["net_amount"].max())
            amt_range = st.slider("Amount range (KES)", amt_min, amt_max, (amt_min, amt_max))

    filtered = df.copy()
    if search:
        filtered = filtered[
            filtered["details"].str.contains(search, case=False, na=False)
            | filtered["receipt"].str.contains(search, case=False, na=False)
            | filtered["payee"].str.contains(search, case=False, na=False)
        ]
    if type_filter and "All" not in type_filter:
        filtered = filtered[filtered["type"].isin(type_filter)]
    if direction != "All":
        filtered = filtered[filtered["direction"] == direction]
    filtered = filtered[
        (filtered["net_amount"] >= amt_range[0])
        & (filtered["net_amount"] <= amt_range[1])
    ]

    st.caption(
        f"Showing **{len(filtered)}** of {len(df)} transactions · "
        f"Total: **{filtered['net_amount'].sum():,.2f} KES**"
    )

    st.dataframe(
        filtered[["date", "time", "details", "payee", "type", "net_amount", "direction"]]
        .sort_values("date", ascending=False),
        use_container_width=True, hide_index=True,
        column_config={
            "net_amount": st.column_config.NumberColumn("Amount (KES)", format="%.2f"),
            "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        },
    )

    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download filtered transactions",
        csv, file_name="mpesa_filtered.csv", mime="text/csv",
    )

# ============ Find & edit mode ============
else:
    st.subheader("Find a transaction by receipt number")
    search_receipt = st.text_input("Receipt number (or partial)", "").strip().upper()

    if search_receipt:
        matches = df[df["receipt"].str.upper().str.contains(search_receipt, na=False)]
        if matches.empty:
            st.warning("No transaction found with that receipt.")
        else:
            st.dataframe(
                matches[["date", "details", "payee", "type", "net_amount"]],
                use_container_width=True, hide_index=True,
            )

            selected_receipt = st.selectbox(
                "Select a receipt to edit", matches["receipt"].tolist()
            )
            row = matches[matches["receipt"] == selected_receipt].iloc[0]

            with st.form("edit_txn"):
                st.text_input("Receipt", value=row["receipt"], disabled=True)
                st.text_input("Date", value=str(row["date"].date()), disabled=True)
                new_payee = st.text_input("Payee", value=row.get("payee", ""))
                type_options = [
                    "Paybill", "Paybill Charge", "Merchant", "Transfer", "Transfer Charge",
                    "Withdrawal", "Withdrawal Charge", "Deposit", "Received",
                    "Data/Airtime", "M-Shwari", "Fuliza Repayment", "Other",
                ]
                current_type = row["type"] if row["type"] in type_options else "Other"
                new_type = st.selectbox(
                    "Type", type_options,
                    index=type_options.index(current_type),
                )
                new_details = st.text_area("Details", value=row.get("details", ""), height=80)

                saved = st.form_submit_button("💾 Save changes", use_container_width=True)

                if saved:
                    ok = update_transaction(
                        receipt=row["receipt"],
                        txn_date=str(row["date"].date()),
                        updates={
                            "payee": new_payee,
                            "txn_type": new_type,
                            "details": new_details,
                        },
                    )
                    if ok:
                        st.success("Saved. Refresh to see the update.")
                        st.session_state.pop("df", None)
                        st.rerun()
                    else:
                        st.error("Save failed.")

            st.divider()
            st.caption("⚠️ Deleting is permanent.")
            if st.button("🗑️ Delete this transaction", type="secondary"):
                if delete_transaction(row["receipt"], str(row["date"].date())):
                    st.success("Deleted.")
                    st.session_state.pop("df", None)
                    st.rerun()
# pages/4_Explorer.py
import streamlit as st
from ui_helpers import is_compact

st.title("🔍 Transaction Explorer")

df = st.session_state.get("working_df")
if df is None or df.empty:
    st.info("No data.")
    st.stop()

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
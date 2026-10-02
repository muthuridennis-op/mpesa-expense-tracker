# pages/12_Payees.py
import plotly.express as px
import streamlit as st

from analytics.common import spending
from ui_helpers import cols, get_df, is_compact, show_chart, show_df

st.title("👥 Payees")
st.caption("Who you paid, ranked by total. Spelling variants of the same name are merged automatically.")

df = get_df()
exp = spending(df)
exp = exp[exp["payee_clean"] != ""] if not exp.empty else exp
if exp.empty:
    st.info("No payee data extracted for this period.")
    st.stop()

payees = (
    exp.groupby("payee_clean")
    .agg(total=("abs_amount", "sum"), count=("abs_amount", "count"),
         average=("abs_amount", "mean"), last_paid=("date", "max"),
         category=("category", lambda s: s.mode().iloc[0]))
    .sort_values("total", ascending=False)
    .reset_index()
    .rename(columns={"payee_clean": "payee"})
)
top = payees.head(30)

c1, c2 = cols(2)
c1.metric("Unique payees", len(payees))
c2.metric("Total to top 30", f"{top['total'].sum():,.0f} KES")

fig = px.bar(
    top.sort_values("total"), x="total", y="payee", orientation="h",
    color="count", color_continuous_scale="Blues",
    labels={"total": "Total (KES)", "count": "Transactions"},
)
fig.update_layout(height=400 if is_compact() else max(400, 25 * len(top)))
show_chart(fig)

st.subheader(f"All payees ({len(payees)})")
show_df(
    payees,
    column_config={
        "total": st.column_config.NumberColumn("Total KES", format="%.0f"),
        "average": st.column_config.NumberColumn("Average KES", format="%.0f"),
        "last_paid": st.column_config.DateColumn("Last paid", format="YYYY-MM-DD"),
    },
)
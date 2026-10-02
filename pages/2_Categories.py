# pages/2_Categories.py
import plotly.express as px
import streamlit as st

from analytics.categories import UNCATEGORISED
from analytics.common import spending
from ui_helpers import cols, get_df, is_compact, show_chart, show_df

st.title("🥧 Categories")

df = get_df()
exp = spending(df)
if exp.empty:
    st.info("No expenses in this period.")
    st.stop()

cat = (
    exp.groupby("category")["abs_amount"].agg(total="sum", count="count")
    .sort_values("total", ascending=False).reset_index()
)
cat["share_%"] = (cat["total"] / cat["total"].sum() * 100).round(1)

unc = float(cat.loc[cat["category"] == UNCATEGORISED, "total"].sum())
if unc / cat["total"].sum() > 0.25:
    st.info(
        f"{unc / cat['total'].sum():.0%} of spending is still “{UNCATEGORISED}”. "
        "Open **Category Rules** to label your top payees; every chart gets better."
    )

st.subheader("Click a bar to drill into transactions")
fig = px.bar(cat, x="category", y="total", color="total", color_continuous_scale="Reds")
fig.update_layout(height=300 if is_compact() else 400, xaxis_title="", yaxis_title="KES")
event = show_chart(fig, on_select="rerun", key="cat_chart")

st.divider()
left, right = cols(2)
with left:
    st.subheader("Expense Breakdown")
    pie = px.pie(cat, values="total", names="category", hole=0.4)
    show_chart(pie)
with right:
    st.subheader("Category Totals")
    show_df(cat)

points = (event or {}).get("selection", {}).get("points") if event else None
if points:
    clicked = points[0]["x"]
    st.divider()
    st.subheader(f"Transactions in **{clicked}**")
    drill = exp[exp["category"] == clicked].sort_values("abs_amount", ascending=False)
    show_df(drill[["date", "details", "payee_clean", "type", "abs_amount"]])
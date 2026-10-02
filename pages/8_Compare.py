# pages/8_Compare.py
import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.common import partial_months, spending
from ui_helpers import cols, get_df, is_compact, metric_row, show_chart, show_df

st.title("📊 Compare Months")

df = get_df(use_filter=False)  # comparing months needs more than one month of data
exp = spending(df)
months = sorted(exp["month"].unique(), reverse=True) if not exp.empty else []
if len(months) < 2:
    st.info("Need expenses in at least two months to compare.")
    st.stop()

c1, c2 = cols(2)
m1 = c1.selectbox("Month A", months, index=1, key="cmp_m1")
m2 = c2.selectbox("Month B", months, index=0, key="cmp_m2")

partial = partial_months(df)
for m in (m1, m2):
    if m in partial:
        st.warning(f"{m} is only partly covered by your statements, so its total is understated.")

a, b = exp[exp["month"] == m1], exp[exp["month"] == m2]
a_total, b_total = a["abs_amount"].sum(), b["abs_amount"].sum()
metric_row([
    (f"Month A ({m1})", f"{a_total:,.0f} KES"),
    (f"Month B ({m2})", f"{b_total:,.0f} KES"),
    ("Difference", f"{b_total - a_total:+,.0f} KES"),
])

compare = pd.DataFrame({
    "Month A": a.groupby("category")["abs_amount"].sum(),
    "Month B": b.groupby("category")["abs_amount"].sum(),
}).fillna(0)
compare["Change"] = compare["Month B"] - compare["Month A"]
compare.index.name = "category"

fig = px.bar(
    compare.reset_index().melt(id_vars="category", value_vars=["Month A", "Month B"],
                               var_name="Month", value_name="Amount"),
    x="category", y="Amount", color="Month", barmode="group", title=f"{m1} vs {m2}",
)
fig.update_layout(height=350 if is_compact() else 450, xaxis_title="")
show_chart(fig)

st.subheader("Change by category")
show_df(compare.reset_index().sort_values("Change", ascending=False))
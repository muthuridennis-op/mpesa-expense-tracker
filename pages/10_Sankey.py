# pages/10_Sankey.py
import plotly.graph_objects as go
import streamlit as st

from analytics.common import income, spending
from ui_helpers import get_df, is_compact, show_chart

st.title("🌊 Money Flow")
st.caption("Real income → wallet → spending by category. Internal movements are excluded.")

df = get_df()
inc, exp = income(df), spending(df)
if inc.empty and exp.empty:
    st.info("No flows to display.")
    st.stop()

TOP_N = 10


def top_with_other(series, n=TOP_N):
    series = series.sort_values(ascending=False)
    if len(series) <= n:
        return series
    head = series.iloc[:n].copy()
    head["Other"] = series.iloc[n:].sum()
    return head


in_groups = top_with_other(inc.groupby("category")["net_amount"].sum()) if not inc.empty else {}
out_groups = top_with_other(exp.groupby("category")["abs_amount"].sum()) if not exp.empty else {}
total_in, total_out = float(sum(in_groups.values)) if len(in_groups) else 0.0, float(sum(out_groups.values)) if len(out_groups) else 0.0

# unique node keys, so an "Uncategorised" income and expense never collide
labels, index = ["Wallet"], {"wallet": 0}


def node(key, label):
    if key not in index:
        index[key] = len(labels)
        labels.append(label)
    return index[key]


src, tgt, val, col = [], [], [], []
for cat, v in (in_groups.items() if len(in_groups) else []):
    src.append(node(("in", cat), f"{cat} (in)")); tgt.append(0); val.append(float(v)); col.append("rgba(44,160,44,0.4)")
for cat, v in (out_groups.items() if len(out_groups) else []):
    src.append(0); tgt.append(node(("out", cat), cat)); val.append(float(v)); col.append("rgba(214,39,40,0.4)")

# balance the wallet so it does not look leaky
gap = total_in - total_out
if gap > 0:
    src.append(0); tgt.append(node("gap", "Saved / unspent")); val.append(gap); col.append("rgba(31,119,180,0.4)")
elif gap < 0:
    src.append(node("gap", "Drawn from balance")); tgt.append(0); val.append(-gap); col.append("rgba(255,127,14,0.4)")

fig = go.Figure(go.Sankey(
    node=dict(label=labels, pad=20, thickness=20),
    link=dict(source=src, target=tgt, value=val, color=col),
))
fig.update_layout(height=450 if is_compact() else 600, title_text="Income → Wallet → Spending")
show_chart(fig)
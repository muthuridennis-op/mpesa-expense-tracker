# pages/5_Heatmap.py
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analytics.common import spending
from ui_helpers import get_df, is_compact, show_chart

st.title("🗓️ Spending Heatmap")
st.caption("Each cell is one calendar day. Rows are weekdays, columns are 7-day blocks of the month.")

df = get_df()
exp = spending(df)
if exp.empty:
    st.info("No expenses.")
    st.stop()

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
BLOCKS = ["1-7", "8-14", "15-21", "22-28", "29+"]

daily = exp.groupby(exp["date"].dt.normalize())["abs_amount"].sum().reset_index()
daily["month"] = daily["date"].dt.strftime("%Y-%m")      # sortable key
daily["dow"] = daily["date"].dt.dayofweek
daily["block"] = (daily["date"].dt.day - 1) // 7         # 0..4; one date per (block, weekday)

months = sorted(daily["month"].unique())[-12:]
ncols = 2 if is_compact() else 3
nrows = -(-len(months) // ncols)

fig = make_subplots(
    rows=nrows, cols=ncols, subplot_titles=months,
    horizontal_spacing=0.06, vertical_spacing=min(0.15, 0.5 / nrows),
)
for i, m in enumerate(months):
    z = [[None] * 5 for _ in range(7)]
    for _, r in daily[daily["month"] == m].iterrows():
        z[int(r["dow"])][int(r["block"])] = float(r["abs_amount"])
    fig.add_trace(
        go.Heatmap(z=z, x=BLOCKS, y=DOW, coloraxis="coloraxis", hoverongaps=False,
                   xgap=2, ygap=2, hovertemplate="%{y}, days %{x}<br>%{z:,.0f} KES<extra></extra>"),
        row=i // ncols + 1, col=i % ncols + 1,
    )
fig.update_yaxes(autorange="reversed")
fig.update_layout(
    coloraxis=dict(colorscale="Reds", cmin=0, cmax=float(daily["abs_amount"].max()),
                   colorbar=dict(title="KES")),
    height=(260 if is_compact() else 300) * nrows,
)
show_chart(fig)
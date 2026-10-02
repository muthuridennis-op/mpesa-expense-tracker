# ui_helpers.py
"""Small helpers shared by app.py and the pages."""
import inspect
from functools import lru_cache

import streamlit as st


# ------------------------------------------------------------------
# Streamlit version compatibility
# Newer Streamlit replaced use_container_width=True with width="stretch".
# sk("button") returns whichever keyword the installed version understands.
# ------------------------------------------------------------------
@lru_cache(maxsize=None)
def _stretch(name: str) -> tuple:
    try:
        params = inspect.signature(getattr(st, name)).parameters
    except (AttributeError, TypeError, ValueError):
        return (("use_container_width", True),)
    if "use_container_width" in params:
        return (("use_container_width", True),)
    if "width" in params:
        return (("width", "stretch"),)
    return ()


def sk(name: str) -> dict:
    return dict(_stretch(name))


def show_chart(fig, **kwargs):
    return st.plotly_chart(fig, **sk("plotly_chart"), **kwargs)


def show_df(df, **kwargs):
    kwargs.setdefault("hide_index", True)
    return st.dataframe(df, **sk("dataframe"), **kwargs)


# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
def is_compact() -> bool:
    return st.session_state.get("compact", False)


def cols(n: int):
    """n columns on desktop; n stacked containers in compact mode."""
    if is_compact():
        return [st.container() for _ in range(n)]
    return st.columns(n)


def metric_row(metrics: list[tuple[str, str]]):
    """Render a row of metrics that stacks on mobile."""
    for col, (label, value) in zip(cols(len(metrics)), metrics):
        col.metric(label, value)


# ------------------------------------------------------------------
# Data access for pages
# ------------------------------------------------------------------
def get_df(use_filter: bool = True):
    """Enriched data for a page, or stop with a helpful message.

    use_filter=True   -> the sidebar month filter applies (Overview, Categories, ...)
    use_filter=False  -> all history (Recurring, Forecast, Compare, Budgets need this:
                         a "This month" filter would leave them with nothing to analyse)
    """
    key = "working_df" if use_filter else "full_df"
    df = st.session_state.get(key)
    if df is None or df.empty:
        full = st.session_state.get("full_df")
        if use_filter and full is not None and not full.empty:
            st.info(
                f"No transactions for “{st.session_state.get('month_filter', 'this period')}”. "
                "Change the month filter in the sidebar."
            )
        else:
            st.info("No data. Upload a statement from the sidebar.")
        st.stop()
    return df


# ------------------------------------------------------------------
# One-shot messages that survive st.rerun()
# ------------------------------------------------------------------
def flash(message: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("_flash", None)
    if item:
        getattr(st, item[0], st.info)(item[1])
# ui_helpers.py
"""Small helpers for responsive layout."""
import streamlit as st


def is_compact() -> bool:
    return st.session_state.get("compact", False)


def responsive_columns(*specs):
    if is_compact():
        return [st.container() for _ in specs]
    return st.columns(list(specs))


def metric_row(metrics: list[tuple[str, str]]):
    """Render a row of metrics that stacks on mobile."""
    if is_compact():
        for label, value in metrics:
            st.metric(label, value)
    else:
        cols = st.columns(len(metrics))
        for col, (label, value) in zip(cols, metrics):
            col.metric(label, value)
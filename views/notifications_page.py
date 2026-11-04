import streamlit as st

from services import core
import ui


def render(user):
    st.header("Notifications")
    rows = core.notes_of(user["id"])
    c1, c2 = st.columns([4, 1])
    c1.caption(f"{core.unread_count(user['id'])} unread")
    if c2.button("Mark all read", key="mark_read"):
        core.mark_all_seen(user["id"])
        st.rerun()
    ui.notes_list(rows)

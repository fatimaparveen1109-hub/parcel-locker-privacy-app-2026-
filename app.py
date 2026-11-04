"""Privacy Parcel Locker - entry point.  Run locally:  streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Privacy Parcel Locker", layout="wide", initial_sidebar_state="collapsed")

import config
import ui
from db import one
from services import auth, core, housekeeping
from views import landing, info, auth_page, scanner, customer, seller, rider, admin

ui.inject_css()
ss = st.session_state
ss.setdefault("page", "home")
ss.setdefault("role", None)
ss.setdefault("uid", None)

try:
    housekeeping.run_all()
except Exception as e:  # never block the page because of a background job
    st.caption(f"Housekeeping note: {e}")

if "flash" in ss:
    st.toast(ss.pop("flash"))

user = auth.get(ss.uid) if ss.uid else None
if ss.page == "dash" and (not user or user["status"] != "active"):
    ss.update(page="home", uid=None, role=None)
    st.rerun()


def go(page, role=None):
    ss["page"] = page
    if role:
        ss["role"] = role
    st.rerun()


# ---------------- top bar ----------------
if ss.page == "dash":
    c = st.columns([4, 2, 2, 2])
    c[0].markdown('<div class="brand"><i></i>Privacy Parcel Locker</div>', unsafe_allow_html=True)
    c[1].markdown(f"**{user['role']}**: {user['name']}  \n<span class='mu'>{user['id']}</span>", unsafe_allow_html=True)
    n = core.unread_count(user["id"])
    if c[2].button(f"Notifications ({n})", key="bell"):
        ss["_goto"] = "Notifications"
        st.rerun()
    c2 = c[3].columns(2)
    if c2[0].button("Scanner", key="top_scan"):
        go("scanner")
    if c2[1].button("Log out", key="logout"):
        for k in [k for k in ss.keys() if k not in ("page", "role", "uid")]:
            del ss[k]
        ss.update(page="home", uid=None, role=None)
        ss["flash"] = "You are logged out. Choose another role."
        st.rerun()
    # toast for new notifications on the open page
    last = ss.get("last_note", core.max_note_id(user["id"]))
    for note in core.new_notes(user["id"], last)[:3]:
        st.toast(note["body"])
    ss["last_note"] = core.max_note_id(user["id"])
else:
    c = st.columns([5, 1, 1, 1, 1])
    c[0].markdown('<div class="brand"><i></i>Privacy Parcel Locker</div>', unsafe_allow_html=True)
    if c[1].button("Home", key="t_home"):
        go("home")
    if c[2].button("Help", key="t_help"):
        go("info")
    if c[3].button("Scanner", key="t_scan"):
        go("scanner")
    if user:
        if c[4].button("My dashboard", key="t_dash"):
            go("dash")
    elif c[4].button("Sign in", key="t_sign"):
        go("home")
    st.divider()

# ---------------- pages ----------------
if ss.page == "home":
    landing.render()
elif ss.page == "info":
    info.render()
elif ss.page == "scanner":
    if user and st.button("Back to my dashboard", key="back_dash"):
        go("dash")
    scanner.render(user)
elif ss.page == "auth":
    auth_page.render(ss.role)
elif ss.page == "dash":
    {"Customer": customer, "Seller": seller, "Rider": rider, "Admin": admin}[user["role"]].render(user)

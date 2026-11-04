import streamlit as st

import config
from services import auth, core
import ui


def _fill_demo():
    pick = st.session_state.get("demo_pick", "")
    if pick:
        st.session_state["login_email"] = pick
        st.session_state["login_pw"] = config.DEMO_PASSWORD


def render(role):
    if "prefill_email" in st.session_state:
        st.session_state["login_email"] = st.session_state.pop("prefill_email")
    if st.button("Back to home"):
        st.session_state.update(page="home", role=None)
        st.rerun()
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title(f"{role} portal")
        msg = st.session_state.pop("auth_msg", None)
        if msg:
            (st.success if msg[0] else st.error)(msg[1])
        tabs = st.tabs(["Log in"] if role == "Admin" else ["Log in", "Create account"])
        with tabs[0]:
            if config.DEMO_MODE and role in ("Seller", "Rider"):
                demo = auth.demo_accounts(role)
                st.selectbox("Quick demo login", [""] + [d["email"] for d in demo], key="demo_pick", on_change=_fill_demo,
                             format_func=lambda e: "Pick a demo account" if not e else next((f"{d['name']} ({d['id']})" for d in demo if d["email"] == e), e))
            email = st.text_input("Email", key="login_email")
            show = st.checkbox("Show password", key="show_pw")
            pw = st.text_input("Password", type="default" if show else "password", key="login_pw")
            if st.button("Log in", type="primary", key="do_login"):
                u, err = auth.login(role, email, pw)
                if u:
                    st.session_state.update(page="dash", uid=u["id"], role=role, last_note=core.max_note_id(u["id"]))
                    st.rerun()
                else:
                    st.error(err)
            if role == "Admin":
                st.caption("Only one admin account exists. It locks for 15 minutes after 5 wrong attempts.")
            elif role == "Customer":
                st.caption("New here? Create an account first, then log in. Your account is saved, so you can log in again later.")
            else:
                st.caption("A new seller or rider account needs admin approval before you can log in.")
        if role != "Admin":
            with tabs[1]:
                with st.form("signup"):
                    name = st.text_input("Full name")
                    phone = st.text_input("Phone number" + (" (required)" if role == "Customer" else " (optional)"))
                    em = st.text_input("Email")
                    p1 = st.text_input("Password (6+ characters)", type="password")
                    if st.form_submit_button("Create account", type="primary"):
                        uid, err = auth.register(role, name, em, phone, p1)
                        if uid:
                            st.session_state["prefill_email"] = em.strip().lower()
                            if role == "Customer":
                                st.success(f"Account created. Your ID is {uid}. Now open the Log in tab.")
                            else:
                                st.success("Request sent. You can log in after the admin approves it.")
                        else:
                            st.error(err)
        st.caption("Prototype login. Do not use real passwords. Refreshing the browser logs you out, but your account stays saved.")

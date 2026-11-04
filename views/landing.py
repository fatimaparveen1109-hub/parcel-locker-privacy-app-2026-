import streamlit as st
import ui

ROLES = [("Customer", "Shop, pay, track and collect with a one-time QR."),
         ("Seller", "Products, orders, dispatch and earnings."),
         ("Rider", "Tasks, locker choice and deposit."),
         ("Admin", "Orders, money flow, lockers and logins.")]


def render():
    st.markdown(
        '<div class="hero"><div><span class="tag">Private. Secure. Automated.</span>'
        '<h1>Smart delivery. <em>Secure pickup.</em> Complete privacy.</h1>'
        '<p>Your parcel goes to a smart locker near you. Your phone number and home address are never shared with the seller or the rider.</p></div>'
        + ui.hero_img() + '</div>', unsafe_allow_html=True)
    st.markdown("## How it works")
    st.markdown('<div class="steps">'
                '<div class="step" data-n="1"><b>Order</b><span class="mu">Pick products, two hubs and when to pay.</span></div>'
                '<div class="step" data-n="2"><b>Pack</b><span class="mu">The seller accepts and prepares the parcel.</span></div>'
                '<div class="step" data-n="3"><b>Deliver</b><span class="mu">A company rider is assigned and picks a locker.</span></div>'
                '<div class="step" data-n="4"><b>Pay</b><span class="mu">Pay now, or after the parcel is in the locker.</span></div>'
                '<div class="step" data-n="5"><b>Collect</b><span class="mu">Scan your one-time QR to open the locker.</span></div></div>',
                unsafe_allow_html=True)
    st.markdown("## Built around privacy")
    st.markdown('<div class="feat">'
                '<div><b>Private address</b><span class="mu">Only you and the system can see it.</span></div>'
                '<div><b>Two preferred hubs</b><span class="mu">The backup hub is used only if you allow it.</span></div>'
                '<div><b>Live tracking</b><span class="mu">Every status comes from the real order record.</span></div>'
                '<div><b>One-time QR and PIN</b><span class="mu">New for every step. Locked until payment is verified.</span></div>'
                '<div><b>Locker management</b><span class="mu">Right size, one parcel per compartment.</span></div>'
                '<div><b>Returns and support</b><span class="mu">Tickets with status and admin replies.</span></div></div>', unsafe_allow_html=True)
    st.markdown("## Privacy at a glance")
    st.markdown('<div class="feat">'
                '<div><b>Seller sees</b><span class="mu">Items, sizes, your name, destination hub. Never phone or address.</span></div>'
                '<div><b>Rider sees</b><span class="mu">Delivery ID, parcel size, pickup point, hub and locker.</span></div>'
                '<div><b>Admin sees</b><span class="mu">Operations with phone masked, plus a full audit log.</span></div></div>', unsafe_allow_html=True)
    st.markdown("## Choose your role")
    st.caption("Customers sign up freely. Sellers and riders need admin approval.")
    for col, (role, text) in zip(st.columns(4), ROLES):
        with col, st.container(border=True):
            st.subheader(role)
            st.caption(text)
            if st.button(f"Open {role}", key=f"open_{role}"):
                st.session_state.update(page="auth", role=role)
                st.rerun()
    st.divider()
    st.caption("University project. Payments, refunds and QR unlocking are simulated.")

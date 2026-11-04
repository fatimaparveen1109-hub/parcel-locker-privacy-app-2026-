import streamlit as st

PAGES = ["Help", "Return policy", "Privacy policy", "Terms", "Contact"]


def render():
    page = st.radio("Info", PAGES, horizontal=True, key="info_page", label_visibility="collapsed")
    if page == "Help":
        st.header("Help and FAQ")
        faq = {
            "How do I pay?": "Pay when you place the order, or after the parcel is in the locker. Cash on delivery is not available. Payments here are simulated.",
            "What if my first hub is full?": "If you allowed the alternative hub, your parcel goes there and you are notified. If both are full, it waits until a locker is free.",
            "How long do I have to collect my parcel?": "48 hours after the parcel is deposited. You get reminders at 24 and 6 hours. After that your QR expires and the admin reviews the case.",
            "Why do I get several QR codes?": "Every step has its own one-time QR: hub room access first, then the locker QR. Each also has a 6-digit PIN if scanning fails.",
            "How do returns work?": "Request a return within 7 days of collecting. Admin reviews it. If approved, a locker is reserved, you deposit the parcel with a Return QR, a rider collects it, the seller inspects it, and a simulated refund is recorded.",
            "Who gets my money?": "One payment is split into the product price (seller), the delivery fee (rider) and the locker fee (locker operator).",
            "Is my address safe?": "Sellers and riders never see your phone number or home address.",
        }
        for q, a in faq.items():
            with st.expander(q):
                st.write(a)
    elif page == "Return policy":
        st.header("Return and refund policy")
        st.markdown("- Return window: **7 days** after you collect the parcel (Admin can change this).\n"
                    "- Reasons: Damaged, Wrong item, Wrong size, Not as described, Changed my mind.\n"
                    "- A photo is required for the first four reasons.\n"
                    "- Admin reviews every request. If approved, a locker is reserved and you get a Return QR.\n"
                    "- Seller at fault: full simulated refund. Changed my mind: the delivery and locker fees are not refunded.\n"
                    "- The refund is recorded after the seller inspects the returned parcel. No real money moves.")
    elif page == "Privacy policy":
        st.header("Privacy policy")
        st.markdown("- Your phone number and address are stored separately and shown only to you.\n"
                    "- Sellers see your name and the order. Riders see only delivery ID, parcel size, hub and locker.\n"
                    "- Admins see masked contact details. Every sensitive action is written to an audit log.\n"
                    "- QR codes contain no personal data, only an order ID and a random token.\n"
                    "- Passwords are stored as salted hashes. No card details are ever collected.")
    elif page == "Terms":
        st.header("Terms and conditions")
        st.markdown("This is a university prototype. Payments, refunds and locker unlocking are simulated. "
                    "Do not enter real passwords or personal data you want to keep private.")
    else:
        st.header("Contact")
        st.write("For project questions, contact your course team through your university channel.")

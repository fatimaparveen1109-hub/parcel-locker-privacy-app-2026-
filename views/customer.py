import base64
import time
import uuid

import streamlit as st

import config
from db import q, now
from services import auth, catalog, comms, core, orders, returns, qr as qrs
import ui
from views import notifications_page

PAGES = ["Shop", "Cart", "My Orders", "My Locker", "Messages", "Returns", "Complaints", "Notifications", "Profile"]
METHODS = ["Demo Card", "Demo Mobile Wallet", "Demo Bank Transfer", "Demo Wallet Balance"]


def render(user):
    page = ui.nav("Customer", PAGES)
    {"Shop": shop, "Cart": cart, "My Orders": my_orders, "My Locker": my_locker, "Messages": messages, "Returns": returns_page,
     "Complaints": complaints, "Notifications": notifications_page.render, "Profile": profile}[page](user)


# ---------------- shop and cart ----------------
def shop(user):
    st.header("Shop")
    st.caption("Demo catalogue. One order can contain items from one seller.")
    items = catalog.all_active()
    cart_ = st.session_state.setdefault("cart", [])
    for start in range(0, len(items), 4):
        for col, p in zip(st.columns(4), items[start:start + 4]):
            with col, st.container(border=True):
                st.markdown(ui.product_img(p["img"], p["name"]), unsafe_allow_html=True)
                st.markdown(f"**{p['name']}**  \n<span class='mu'>{p['seller_name']}</span>", unsafe_allow_html=True)
                st.markdown(f"**{ui.rs(p['price'])}**  \n<span class='mu'>{p['stock']} in stock</span>", unsafe_allow_html=True)
                sizes = [s for s in (p["sizes"] or "").split(",") if s]
                size = st.selectbox("Size", sizes, key=f"sz_{p['id']}") if sizes else ""
                if st.button("Add to cart", key=f"add_{p['id']}", disabled=p["stock"] < 1):
                    other = {catalog.get(c["product_id"])["seller_id"] for c in cart_}
                    if other and p["seller_id"] not in other:
                        st.error("Your cart has another seller's items. Clear the cart first.")
                    else:
                        for c in cart_:
                            if c["product_id"] == p["id"] and c["size"] == size:
                                if c["qty"] >= p["stock"]:
                                    st.error("No more stock.")
                                    return
                                c["qty"] += 1
                                break
                        else:
                            cart_.append({"product_id": p["id"], "size": size, "qty": 1})
                        ui.flash(f"{p['name']} added to cart.")
                        st.rerun()


def cart(user):
    st.header("Cart and checkout")
    cart_ = st.session_state.setdefault("cart", [])
    if not cart_:
        st.info("Your cart is empty. Add a product from the Shop.")
        return
    sub = 0
    with st.container(border=True):
        st.subheader("Your items")
        for i, c in enumerate(list(cart_)):
            p = catalog.get(c["product_id"])
            sub += p["price"] * c["qty"]
            a, b, d = st.columns([4, 2, 1])
            a.write(f"{p['name']} {('(' + c['size'] + ')') if c['size'] else ''}")
            c["qty"] = b.number_input("Qty", 1, max(1, p["stock"]), min(c["qty"], max(1, p["stock"])), key=f"q_{i}_{c['product_id']}", label_visibility="collapsed")
            if d.button("Remove", key=f"rm_{i}_{c['product_id']}"):
                cart_.pop(i)
                st.rerun()
    priv = auth.private(user["id"])
    with st.container(border=True):
        st.subheader("Step 1: Your details and address")
        st.caption("Private. The seller and the rider never see your phone or address.")
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", user["name"], key="co_name")
        phone = c2.text_input("Phone", priv.get("phone") or "", key="co_phone")
        area = st.selectbox("Area (search or pick)", list(config.AREAS), key="co_area",
                            index=list(config.AREAS).index(priv["area"]) if priv.get("area") in config.AREAS else 0)
        a = config.AREAS[area]
        c3, c4 = st.columns(2)
        block = c3.selectbox("Sector / block", a["blocks"], key=f"co_block_{area}")
        street = c4.text_input("Street", a["street"], key=f"co_street_{area}")
        c5, c6 = st.columns(2)
        house = c5.text_input("House / flat", priv.get("house") or "", key="co_house")
        landmark = c6.text_input("Landmark (optional)", priv.get("landmark") or "", key="co_land")
    hubs = core.hub_names()
    ids = list(hubs)
    near = a["hub"]
    with st.container(border=True):
        st.subheader("Step 2: Locker hubs")
        st.caption(f"Nearest hub to {area}: {hubs.get(near, '-')}")
        c1, c2 = st.columns(2)
        h1 = c1.selectbox("Primary hub", ids, index=ids.index(near) if near in ids else 0, format_func=hubs.get, key=f"co_h1_{area}")
        rest = [x for x in ids if x != h1]
        h2 = c2.selectbox("Alternative hub", rest, format_func=hubs.get, key=f"co_h2_{area}_{h1}")
        allow = st.checkbox("Allow the alternative hub if the primary hub has no space", True, key="co_alt")
    df, lf = core.isetting("delivery_fee"), core.isetting("locker_fee")
    with st.container(border=True):
        st.subheader("Step 3: Charges")
        st.write(f"Product (to seller): **{ui.rs(sub)}**")
        st.write(f"Delivery fee (to rider): **{ui.rs(df)}**")
        st.write(f"Locker fee (to locker operator): **{ui.rs(lf)}**")
        st.markdown(f"### Total {ui.rs(sub + df + lf)}")
    with st.container(border=True):
        st.subheader("Step 4: Payment (simulation)")
        timing = st.radio("When to pay", ["now", "later"], format_func=lambda x: "Pay now" if x == "now" else "Pay after the parcel is in the locker",
                          key="co_timing", horizontal=True)
        method = st.selectbox("Method", METHODS, key="co_method")
        fail = st.checkbox("Simulate a failed payment (to show Retry)", key="co_fail")
        st.caption("Simulation only. No real money. No card details are stored. No cash on delivery.")
        idem = st.session_state.setdefault("idem", uuid.uuid4().hex)
        if st.button("Place order", type="primary", key="co_place"):
            contact = {"name": name, "phone": phone, "area": area, "block": block, "street": street, "house": house, "landmark": landmark}
            oid, err = orders.place_order(user, cart_, contact, h1, h2, allow, timing)
            if err:
                st.error(err)
                return
            auth.save_profile(user["id"], phone, area, block, street, house, landmark)
            msg = f"Order {oid} placed."
            if timing == "now":
                with st.spinner(f"Processing {method} payment..."):
                    time.sleep(1.2)
                    ok, pm = orders.pay(oid, user["id"], method, fail, idem)
                msg += " " + pm
            st.session_state["cart"] = []
            st.session_state.pop("idem", None)
            ui.flash(msg)
            ui.goto("My Orders")


# ---------------- orders ----------------
def pay_box(o, user):
    k = o["id"]
    c1, c2 = st.columns(2)
    method = c1.selectbox("Method", METHODS, key=f"pm_{k}")
    fail = c2.checkbox("Simulate a failed payment", key=f"pf_{k}")
    label = "Retry payment" if o["pay_status"] == "Payment Failed" else f"Pay Now {ui.rs(o['total'])}"
    if st.button(label, type="primary", key=f"pay_{k}"):
        with st.spinner(f"Processing {method} payment..."):
            time.sleep(1.2)
            ok, msg = orders.pay(k, user["id"], method, fail, uuid.uuid4().hex)
        ui.flash(msg)
        st.rerun()
    st.caption("Simulation only. No real card or money.")


def my_orders(user):
    st.header("My orders")
    rows = orders.customer_orders(user["id"])
    if not rows:
        st.info("No orders yet. Go to Shop.")
    for o in rows:
        with st.expander(f"{o['id']}  |  {o['status']}  |  {ui.rs(o['total'])}", expanded=len(rows) == 1):
            st.markdown(f"{ui.sb(o['status'])} {ui.sb(o['pay_status'])}", unsafe_allow_html=True)
            idx = config.STATUS_FLOW.index(o["status"]) if o["status"] in config.STATUS_FLOW else 0
            st.progress(idx / (len(config.STATUS_FLOW) - 1))
            items = core.items_of(o["id"])
            ui.table([{"Item": i["name"], "Size": i["size"] or "-", "Qty": i["qty"], "Price": ui.rs(i["unit_price"]), "Amount": ui.rs(i["unit_price"] * i["qty"])} for i in items])
            st.write(f"Delivery fee {ui.rs(o['delivery_fee'])} | Locker fee {ui.rs(o['locker_fee'])} | **Total {ui.rs(o['total'])}**")
            st.markdown("**Timeline**")
            ui.table([{"Status": e["status"], "Time": ui.fmt(e["ts"]), "By": e["actor"]} for e in q("SELECT * FROM events WHERE order_id=? ORDER BY id", (o["id"],))])
            if o["pay_status"] != "Paid" and o["status"] not in config.DONE:
                pay_box(o, user)
            if o["status"] == "Order Placed" and st.button("Cancel order", key=f"cx_{o['id']}"):
                ok, msg = orders.cancel(o["id"], user["id"])
                ui.flash(msg)
                st.rerun()
            st.download_button("Download receipt", orders.receipt_html(o["id"]), file_name=f"{o['id']}_receipt.html", mime="text/html", key=f"rc_{o['id']}")


def my_locker(user):
    st.header("My locker")
    names = core.hub_names()
    rows = [o for o in orders.customer_orders(user["id"]) if o["status"] in config.IN_LOCKER + ["Expired (Admin Review)"]]
    if not rows:
        st.info("No parcel in a locker yet. You will get a notification when your parcel is deposited.")
    for o in rows:
        with st.container(border=True):
            st.subheader(o["id"])
            st.markdown(f"{ui.sb(o['status'])} {ui.sb(o['pay_status'])}", unsafe_allow_html=True)
            st.write(f"Hub: **{names[o['hub']]}**{' (your alternative hub)' if o['hub'] != o['hub1'] else ''} | Locker **{o['locker']}**")
            if o["status"] == "Expired (Admin Review)":
                st.error("The pickup window ended. Admin will review this parcel.")
                continue
            st.info(f"Time left to collect: **{ui.left_text(o['expires_at'], now())}** (deadline {ui.fmt(o['expires_at'])})")
            if o["pay_status"] != "Paid":
                st.warning("Payment is due. Your pickup QR unlocks only after payment is verified.")
                pay_box(o, user)
                continue
            access = qrs.current(o["id"], "HUB_ACCESS", user["id"])
            pickup = qrs.current(o["id"], "CUSTOMER_PICKUP", user["id"])
            st.caption("Open the Locker scanner (demo device) from the top bar. Scan Step 1, then Step 2.")
            if access and not access["used"] and not access["expired"]:
                ui.show_qr(access, "Step 1: Hub room access QR", f"acc_{o['id']}", "Opens the room door.")
            else:
                ui.show_qr(pickup, "Step 2: Pickup QR", f"pk_{o['id']}", "Opens your locker. Works once.")
            if st.button("I need a new QR", key=f"regen_{o['id']}"):
                qrs.issue(o["id"], "HUB_ACCESS", "Customer", user["id"], o["expires_at"], o["hub"], None)
                qrs.issue(o["id"], "CUSTOMER_PICKUP", "Customer", user["id"], o["expires_at"], o["hub"], o["locker"])
                ui.flash("New QR codes issued. The old ones no longer work.")
                st.rerun()


# ---------------- messages, returns, complaints, profile ----------------
def messages(user):
    st.header("Messages")
    tab1, tab2 = st.tabs(["Seller chat", "Admin support"])
    my = orders.customer_orders(user["id"])
    for tab, channel in ((tab1, "seller"), (tab2, "admin")):
        with tab:
            for m in comms.thread(channel, customer_id=user["id"]):
                st.markdown(f"**{m['sender_role']}** <span class='mu'>{m['order_id'] or 'General'} | {ui.fmt(m['ts'])}</span>  \n{m['body']}", unsafe_allow_html=True)
            with st.form(f"msg_{channel}", clear_on_submit=True):
                oid = ""
                if channel == "seller":
                    oid = st.selectbox("About order", [o["id"] for o in my]) if my else ""
                body = st.text_input("Message")
                if st.form_submit_button("Send"):
                    if channel == "seller" and not oid:
                        st.error("Place an order first to chat with a seller.")
                    else:
                        ok, msg = comms.send(channel, user["id"], oid, "Customer", user["id"], body)
                        st.success(msg) if ok else st.error(msg)
            st.caption("Phone numbers and emails are blocked in chat.")


def returns_page(user):
    st.header("Returns")
    d = core.isetting("return_days")
    with st.container(border=True):
        st.subheader("Return policy")
        st.markdown(f"- Request within **{d} days** of collecting.\n- Admin reviews each request. If approved, a locker is reserved and you get a Return QR.\n"
                    "- Seller at fault: full simulated refund. Changed my mind: delivery and locker fees are not refunded.\n- A photo is required except for Changed my mind.")
    elig = returns.eligible(user["id"])
    with st.container(border=True):
        st.subheader("Request a return")
        if not elig:
            st.caption("No order is eligible. Only collected orders inside the return window can be returned.")
        else:
            with st.form("ret_form", clear_on_submit=True):
                oid = st.selectbox("Order", [o["id"] for o in elig])
                reason = st.selectbox("Reason", config.RETURN_REASONS)
                body = st.text_input("Describe the problem")
                photo = st.file_uploader("Photo (max 1 MB)", type=["jpg", "jpeg", "png"])
                if st.form_submit_button("Request return"):
                    b64 = None
                    if photo is not None:
                        if photo.size > 1_000_000:
                            st.error("Photo is larger than 1 MB.")
                            return
                        b64 = base64.b64encode(photo.getvalue()).decode()
                    rid, err = returns.request(user["id"], oid, reason, body, b64)
                    st.success(f"Return {rid} sent.") if rid else st.error(err)
    for r in returns.for_customer(user["id"]):
        with st.container(border=True):
            st.markdown(f"**{r['id']}** for {r['order_id']} {ui.sb(r['status'])}", unsafe_allow_html=True)
            st.caption(f"{r['reason']}: {r['body']}" + (f" | Admin: {r['admin_note']}" if r["admin_note"] else ""))
            if r["status"] == "Locker Assigned":
                access = qrs.current(r["order_id"], "HUB_ACCESS", user["id"])
                if access and not access["used"] and not access["expired"]:
                    ui.show_qr(access, "Step 1: Hub room access QR", f"racc_{r['id']}")
                else:
                    ui.show_qr(qrs.current(r["order_id"], "CUSTOMER_RETURN", user["id"]), "Step 2: Return QR", f"ret_{r['id']}",
                               f"Deposit in locker {r['locker']} at {core.hub_names()[r['hub']]}.")
            if r["status"] == "Refunded":
                st.success(f"Simulated refund of {ui.rs(r['refund_amount'])} recorded.")


def complaints(user):
    st.header("Complaints")
    my = orders.customer_orders(user["id"])
    with st.container(border=True):
        if not my:
            st.caption("Place an order first.")
        else:
            with st.form("cmp", clear_on_submit=True):
                oid = st.selectbox("Order", [o["id"] for o in my])
                cat = st.selectbox("Issue type", ["Delivery issue", "Damaged parcel", "QR problem", "Payment problem", "Other"])
                body = st.text_area("Describe the problem")
                if st.form_submit_button("Submit complaint"):
                    tid, err = comms.new_ticket(user["id"], oid, cat, body)
                    st.success(f"Ticket {tid} opened.") if tid else st.error(err)
    st.subheader("My tickets")
    ui.table([{"Ticket": t["id"], "Order": t["order_id"], "Issue": t["category"], "Status": t["status"], "Admin reply": t["reply"] or "-"} for t in comms.tickets_of(user["id"])],
             "No tickets yet.")


def profile(user):
    st.header("Profile")
    p = auth.private(user["id"])
    st.write(f"**{user['name']}** ({user['id']})  \n{user['email']}")
    with st.form("prof"):
        phone = st.text_input("Phone", p.get("phone") or "")
        area = st.selectbox("Area", list(config.AREAS), index=list(config.AREAS).index(p["area"]) if p.get("area") in config.AREAS else 0)
        block = st.text_input("Block", p.get("block") or "")
        street = st.text_input("Street", p.get("street") or "")
        house = st.text_input("House / flat", p.get("house") or "")
        land = st.text_input("Landmark", p.get("landmark") or "")
        if st.form_submit_button("Save"):
            auth.save_profile(user["id"], phone, area, block, street, house, land)
            st.success("Saved. This stays private.")

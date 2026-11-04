import streamlit as st

import config
from db import q
from services import catalog, comms, core, orders, returns, wallets
import ui
from views import notifications_page

PAGES = ["Overview", "Orders", "Products", "Messages", "Returns", "Earnings", "Notifications"]


def render(user):
    page = ui.nav("Seller", PAGES)
    {"Overview": overview, "Orders": orders_page, "Products": products, "Messages": messages, "Returns": returns_page,
     "Earnings": earnings, "Notifications": notifications_page.render}[page](user)


def overview(user):
    st.header("Overview")
    o = orders.seller_orders(user["id"])
    n = lambda *s: sum(1 for x in o if x["status"] in s)
    ui.boxes([("New orders", n("Order Placed")), ("Preparing", n("Accepted", "Preparing")),
              ("Ready / with rider", n("Ready for Dispatch", "Awaiting Drop-off", "Pending Assignment", "Rider Assigned", "Awaiting Pickup")),
              ("Dispatched", n("In Transit", "Locker Assigned", "Awaiting Locker", "Parcel Deposited", "Ready for Customer Pickup"))])
    ui.boxes([("Completed", n("Collected")), ("Accepted", sum(1 for x in o if x["status"] not in ("Order Placed", "Rejected", "Cancelled"))),
              ("Rejected", n("Rejected")), ("Pending balance", ui.rs(wallets.wallet("Seller", user["id"])["pending"]))])
    st.caption("Orders must be accepted within %d hours or they are cancelled automatically." % core.isetting("accept_hours"))


def act(label, fn, key, *args, primary=False):
    if st.button(label, key=key, type="primary" if primary else "secondary"):
        ok, msg = fn(*args)
        ui.flash(msg)
        st.rerun()


def orders_page(user):
    st.header("Orders")
    names = core.hub_names()
    rows = orders.seller_orders(user["id"])
    if not rows:
        st.info("No orders yet.")
    for o in rows:
        with st.expander(f"{o['id']}  |  {o['status']}  |  {ui.rs(o['product_total'])}", expanded=o["status"] == "Order Placed"):
            st.markdown(f"{ui.sb(o['status'])} {ui.sb(o['pay_status'])}", unsafe_allow_html=True)
            ui.table([{"Item": i["name"], "Size": i["size"] or "-", "Qty": i["qty"], "Price": ui.rs(i["unit_price"]), "Amount": ui.rs(i["unit_price"] * i["qty"])} for i in core.items_of(o["id"])])
            st.caption(f"Customer: {o['customer_name']} | Parcel size {o['parcel']} | Hubs: {names[o['hub1']]}, {names[o['hub2']]} | Phone and address are hidden")
            k, s = o["id"], o["status"]
            if s == "Order Placed":
                c1, c2 = st.columns(2)
                with c1:
                    act("Accept", orders.seller_accept, f"ac_{k}", k, user["id"], primary=True)
                reason = c2.text_input("Rejection reason", key=f"rr_{k}")
                with c2:
                    act("Reject", orders.seller_reject, f"rj_{k}", k, user["id"], reason)
            elif s == "Accepted":
                act("Start preparing", orders.seller_prepare, f"pp_{k}", k, user["id"], primary=True)
            elif s == "Preparing":
                disp = st.radio("Dispatch method", ["rider", "drop"], format_func=lambda x: "Rider pickup" if x == "rider" else "Seller drop-off at collection point",
                                key=f"dm_{k}", horizontal=True)
                act("Ready for dispatch", orders.seller_ready, f"rd_{k}", k, user["id"], disp, primary=True)
            elif s == "Awaiting Drop-off":
                st.info(f"Drop the parcel at: {core.setting('collection_point')}")
                act("Confirm drop-off", orders.seller_dropped, f"dr_{k}", k, user["id"], primary=True)
            elif s == "Ready for Dispatch" or s == "Pending Assignment":
                st.caption("Waiting for a company rider. The system assigns one automatically.")


def products(user):
    st.header("My products")
    for p in catalog.of_seller(user["id"]):
        with st.container(border=True):
            c = st.columns([3, 2, 2, 1, 1])
            c[0].markdown(f"**{p['name']}**  \n<span class='mu'>Size {p['parcel']} | photo: assets/{p['img'] or '-'}</span>", unsafe_allow_html=True)
            price = c[1].number_input("Price", 1, 1_000_000, int(p["price"]), key=f"pr_{p['id']}")
            stock = c[2].number_input("Stock", 0, 100000, int(p["stock"]), key=f"st_{p['id']}")
            active = c[3].checkbox("Active", bool(p["active"]), key=f"ac_{p['id']}")
            if c[4].button("Save", key=f"sv_{p['id']}"):
                ok, msg = catalog.update(p["id"], user["id"], price, stock, active)
                ui.flash(msg)
                st.rerun()
    with st.expander("Add a new product"):
        with st.form("addp", clear_on_submit=True):
            name = st.text_input("Name")
            c1, c2, c3 = st.columns(3)
            price = c1.number_input("Price (Rs)", 0, 1_000_000, 0)
            stock = c2.number_input("Stock", 0, 100000, 0)
            parcel = c3.selectbox("Parcel size", ["S", "M", "L"], format_func=lambda s: config.SIZE_NAME[s])
            sizes = st.text_input("Sizes (comma separated, optional)", placeholder="S,M,L")
            img = st.text_input("Image name (file in assets/, without .jpg)")
            if st.form_submit_button("Add product"):
                ok, msg = catalog.add(user["id"], name, price, sizes, stock, parcel, img)
                st.success(msg) if ok else st.error(msg)


def messages(user):
    st.header("Messages")
    thread = comms.thread("seller", seller_id=user["id"])
    for m in thread:
        st.markdown(f"**{m['sender_role']}** <span class='mu'>{m['order_id']} | {ui.fmt(m['ts'])}</span>  \n{m['body']}", unsafe_allow_html=True)
    if not thread:
        st.caption("No messages yet.")
    mine = [o["id"] for o in orders.seller_orders(user["id"])]
    if mine:
        with st.form("sm", clear_on_submit=True):
            oid = st.selectbox("Reply about order", mine)
            body = st.text_input("Reply")
            if st.form_submit_button("Send"):
                cust = core.order(oid)["customer_id"]
                ok, msg = comms.send("seller", cust, oid, "Seller", user["id"], body)
                st.success(msg) if ok else st.error(msg)


def returns_page(user):
    st.header("Returns")
    rows = returns.for_seller(user["id"])
    if not rows:
        st.info("No returns for your products.")
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['id']}** for {r['order_id']} {ui.sb(r['status'])}", unsafe_allow_html=True)
            st.caption(f"{r['reason']}: {r['body']}")
            if r["status"] == "Return Collected":
                c1, c2 = st.columns(2)
                if c1.button("Received and inspected: OK", key=f"ok_{r['id']}", type="primary"):
                    ui.flash(returns.seller_inspect(r["id"], user["id"], True)[1])
                    st.rerun()
                if c2.button("Problem found", key=f"bad_{r['id']}"):
                    ui.flash(returns.seller_inspect(r["id"], user["id"], False)[1])
                    st.rerun()


def earnings(user):
    st.header("Earnings (simulated)")
    w = wallets.wallet("Seller", user["id"])
    ui.boxes([("Pending", ui.rs(w["pending"])), ("Available", ui.rs(w["available"])), ("Paid out", ui.rs(w["paid_out"]))])
    st.caption(f"Your share becomes Available {core.isetting('return_days')} days after the customer collects (the return window).")
    ui.table([{"Order": r["order"], "Amount": ui.rs(r["amount"]), "State": r["state"]} for r in w["rows"]], "No earnings yet.")
    st.download_button("Download statement (CSV)", wallets.statement_csv("Seller", user["id"]), file_name="seller_statement.csv", mime="text/csv")

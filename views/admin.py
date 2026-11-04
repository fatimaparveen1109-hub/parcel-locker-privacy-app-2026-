import pandas as pd
import streamlit as st

import config
import db
from db import q, one, now
from services import auth, comms, core, housekeeping, lockers, orders, returns, riders, wallets, qr as qrs
import ui
from views import notifications_page

PAGES = ["Overview", "Orders", "Deliveries", "Money", "Settlements", "Hubs & Lockers", "Users", "Support", "Returns", "Expired", "Reports",
         "Scan Log", "Audit Log", "Settings", "Notifications"]


def render(user):
    page = ui.nav("Admin", PAGES)
    {"Overview": overview, "Orders": orders_page, "Deliveries": deliveries, "Money": money, "Settlements": settlements, "Hubs & Lockers": hubs,
     "Users": users, "Support": support, "Returns": returns_page, "Expired": expired, "Reports": reports, "Scan Log": scan_log,
     "Audit Log": audit_log, "Settings": settings_page, "Notifications": notifications_page.render}[page](user)


def cnt(sql, args=()):
    return one(sql, args)["n"]


def overview(user):
    st.header("Overview")
    pend = cnt("SELECT COUNT(*) n FROM orders WHERE status='Pending Assignment'")
    wait = cnt("SELECT COUNT(*) n FROM orders WHERE status='Awaiting Locker'")
    off = cnt("SELECT COUNT(*) n FROM lockers WHERE status='off'")
    exp = cnt("SELECT COUNT(*) n FROM orders WHERE status='Expired (Admin Review)'")
    alerts = [t for t in (f"{pend} order(s) waiting for a rider" if pend else "", f"{wait} order(s) waiting for a locker" if wait else "",
                          f"{off} locker(s) unavailable" if off else "", f"{exp} expired pickup(s) need review" if exp else "") if t]
    if alerts:
        st.warning(" | ".join(alerts))
    s = lambda *x: cnt("SELECT COUNT(*) n FROM orders WHERE status IN (%s)" % ",".join("?" * len(x)), x)
    st.subheader("Orders")
    ui.boxes([("Total orders", cnt("SELECT COUNT(*) n FROM orders")), ("Awaiting processing", s("Order Placed", "Accepted", "Preparing")),
              ("Collected", s("Collected")), ("Rejected / cancelled", s("Rejected", "Cancelled"))])
    st.subheader("Sellers")
    ui.boxes([("Orders accepted", cnt("SELECT COUNT(*) n FROM orders WHERE status NOT IN ('Order Placed','Rejected','Cancelled')")), ("Orders rejected", s("Rejected"))])
    st.subheader("Deliveries")
    ui.boxes([("Pending assignment", pend), ("Rider assigned", s("Rider Assigned", "Awaiting Pickup")), ("In transit (with riders)", s("In Transit")),
              ("Deposited in lockers", s("Parcel Deposited", "Ready for Customer Pickup")), ("Awaiting locker", wait)])
    st.subheader("Payments (simulated)")
    ok = one("SELECT COUNT(*) n, COALESCE(SUM(amount),0) a FROM payments WHERE status='Success'")
    ui.boxes([("Verified", f"{ok['n']} | {ui.rs(ok['a'])}"), ("Pending orders", cnt("SELECT COUNT(*) n FROM orders WHERE pay_status!='Paid' AND status NOT IN ('Cancelled','Rejected')")),
              ("Failed attempts", cnt("SELECT COUNT(*) n FROM payments WHERE status='Failed'"))])
    st.subheader("Lockers")
    names, c = core.hub_names(), lockers.counts()
    rows = [{"Hub": names[h], "Free": v["free"], "Occupied": v["occupied"], "Reserved": v["reserved"], "Unavailable": v["off"]} for h, v in c.items()]
    ui.table(sorted(rows, key=lambda r: r["Hub"]))
    st.subheader("Issues")
    ui.boxes([("Unavailable lockers", off), ("Open complaints", cnt("SELECT COUNT(*) n FROM tickets WHERE status IN ('Open','Under Review')")),
              ("Open returns", cnt("SELECT COUNT(*) n FROM returns WHERE status IN ('Requested','Inspection Failed')")),
              ("Pickups near / past deadline", cnt("SELECT COUNT(*) n FROM orders WHERE status IN ('Parcel Deposited','Ready for Customer Pickup') AND expires_at<?", (now() + 12 * 3600,)) + exp)])
    st.subheader("People")
    avail = [r for r in q("SELECT id FROM users WHERE role='Rider' AND status='active'")]
    busy = sum(1 for r in avail if riders.load(r["id"]) > 0)
    ui.boxes([("Riders available / busy", f"{len(avail) - busy} / {busy}"), ("Sellers", cnt("SELECT COUNT(*) n FROM users WHERE role='Seller' AND status='active'")),
              ("Customers", cnt("SELECT COUNT(*) n FROM users WHERE role='Customer'")),
              ("Pending approvals", cnt("SELECT COUNT(*) n FROM users WHERE status='pending'")),
              ("Logins last hour", cnt("SELECT COUNT(*) n FROM logins WHERE ok=1 AND ts>?", (now() - 3600,)))])


def orders_page(user):
    st.header("Orders")
    rows = orders.admin_orders()
    names = core.hub_names()
    ui.table([{"Order": o["id"], "Status": o["status"], "Payment": o["pay_status"], "Seller": o["seller_id"], "Rider": o["rider_id"] or "-",
               "Primary hub": names.get(o["hub1"]), "Alt hub": names.get(o["hub2"]) if o["allow_alt"] else "not allowed",
               "Assigned": f"{names.get(o['hub'])} {o['locker']}" if o["hub"] else "-", "Total": ui.rs(o["total"]), "Updated": ui.fmt(o["updated"])} for o in rows], "No orders yet.")
    if rows:
        pick = st.selectbox("Open order details", [o["id"] for o in rows])
        o = core.order(pick)
        p = orders.private_of(pick, masked=True)
        with st.container(border=True):
            st.markdown(f"### {pick} {ui.sb(o['status'])} {ui.sb(o['pay_status'])}", unsafe_allow_html=True)
            st.caption(f"Customer {p.get('cname')} | phone {p.get('phone')} | address hidden | Rider {o['rider_id'] or '-'} | Pickup deadline {ui.fmt(o['expires_at'])}")
            ui.table([{"Item": i["name"], "Size": i["size"] or "-", "Qty": i["qty"], "Amount": ui.rs(i["unit_price"] * i["qty"])} for i in core.items_of(pick)])
            st.markdown("**Timeline**")
            ui.table([{"Status": e["status"], "Time": ui.fmt(e["ts"]), "By": e["actor"]} for e in q("SELECT * FROM events WHERE order_id=? ORDER BY id", (pick,))])
            st.markdown("**Payments**")
            ui.table([{"Txn": x["id"], "Method": x["method"], "Amount": ui.rs(x["amount"]), "Status": x["status"], "Time": ui.fmt(x["ts"])} for x in q("SELECT * FROM payments WHERE order_id=? ORDER BY ts", (pick,))], "No payments.")
            st.markdown("**QR scan log**")
            ui.table([{"Time": ui.fmt(s["ts"]), "Type": s["qtype"], "Result": s["result"]} for s in qrs.recent_scans(30, pick)], "No scans.")
            st.caption(f"Split: {ui.rs(o['total'])} = Seller {ui.rs(o['product_total'])} + Rider {ui.rs(o['delivery_fee'])} + Locker {ui.rs(o['locker_fee'])}")


def deliveries(user):
    st.header("Deliveries")
    act = [o for o in orders.admin_orders() if o["status"] not in config.DONE]
    ui.table([{"Order": o["id"], "Status": o["status"], "Rider": o["rider_id"] or "-", "Parcel": o["parcel"]} for o in act], "No active deliveries.")
    pend = [o for o in act if o["status"] == "Pending Assignment"]
    for o in pend:
        if st.button(f"Retry auto-assign {o['id']}", key=f"ra_{o['id']}"):
            riders.assign_order(o["id"])
            st.rerun()
    movable = [o for o in act if o["status"] in ("Rider Assigned", "Awaiting Pickup", "In Transit")]
    rid = [r["id"] for r in q("SELECT id FROM users WHERE role='Rider' AND status='active'")]
    if movable and rid:
        with st.form("reassign"):
            oid = st.selectbox("Reassign order", [o["id"] for o in movable])
            to = st.selectbox("To rider", rid)
            if st.form_submit_button("Reassign"):
                db.run("UPDATE orders SET rider_id=? WHERE id=?", (to, oid))
                core.note(to, f"Task {oid} was assigned to you by Admin.")
                core.audit("Admin", f"Reassigned {oid} to {to}")
                st.rerun()


def money(user):
    st.header("Payments and money flow")
    st.caption("Everything is SIMULATED. No real funds move.")
    ws = {n: wallets.wallet(n) for n in ("Seller", "Rider", "Locker operator")}
    ui.boxes([(f"{n}: pending / available", f"{ui.rs(w['pending'])} / {ui.rs(w['available'])}") for n, w in ws.items()])
    st.subheader("How each payment is split")
    rows = []
    for o in q("SELECT * FROM orders WHERE pay_status='Paid' ORDER BY created DESC"):
        sh = wallets.shares(o)
        rows.append({"Order": o["id"], "Total": ui.rs(o["total"]), "Seller": f"{ui.rs(o['product_total'])} -> {o['seller_id']}",
                     "Rider": f"{ui.rs(o['delivery_fee'])} -> {o['rider_id'] or 'unassigned'}", "Locker operator": ui.rs(o["locker_fee"]), "State": sh[0]["state"] if sh else "-"})
    ui.table(rows, "No verified payments yet.")
    st.caption(f"Rider share is Available after deposit. Seller and locker shares are Available {core.isetting('return_days')} days after collection. Refunds reverse them.")
    st.subheader("All payment attempts")
    ui.table([{"Txn": p["id"], "Order": p["order_id"], "Method": p["method"], "Amount": ui.rs(p["amount"]), "Status": p["status"], "Time": ui.fmt(p["ts"])}
              for p in q("SELECT * FROM payments ORDER BY ts DESC")], "No payments yet.")


def settlements(user):
    st.header("Settlements (simulated payouts)")
    for name in ("Seller", "Rider", "Locker operator"):
        st.subheader(name)
        for owner in wallets.owners(name):
            w = wallets.wallet(name, owner)
            c = st.columns([3, 2, 2, 2])
            c[0].write(owner)
            c[1].write(f"Available {ui.rs(w['available'])}")
            c[2].write(f"Paid out {ui.rs(w['paid_out'])}")
            if c[3].button("Mark as paid out", key=f"po_{name}_{owner}", disabled=w["available"] <= 0):
                ui.flash(wallets.payout(name, owner)[1])
                st.rerun()
        if not wallets.owners(name):
            st.caption("No earnings yet.")


def hubs(user):
    st.header("Hubs and lockers")
    for h in q("SELECT * FROM hubs ORDER BY name"):
        with st.container(border=True):
            st.subheader(h["name"])
            rows = lockers.grid(h["id"])
            st.markdown(ui.lockers_html(rows), unsafe_allow_html=True)
            st.caption("Blue = occupied | Purple = reserved | Red = unavailable | Grey = free. Hover for the Delivery ID.")
            c1, c2, c3 = st.columns([2, 1, 1])
            lk = c1.selectbox("Locker", [r["id"] for r in rows], key=f"lk_{h['id']}")
            cur = next(r for r in rows if r["id"] == lk)
            if c2.button("Restore" if cur["status"] == "off" else "Mark unavailable", key=f"off_{h['id']}", disabled=bool(cur["order_id"])):
                lockers.set_off(h["id"], lk, cur["status"] != "off")
                core.audit("Admin", f"Locker {h['id']}/{lk} toggled")
                st.rerun()
    with st.expander("Add or edit a hub"):
        with st.form("addhub", clear_on_submit=True):
            name = st.text_input("Hub name")
            area = st.text_input("Area")
            if st.form_submit_button("Add hub with 8 lockers"):
                if name.strip():
                    hid = "H-" + str(db.meta_get("hubseq", 10) + 1)
                    db.meta_set("hubseq", db.meta_get("hubseq", 10) + 1)
                    db.run("INSERT INTO hubs VALUES(?,?,?,1)", (hid, name.strip(), area.strip()))
                    for i, size in enumerate(config.LOCKER_SIZES, 1):
                        db.run("INSERT INTO lockers VALUES(?,?,?,'ok',NULL,NULL,NULL)", (f"L{i}", hid, size))
                    core.audit("Admin", f"Hub added {name}")
                    st.rerun()


def users(user):
    st.header("Users and login activity")
    pend = q("SELECT * FROM users WHERE status='pending' ORDER BY created")
    st.subheader("Waiting for approval")
    if not pend:
        st.caption("No pending seller or rider requests.")
    for u in pend:
        c = st.columns([3, 2, 1, 1])
        c[0].write(f"{u['name']} ({u['role']})")
        c[1].write(core.mask_email(u["email"]))
        if c[2].button("Approve", key=f"apr_{u['id']}", type="primary"):
            auth.set_user_status(u["id"], "active")
            st.rerun()
        if c[3].button("Reject", key=f"rej_{u['id']}"):
            auth.reject_request(u["id"])
            st.rerun()
    st.subheader("Accounts")
    for u in q("SELECT * FROM users WHERE status!='pending' ORDER BY role, id"):
        c = st.columns([3, 3, 2, 1])
        c[0].write(f"{u['name']} ({u['id']})")
        c[1].write(core.mask_email(u["email"]) + f" | {u['role']}")
        c[2].markdown(ui.sb(u["status"]), unsafe_allow_html=True)
        if u["role"] != "Admin" and c[3].button("Suspend" if u["status"] == "active" else "Activate", key=f"su_{u['id']}"):
            auth.set_user_status(u["id"], "suspended" if u["status"] == "active" else "active")
            st.rerun()
    st.subheader("Sellers and riders")
    ui.table([{"Seller": s["id"], "Accepted": cnt("SELECT COUNT(*) n FROM orders WHERE seller_id=? AND status NOT IN ('Order Placed','Rejected','Cancelled')", (s["id"],)),
               "Rejected": cnt("SELECT COUNT(*) n FROM orders WHERE seller_id=? AND status='Rejected'", (s["id"],)),
               "Collected": cnt("SELECT COUNT(*) n FROM orders WHERE seller_id=? AND status='Collected'", (s["id"],)),
               "Earnings (sim.)": ui.rs(wallets.wallet("Seller", s["id"])["total"])} for s in q("SELECT id FROM users WHERE role='Seller'")], "No sellers.")
    ui.table([{"Rider": r["id"], "Assigned": cnt("SELECT COUNT(*) n FROM orders WHERE rider_id=?", (r["id"],)), "Active load": riders.load(r["id"]),
               "Declined": cnt("SELECT COUNT(*) n FROM orders WHERE declined LIKE ?", (f"%{r['id']}%",))} for r in q("SELECT id FROM users WHERE role='Rider'")], "No riders.")
    st.subheader("Login activity")
    ui.table([{"Time": ui.fmt(l["ts"]), "User": l["user_id"], "Role": l["role"], "Email": l["email_masked"], "Result": "Success" if l["ok"] else "Failed"}
              for l in q("SELECT * FROM logins ORDER BY id DESC LIMIT 60")], "No logins yet.")


def support(user):
    st.header("Support")
    st.subheader("Complaint tickets")
    for t in comms.all_tickets():
        with st.container(border=True):
            st.markdown(f"**{t['id']}** | {t['order_id']} | {t['category']} {ui.sb(t['status'])}", unsafe_allow_html=True)
            st.caption(t["body"])
            c1, c2 = st.columns([1, 3])
            status = c1.selectbox("Status", ["Open", "Under Review", "Resolved", "Closed"], index=["Open", "Under Review", "Resolved", "Closed"].index(t["status"]), key=f"ts_{t['id']}")
            reply = c2.text_input("Reply", t["reply"] or "", key=f"tr_{t['id']}")
            if st.button("Save", key=f"tv_{t['id']}"):
                comms.update_ticket(t["id"], status, reply)
                st.rerun()
    if not comms.all_tickets():
        st.caption("No complaints.")
    st.subheader("Customer support chat")
    msgs = comms.thread("admin")
    for m in msgs:
        st.markdown(f"**{m['sender_role']}** <span class='mu'>{m['customer_id']} | {ui.fmt(m['ts'])}</span>  \n{m['body']}", unsafe_allow_html=True)
    custs = sorted({m["customer_id"] for m in msgs})
    if custs:
        with st.form("ar", clear_on_submit=True):
            cid = st.selectbox("Reply to", custs)
            body = st.text_input("Message")
            if st.form_submit_button("Send"):
                ok, msg = comms.send("admin", cid, "", "Admin", user["id"], body)
                st.success(msg) if ok else st.error(msg)
    else:
        st.caption("No support chats.")


def returns_page(user):
    st.header("Returns")
    rows = returns.all_returns()
    if not rows:
        st.info("No return requests.")
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['id']}** for {r['order_id']} {ui.sb(r['status'])}", unsafe_allow_html=True)
            st.caption(f"{r['reason']}: {r['body']}")
            if r["photo"]:
                st.image(__import__("base64").b64decode(r["photo"]), width=160)
            if r["status"] == "Requested":
                note = st.text_input("Note to customer", key=f"rn_{r['id']}")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"rap_{r['id']}", type="primary"):
                    ui.flash(returns.decide(r["id"], True, note)[1])
                    st.rerun()
                if c2.button("Reject", key=f"rrj_{r['id']}"):
                    ui.flash(returns.decide(r["id"], False, note)[1])
                    st.rerun()
            elif r["status"] == "Inspection Failed":
                c1, c2 = st.columns(2)
                if c1.button("Refund anyway (simulated)", key=f"rf_{r['id']}"):
                    ui.flash(returns.admin_resolve_failed(r["id"], True)[1])
                    st.rerun()
                if c2.button("Close without refund", key=f"rc_{r['id']}"):
                    ui.flash(returns.admin_resolve_failed(r["id"], False)[1])
                    st.rerun()


def expired(user):
    st.header("Expired pickups")
    rows = [o for o in orders.admin_orders() if o["status"] == "Expired (Admin Review)"]
    if not rows:
        st.info("No expired pickups.")
    for o in rows:
        with st.container(border=True):
            st.write(f"**{o['id']}** | {o['hub']} {o['locker']} | deadline was {ui.fmt(o['expires_at'])}")
            c1, c2 = st.columns(2)
            if c1.button("Extend 24 hours", key=f"ex_{o['id']}", type="primary"):
                ui.flash(housekeeping.extend_pickup(o["id"])[1])
                st.rerun()
            if c2.button("Return to seller", key=f"rt_{o['id']}"):
                ui.flash(housekeeping.return_to_seller(o["id"])[1])
                st.rerun()
    st.caption("Parcels are never returned automatically. Admin decides.")


def reports(user):
    st.header("Reports")
    rows = orders.admin_orders()
    if not rows:
        st.info("No data yet.")
        return
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["created"], unit="s").dt.strftime("%Y-%m-%d")
    st.subheader("Orders per day")
    st.bar_chart(df.groupby("day").size())
    pays = pd.DataFrame(q("SELECT status FROM payments WHERE status IN ('Success','Failed')"))
    st.subheader("Payments: verified vs failed")
    if len(pays):
        st.bar_chart(pays.groupby("status").size())
    else:
        st.caption("No payments yet.")
    coll = cnt("SELECT COUNT(*) n FROM orders WHERE status='Collected'")
    rets = cnt("SELECT COUNT(*) n FROM returns")
    ui.boxes([("Return rate", f"{(rets * 100 // coll) if coll else 0}%"), ("Returns", rets), ("Collected", coll)])
    st.subheader("Locker usage per hub (orders assigned)")
    names = core.hub_names()
    use = pd.DataFrame(q("SELECT hub, COUNT(*) n FROM orders WHERE hub IS NOT NULL GROUP BY hub"))
    if len(use):
        use["hub"] = use["hub"].map(names)
        st.bar_chart(use.set_index("hub"))
    else:
        st.caption("No locker usage yet.")


def scan_log(user):
    st.header("QR scan log")
    ui.table([{"Time": ui.fmt(s["ts"]), "Order": s["order_id"] or "-", "Type": s["qtype"] or "-", "Role": s["role"] or "-", "Hub": s["hub_id"] or "-",
               "Locker": s["locker_id"] or "-", "Result": s["result"]} for s in qrs.recent_scans(200)], "No scans yet.")


def audit_log(user):
    st.header("Audit log")
    ui.table([{"Time": ui.fmt(a["ts"]), "Actor": a["actor"], "Action": a["body"]} for a in q("SELECT * FROM audit ORDER BY id DESC LIMIT 200")], "No records yet.")


def settings_page(user):
    st.header("Settings")
    if not db.IS_PG:
        st.error("DATABASE_URL is not set. The app is using a temporary local file that disappears when Streamlit restarts. Set DATABASE_URL in Secrets.")
    if config.USING_DEFAULT_ADMIN or config.APP_SECRET == "dev-secret-change-me":
        st.warning("Default admin password or APP_SECRET is in use. Set ADMIN_PASSWORD and APP_SECRET in Secrets before sharing the app.")
    with st.container(border=True):
        st.subheader("Fees and policies")
        keys = [("delivery_fee", "Delivery fee (Rs)"), ("locker_fee", "Locker fee (Rs)"), ("return_days", "Return window (days)"),
                ("pickup_hours", "Pickup window (hours)"), ("accept_hours", "Seller must accept within (hours)"), ("pay_hours", "Unpaid pay-now orders cancel after (hours)"),
                ("reserve_hours", "Locker reservation (hours)"), ("rider_capacity", "Rider capacity (active tasks)"), ("commission_pct", "Platform commission (%)")]
        with st.form("cfg"):
            vals = {k: st.number_input(label, 0, 100000, core.isetting(k), key=f"cfg_{k}") for k, label in keys}
            cp = st.text_input("Seller drop-off collection point", core.setting("collection_point"))
            if st.form_submit_button("Save settings"):
                for k, v in vals.items():
                    core.set_setting(k, int(v))
                core.set_setting("collection_point", cp)
                core.audit("Admin", "Settings changed")
                st.success("Saved. Fees apply to new orders.")
    with st.container(border=True):
        st.subheader("Integration status")
        from integrations import LOCKER, QR_PROVIDER
        st.write(f"QR system: **{QR_PROVIDER.mode}**")
        st.write(f"Locker controller: **{LOCKER.mode}**")
        st.caption("Replace the classes in integrations.py when the real controller and QR system details are available.")
    with st.container(border=True):
        st.subheader("Demo tools")
        st.caption(f"Time shift now: +{db.get_offset()} hours (demo only).")
        c1, c2, c3 = st.columns(3)
        if c1.button("Run housekeeping now"):
            st.success(f"{housekeeping.run_all(True)} change(s) made.")
        if c2.button("Simulate +49 hours"):
            db.set_offset(db.get_offset() + 49)
            housekeeping.run_all(True)
            ui.flash("Moved forward 49 hours.")
            st.rerun()
        if c3.button(f"Skip return window (+{core.isetting('return_days')} days)"):
            db.set_offset(db.get_offset() + core.isetting("return_days") * 24 + 1)
            housekeeping.run_all(True)
            ui.flash("Return window skipped.")
            st.rerun()
        if st.button("Reset time shift"):
            db.set_offset(0)
            st.rerun()
    with st.container(border=True):
        st.subheader("Reset demo data (Admin only)")
        st.error("This deletes demo records. It cannot be undone.")
        sure = st.checkbox("I understand this deletes demo data", key="reset_sure")
        c1, c2 = st.columns(2)
        if c1.button("Reset orders and stock (keep accounts)", disabled=not sure):
            reset_orders()
            ui.flash("Orders, payments, lockers and stock were reset. Accounts were kept.")
            st.rerun()
        if c2.button("Reset everything (keep admin)", disabled=not sure):
            reset_all()
            ui.flash("Everything was reset.")
            st.session_state.update(page="home", uid=None, role=None)
            st.rerun()


def _clear_orders():
    for t in ("orders", "order_items", "order_private", "events", "payments", "qr_codes", "scans", "returns", "tickets", "messages", "notifications", "payouts", "audit"):
        db.run(f"DELETE FROM {t}")
    db.run("DELETE FROM meta WHERE k IN ('DLV','RET','TKT','TXN')")
    db.run("UPDATE lockers SET order_id=NULL, res_kind=NULL, res_until=NULL, status='ok'")
    db.run("DELETE FROM products")
    import seed
    for sel, name, img, price, sizes, stock, parcel in config.PRODUCTS:
        if one("SELECT 1 FROM users WHERE id=?", (sel,)):
            db.run("INSERT INTO products(seller_id,name,img,price,sizes,stock,parcel,active) VALUES(?,?,?,?,?,?,?,1)", (sel, name, img, price, sizes, stock, parcel))
    db.set_offset(0)


def reset_orders():
    _clear_orders()
    core.audit("Admin", "Demo reset: orders cleared, accounts kept")
    for r in ("Customer", "Seller", "Rider"):
        core.note_role(r, "Demo data was reset by admin.")


def reset_all():
    _clear_orders()
    db.run("DELETE FROM user_private WHERE user_id IN (SELECT id FROM users WHERE role!='Admin')")
    db.run("DELETE FROM users WHERE role!='Admin'")
    db.run("DELETE FROM logins")
    db.run("DELETE FROM meta WHERE k IN ('CUS','SEL','RID')")
    db.run("DELETE FROM products")
    import seed
    seed.run()
    core.audit("Admin", "Demo reset: everything cleared")

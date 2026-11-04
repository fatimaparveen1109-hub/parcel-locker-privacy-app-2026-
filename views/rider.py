import streamlit as st

import config
from db import q, run
from services import core, orders, returns, wallets, qr as qrs
import ui
from views import notifications_page

PAGES = ["Overview", "My Tasks", "History", "Report Problem", "Earnings", "Notifications"]


def render(user):
    page = ui.nav("Rider", PAGES)
    {"Overview": overview, "My Tasks": tasks, "History": history, "Report Problem": report, "Earnings": earnings,
     "Notifications": notifications_page.render}[page](user)


def overview(user):
    st.header("Overview")
    t = orders.rider_tasks(user["id"])
    n = lambda *s: sum(1 for x in t if x["status"] in s)
    rets = [r for r in q("SELECT * FROM returns WHERE rider_id=?", (user["id"],))]
    ui.boxes([("New tasks", n("Rider Assigned")), ("Pending pickups", n("Awaiting Pickup")), ("In transit", n("In Transit")),
              ("Pending deposits", n("Locker Assigned", "Awaiting Locker"))])
    ui.boxes([("Completed deliveries", sum(1 for x in t if x["status"] in config.IN_LOCKER + ["Collected"])),
              ("Return pickups waiting", sum(1 for r in rets if r["status"] == "Return Deposited")), ("Active load", len(t))])


def tasks(user):
    st.header("My tasks")
    names = core.hub_names()
    active = [t for t in orders.rider_tasks(user["id"]) if t["status"] in config.ACTIVE_RIDER]
    if not active:
        st.info("No active delivery tasks. New orders are assigned to you automatically.")
    for t in active:
        k, s = t["id"], t["status"]
        with st.container(border=True):
            st.markdown(f"**{k}** {ui.sb(s)}", unsafe_allow_html=True)
            pickup = core.setting("collection_point") if t["disp"] == "drop" else f"Seller {t['seller_id']} pickup point"
            st.caption(f"Parcel size {t['parcel']} | Pickup: {pickup} | Customer details are hidden")
            if s == "Rider Assigned":
                c1, c2 = st.columns(2)
                if c1.button("Accept task", key=f"acc_{k}", type="primary"):
                    ui.flash(orders.rider_accept(k, user["id"])[1])
                    st.rerun()
                if c2.button("Decline", key=f"dec_{k}"):
                    ui.flash(orders.rider_decline(k, user["id"])[1])
                    st.rerun()
            elif s == "Awaiting Pickup":
                if st.button("Confirm pickup from seller", key=f"pk_{k}", type="primary"):
                    ui.flash(orders.rider_pickup(k, user["id"])[1])
                    st.rerun()
            elif s in ("In Transit", "Awaiting Locker"):
                opts = orders.suggest(k)
                if not opts:
                    st.warning("No compatible free locker at the allowed hubs. The system retries automatically.")
                else:
                    pick = st.selectbox("Suggested lockers", range(len(opts)), key=f"sg_{k}",
                                        format_func=lambda i: f"{names[opts[i]['hub']]} | {opts[i]['locker']} ({config.SIZE_NAME[opts[i]['size']]})" + (" | alternative hub" if opts[i]["alt"] else ""))
                    if st.button("Assign this locker", key=f"as_{k}", type="primary"):
                        ui.flash(orders.assign_locker(k, user["id"], opts[pick]["hub"], opts[pick]["locker"])[1])
                        st.rerun()
            elif s == "Locker Assigned":
                st.info(f"Go to {names[t['hub']]}, locker {t['locker']}. Use the Locker scanner (top bar): Step 1 room QR, Step 2 delivery QR, then confirm Door closed.")
                access = qrs.current(k, "HUB_ACCESS", user["id"])
                if access and not access["used"] and not access["expired"]:
                    ui.show_qr(access, "Step 1: Hub room access QR", f"acc_{k}")
                else:
                    ui.show_qr(qrs.current(k, "RIDER_DELIVERY", user["id"]), "Step 2: Delivery QR", f"dl_{k}", "Opens the locker for deposit.")
                if st.button("I need a new QR", key=f"rg_{k}"):
                    o = core.order(k)
                    qrs.issue(k, "HUB_ACCESS", "Rider", user["id"], o["reserve_until"] or 0, t["hub"], None)
                    qrs.issue(k, "RIDER_DELIVERY", "Rider", user["id"], o["reserve_until"] or 0, t["hub"], t["locker"])
                    ui.flash("New QR codes issued.")
                    st.rerun()
    st.subheader("Return pickups")
    rets = q("SELECT * FROM returns WHERE rider_id=? AND status='Return Deposited'", (user["id"],))
    if not rets:
        st.caption("No return pickups waiting.")
    for r in rets:
        with st.container(border=True):
            st.markdown(f"**Return pickup {r['order_id']}**  \n<span class='mu'>{names[r['hub']]} | locker {r['locker']} | Customer details hidden</span>", unsafe_allow_html=True)
            access = qrs.current(r["order_id"], "HUB_ACCESS", user["id"])
            if access and not access["used"] and not access["expired"]:
                ui.show_qr(access, "Step 1: Hub room access QR", f"racc_{r['id']}")
            else:
                ui.show_qr(qrs.current(r["order_id"], "RIDER_RETURN", user["id"]), "Step 2: Return pickup QR", f"rp_{r['id']}")


def history(user):
    st.header("History")
    names = core.hub_names()
    done = [t for t in orders.rider_tasks(user["id"]) if t["status"] in config.IN_LOCKER + ["Collected"]]
    ui.table([{"Delivery": t["id"], "Hub": names.get(t["hub"], "-"), "Locker": t["locker"], "Status": t["status"]} for t in done], "No completed deliveries yet.")


def report(user):
    st.header("Report a problem")
    mine = [t for t in orders.rider_tasks(user["id"]) if t["status"] in config.ACTIVE_RIDER]
    if not mine:
        st.info("You have no active task.")
        return
    with st.form("rp", clear_on_submit=True):
        oid = st.selectbox("Task", [t["id"] for t in mine])
        kind = st.selectbox("Problem", ["Locker full", "Locker faulty or offline", "Parcel damaged", "Other"])
        text = st.text_input("Details (no personal data)")
        if st.form_submit_button("Report"):
            if kind.startswith("Locker"):
                ok, msg = orders.report_locker_issue(oid, user["id"], f"{kind}. {text}")
                if not ok:
                    core.note_role("Admin", f"{oid}: rider reported '{kind}'. {text}")
                    msg = "Reported to Admin."
            else:
                core.note_role("Admin", f"{oid}: rider reported '{kind}'. {text}")
                core.audit(user["id"], f"Problem reported on {oid}: {kind}")
                msg = "Reported to Admin."
            st.success(msg)


def earnings(user):
    st.header("Earnings (simulated)")
    w = wallets.wallet("Rider", user["id"])
    ui.boxes([("Pending", ui.rs(w["pending"])), ("Available", ui.rs(w["available"])), ("Paid out", ui.rs(w["paid_out"]))])
    st.caption("Your delivery fee becomes Available after the parcel is confirmed in the locker.")
    ui.table([{"Order": r["order"], "Amount": ui.rs(r["amount"]), "State": r["state"]} for r in w["rows"]], "No earnings yet.")
    st.download_button("Download statement (CSV)", wallets.statement_csv("Rider", user["id"]), file_name="rider_statement.csv", mime="text/csv")

"""Streamlit has no background scheduler, so these jobs run at the start of page loads (every few seconds at most)
and from an Admin button. They handle expiries, reminders, reservation timeouts and auto-cancels."""
from db import q, one, run, now, meta_get, meta_set
from services import core, lockers, orders, returns, riders


def run_all(force=False):
    if not force and now() - meta_get("last_hk", 0) < 10:
        return 0
    meta_set("last_hk", now())
    n = 0
    t = now()
    # seller must accept in time
    for o in q("SELECT * FROM orders WHERE status='Order Placed' AND created<?", (t - core.isetting("accept_hours") * 3600,)):
        orders.cancel(o["id"], "System", who="System")
        core.tell_customer(o, "the seller did not accept in time, so the order was cancelled.")
        n += 1
    # unpaid pay-now orders
    for o in q("SELECT * FROM orders WHERE pay_timing='now' AND pay_status!='Paid' AND status NOT IN ('Cancelled','Rejected','Collected') AND created<?",
               (t - core.isetting("pay_hours") * 3600,)):
        orders.cancel(o["id"], "System", who="System")
        n += 1
    # locker reservation timeout: release and search again
    for o in q("SELECT * FROM orders WHERE status='Locker Assigned' AND reserve_until IS NOT NULL AND reserve_until<?", (t,)):
        lockers.release(o["hub"], o["locker"])
        run("UPDATE qr_codes SET active=0 WHERE order_id=? AND used=0", (o["id"],))
        run("UPDATE orders SET hub=NULL, locker=NULL, reserve_until=NULL WHERE id=?", (o["id"],))
        core.set_status(o["id"], "In Transit", "System")
        core.note(o["rider_id"], f"{o['id']}: the locker reservation timed out. A new locker is being found.")
        orders.try_auto_locker(o["id"])
        n += 1
    # waiting for a locker: retry
    for o in q("SELECT id FROM orders WHERE status='Awaiting Locker'"):
        if orders.try_auto_locker(o["id"]):
            n += 1
    returns.retry_waiting()
    # pickup reminders and expiry
    for o in q("SELECT * FROM orders WHERE status IN ('Parcel Deposited','Ready for Customer Pickup') AND expires_at IS NOT NULL"):
        left = o["expires_at"] - t
        if left <= 0:
            run("UPDATE qr_codes SET active=0 WHERE order_id=? AND used=0", (o["id"],))
            core.set_status(o["id"], "Expired (Admin Review)", "System")
            core.tell_customer(o, "the pickup window ended. Your QR expired and Admin will review the case.")
            core.note_role("Admin", f"{o['id']}: pickup expired, review needed.")
            n += 1
        elif left <= 6 * 3600 and not o["rem6"]:
            run("UPDATE orders SET rem6=1 WHERE id=?", (o["id"],))
            core.tell_customer(o, "only 6 hours left to collect your parcel.")
        elif left <= 24 * 3600 and not o["rem24"]:
            run("UPDATE orders SET rem24=1 WHERE id=?", (o["id"],))
            core.tell_customer(o, "24 hours left to collect your parcel.")
    return n


def extend_pickup(oid, hours=24):
    o = core.order(oid)
    if o["status"] != "Expired (Admin Review)":
        return False, "Not allowed now."
    from services import qr as qrs
    exp = now() + hours * 3600
    run("UPDATE orders SET expires_at=?, rem24=0, rem6=0 WHERE id=?", (exp, oid))
    if o["pay_status"] == "Paid":
        core.set_status(oid, "Ready for Customer Pickup", "Admin")
        qrs.issue(oid, "CUSTOMER_PICKUP", "Customer", o["customer_id"], exp, o["hub"], o["locker"])
        qrs.issue(oid, "HUB_ACCESS", "Customer", o["customer_id"], exp, o["hub"], None)
    else:
        core.set_status(oid, "Parcel Deposited", "Admin")
    core.tell_customer(o, f"pickup extended by {hours} hours. A new QR was issued.")
    return True, "Extended."


def return_to_seller(oid):
    o = core.order(oid)
    if o["status"] != "Expired (Admin Review)":
        return False, "Not allowed now."
    lockers.release(o["hub"], o["locker"])
    core.set_status(oid, "Returned to Seller", "Admin")
    orders.restock(oid)
    core.tell_customer(o, "the parcel was returned to the seller after the pickup window ended.")
    core.note(o["seller_id"], f"{oid}: returned to you after the pickup window.")
    return True, "Returned to seller."

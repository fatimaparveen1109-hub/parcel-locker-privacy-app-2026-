"""Return flow: request -> admin decision -> NEW locker -> customer deposit -> rider pickup -> seller inspection -> simulated refund."""
import config
from db import q, one, run, now, next_id
from services import core, lockers, riders, qr as qrs, orders


def eligible(cid):
    days = core.isetting("return_days") * 86400
    rows = q("SELECT * FROM orders WHERE customer_id=? AND status='Collected' AND collected_at>?", (cid, now() - days))
    return [o for o in rows if not one("SELECT 1 FROM returns WHERE order_id=? AND status NOT IN ('Rejected')", (o["id"],))]


def request(cid, oid, reason, body, photo_b64=None):
    o = core.order(oid)
    if not o or o["customer_id"] != cid or not any(x["id"] == oid for x in eligible(cid)):
        return None, "This order is not eligible for a return."
    if reason in config.SELLER_FAULT and not photo_b64:
        return None, "Please add a photo for this reason."
    rid = next_id("RET")
    run("INSERT INTO returns VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,0,?,?)", (rid, oid, cid, reason, body or "", photo_b64, "Requested", "", now(), now()))
    core.note_role("Admin", f"Return request {rid} for {oid}.")
    core.note(cid, f"Return request {rid} sent for {oid}.")
    return rid, ""


def decide(rid, approve, note_text, actor="Admin"):
    r = one("SELECT * FROM returns WHERE id=?", (rid,))
    if not r or r["status"] != "Requested":
        return False, "Not allowed now."
    if not approve:
        run("UPDATE returns SET status='Rejected', admin_note=?, updated=? WHERE id=?", (note_text, now(), rid))
        core.note(r["customer_id"], f"Return {rid} was rejected. {note_text}")
        return True, "Rejected."
    run("UPDATE returns SET admin_note=?, updated=? WHERE id=?", (note_text, now(), rid))
    core.note(r["customer_id"], f"Return {rid} approved.")
    return _reserve(rid)


def _reserve(rid):
    r = one("SELECT * FROM returns WHERE id=?", (rid,))
    o = core.order(r["order_id"])
    hubs = [o["hub1"]] + ([o["hub2"]] if o["allow_alt"] else [])
    got = lockers.auto_reserve(hubs, o["parcel"], o["id"], "return", 24)  # a NEW free compartment, never the old one by assumption
    if not got:
        run("UPDATE returns SET status='Awaiting Locker', updated=? WHERE id=?", (now(), rid))
        core.note(r["customer_id"], f"Return {rid}: no locker is free yet. We will notify you.")
        core.note_role("Admin", f"Return {rid} is waiting for a locker.")
        return True, "Approved, waiting for a locker."
    hub, lk = got
    run("UPDATE returns SET status='Locker Assigned', hub=?, locker=?, updated=? WHERE id=?", (hub, lk, now(), rid))
    exp = now() + 86400
    qrs.issue(o["id"], "CUSTOMER_RETURN", "Customer", o["customer_id"], exp, hub, lk)
    qrs.issue(o["id"], "HUB_ACCESS", "Customer", o["customer_id"], exp, hub, None)
    core.note(o["customer_id"], f"Return {rid}: locker {lk} at {core.hub_names()[hub]} is reserved. Use your Return QR within 24 hours.")
    return True, "Approved. A locker was reserved."


def on_return_deposit(oid):
    r = one("SELECT * FROM returns WHERE order_id=? AND status='Locker Assigned' ORDER BY created DESC LIMIT 1", (oid,))
    if not r:
        return
    lockers.occupy(r["hub"], r["locker"], "return_in")
    rider = riders.pick()
    run("UPDATE returns SET status='Return Deposited', rider_id=?, updated=? WHERE id=?", (rider, now(), r["id"]))
    o = core.order(oid)
    core.note(o["customer_id"], f"{r['id']}: return parcel deposited. A rider will collect it.")
    if rider:
        exp = now() + 172800
        qrs.issue(oid, "RIDER_RETURN", "Rider", rider, exp, r["hub"], r["locker"])
        qrs.issue(oid, "HUB_ACCESS", "Rider", rider, exp, r["hub"], None)
        core.note(rider, f"Return pickup task {oid}.")
    else:
        core.note_role("Admin", f"{r['id']}: no rider for the return pickup.")


def on_return_pickup(oid):
    r = one("SELECT * FROM returns WHERE order_id=? AND status='Return Deposited' ORDER BY created DESC LIMIT 1", (oid,))
    if not r:
        return
    lockers.release(r["hub"], r["locker"])
    run("UPDATE returns SET status='Return Collected', updated=? WHERE id=?", (now(), r["id"]))
    o = core.order(oid)
    core.note(o["seller_id"], f"{oid}: the return parcel is on its way to you.")
    core.note(o["customer_id"], f"{r['id']}: collected by the rider.")


def seller_inspect(rid, sid, ok):
    r = one("SELECT * FROM returns WHERE id=?", (rid,))
    o = core.order(r["order_id"]) if r else None
    if not r or o["seller_id"] != sid or r["status"] != "Return Collected":
        return False, "Not allowed now."
    if not ok:
        run("UPDATE returns SET status='Inspection Failed', updated=? WHERE id=?", (now(), rid))
        core.note_role("Admin", f"{rid}: seller reports a problem with the returned parcel.")
        core.note(r["customer_id"], f"{rid}: the seller reported a problem. Admin will review.")
        return True, "Reported to Admin."
    # seller fault: full refund; "Changed my mind": product price only (delivery and locker fee not refunded)
    kind = "full" if r["reason"] in config.SELLER_FAULT else "product"
    amt = orders.refund(o["id"], kind)
    orders.restock(o["id"])
    run("UPDATE returns SET status='Refunded', refund_amount=?, updated=? WHERE id=?", (amt, now(), rid))
    core.note(r["customer_id"], f"{rid}: simulated refund of Rs {amt:,} recorded.")
    core.audit(sid, f"Return {rid} inspected OK")
    return True, "Refund recorded (simulated)."


def admin_resolve_failed(rid, refund_it):
    r = one("SELECT * FROM returns WHERE id=?", (rid,))
    if not r or r["status"] != "Inspection Failed":
        return False, "Not allowed now."
    if refund_it:
        o = core.order(r["order_id"])
        kind = "full" if r["reason"] in config.SELLER_FAULT else "product"
        amt = orders.refund(o["id"], kind)
        run("UPDATE returns SET status='Refunded', refund_amount=?, updated=? WHERE id=?", (amt, now(), rid))
        core.note(r["customer_id"], f"{rid}: Admin approved a simulated refund of Rs {amt:,}.")
    else:
        run("UPDATE returns SET status='Closed', updated=? WHERE id=?", (now(), rid))
        core.note(r["customer_id"], f"{rid}: Admin closed the return without a refund.")
    return True, "Done."


def retry_waiting():
    for r in q("SELECT id FROM returns WHERE status='Awaiting Locker'"):
        _reserve(r["id"])


def for_customer(cid):
    return q("SELECT * FROM returns WHERE customer_id=? ORDER BY created DESC", (cid,))


def for_seller(sid):
    return q("SELECT r.* FROM returns r JOIN orders o ON o.id=r.order_id WHERE o.seller_id=? ORDER BY r.created DESC", (sid,))


def all_returns():
    return q("SELECT * FROM returns ORDER BY created DESC")

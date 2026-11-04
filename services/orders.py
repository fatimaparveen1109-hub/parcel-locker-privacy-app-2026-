"""Order lifecycle. Every function checks ownership and the allowed status transition on the server."""
import config
from db import q, one, run, tx, now, next_id
from services import core, lockers, riders, qr as qrs


# ---------- checkout ----------
def place_order(customer, cart, contact, hub1, hub2, allow_alt, timing):
    """cart: list of {product_id, size, qty}. One order = one seller. Stock is reserved inside a transaction."""
    if not cart:
        return None, "Your cart is empty."
    if hub1 == hub2:
        return None, "Choose two different hubs."
    if not all((contact.get(k) or "").strip() for k in ("name", "phone", "area", "street", "house")):
        return None, "Enter your name, phone and address."
    with tx():
        prods = {}
        for c in cart:
            p = one("SELECT * FROM products WHERE id=? AND active=1", (c["product_id"],))
            if not p or p["stock"] < c["qty"] or c["qty"] < 1:
                return None, f"Not enough stock for {p['name'] if p else 'an item'}."
            prods[c["product_id"]] = p
        sellers = {p["seller_id"] for p in prods.values()}
        if len(sellers) > 1:
            return None, "One order can contain items from one seller only."
        sub = sum(prods[c["product_id"]]["price"] * c["qty"] for c in cart)
        parcel = max((prods[c["product_id"]]["parcel"] for c in cart), key=lambda s: config.RANK[s])
        df, lf = core.isetting("delivery_fee"), core.isetting("locker_fee")
        oid = next_id("DLV")
        t = now()
        run("INSERT INTO orders(id,customer_id,seller_id,rider_id,status,pay_status,pay_timing,disp,hub1,hub2,allow_alt,hub,locker,parcel,"
            "product_total,delivery_fee,locker_fee,total,created,updated,rem24,rem6,declined,last_try) "
            "VALUES(?,?,?,NULL,'Order Placed','Payment Pending',?,NULL,?,?,?,NULL,NULL,?,?,?,?,?,?,?,0,0,'',0)",
            (oid, customer["id"], sellers.pop(), timing, hub1, hub2, 1 if allow_alt else 0, parcel, sub, df, lf, sub + df + lf, t, t))
        for c in cart:
            p = prods[c["product_id"]]
            run("INSERT INTO order_items VALUES(?,?,?,?,?)", (oid, p["id"], c.get("size") or "", c["qty"], p["price"]))
            run("UPDATE products SET stock=stock-? WHERE id=?", (c["qty"], p["id"]))
        addr = ", ".join(x for x in (contact["house"], contact["street"], contact.get("block"), contact["area"], contact.get("landmark")) if x)
        run("INSERT INTO order_private VALUES(?,?,?,?)", (oid, contact["name"].strip(), contact["phone"].strip(), addr))
        run("INSERT INTO events(order_id,status,actor,ts) VALUES(?,?,?,?)", (oid, "Order Placed", customer["id"], t))
    o = core.order(oid)
    core.note(o["seller_id"], f"New order {oid}.")
    core.tell_customer(o, "order placed.")
    core.audit(customer["id"], f"{oid} placed")
    return oid, ""


# ---------- payment (SIMULATED) ----------
def pay(oid, customer_id, method, simulate_fail=False, idem=None):
    with tx():
        o = core.order(oid)
        if not o or o["customer_id"] != customer_id:
            return False, "Order not found."
        if o["status"] in ("Cancelled", "Rejected"):
            return False, "This order is closed."
        if o["pay_status"] == "Paid":
            return False, "Already paid."
        if idem and one("SELECT 1 FROM payments WHERE idem=?", (idem,)):
            return False, "Duplicate click ignored."
        if one("SELECT COUNT(*) n FROM payments WHERE order_id=? AND status='Failed'", (oid,))["n"] >= 3:
            return False, "Too many failed attempts. Please contact support."
        ok = not simulate_fail
        run("INSERT INTO payments VALUES(?,?,?,?,?,?,?)", (next_id("TXN"), oid, method, o["total"], "Success" if ok else "Failed", idem, now()))
        run("UPDATE orders SET pay_status=?, updated=? WHERE id=?", ("Paid" if ok else "Payment Failed", now(), oid))
    o = core.order(oid)
    if not ok:
        core.tell_customer(o, "payment failed. You can retry.")
        return False, "Payment failed (simulated). You can retry."
    core.tell_customer(o, "payment verified.")
    core.note(o["seller_id"], f"{oid}: payment verified.")
    core.audit(customer_id, f"{oid} payment success")
    if o["status"] == "Parcel Deposited":
        _make_ready(o)
    return True, "Payment successful (simulated)."


def _make_ready(o):
    core.set_status(o["id"], "Ready for Customer Pickup", "System")
    qrs.issue(o["id"], "CUSTOMER_PICKUP", "Customer", o["customer_id"], o["expires_at"], o["hub"], o["locker"])
    qrs.issue(o["id"], "HUB_ACCESS", "Customer", o["customer_id"], o["expires_at"], o["hub"], None)
    core.tell_customer(o, "your pickup QR is now active.")


def refund(oid, kind="full"):
    o = core.order(oid)
    amt = o["total"] if kind == "full" else o["product_total"]
    run("INSERT INTO payments VALUES(?,?,?,?,?,?,?)", (next_id("TXN"), oid, "Refund (simulated)", -amt, "Refunded", None, now()))
    run("UPDATE orders SET refund_type=? WHERE id=?", (kind, oid))
    return amt


def restock(oid):
    for i in q("SELECT * FROM order_items WHERE order_id=?", (oid,)):
        run("UPDATE products SET stock=stock+? WHERE id=?", (i["qty"], i["product_id"]))


def cancel(oid, actor, who="Customer"):
    o = core.order(oid)
    if who == "Customer" and o["status"] != "Order Placed":
        return False, "You can cancel only before the seller accepts. Contact support."
    if o["status"] in config.DONE:
        return False, "This order is already closed."
    with tx():
        restock(oid)
        core.set_status(oid, "Cancelled", actor)
        if o["locker"]:
            lockers.release(o["hub"], o["locker"])
        if o["pay_status"] == "Paid":
            refund(oid)
    core.tell_customer(o, "cancelled." + (" A simulated refund was recorded." if o["pay_status"] == "Paid" else ""))
    return True, "Order cancelled."


# ---------- seller ----------
def _own(oid, seller_id):
    o = core.order(oid)
    return o if o and o["seller_id"] == seller_id else None


def seller_accept(oid, sid):
    o = _own(oid, sid)
    if not o or o["status"] != "Order Placed":
        return False, "Not allowed now."
    core.set_status(oid, "Accepted", sid)
    core.tell_customer(o, "the seller accepted your order.")
    return True, "Accepted."


def seller_reject(oid, sid, reason):
    o = _own(oid, sid)
    if not o or o["status"] != "Order Placed" or not (reason or "").strip():
        return False, "Enter a reason for a new order."
    with tx():
        restock(oid)
        core.set_status(oid, "Rejected", sid)
        if o["pay_status"] == "Paid":
            refund(oid)
    core.tell_customer(o, f"the seller rejected your order. Reason: {reason.strip()}." + (" A simulated refund was recorded." if o["pay_status"] == "Paid" else ""))
    return True, "Rejected."


def seller_prepare(oid, sid):
    o = _own(oid, sid)
    if not o or o["status"] != "Accepted":
        return False, "Not allowed now."
    core.set_status(oid, "Preparing", sid)
    return True, "Preparing."


def seller_ready(oid, sid, disp):
    o = _own(oid, sid)
    if not o or o["status"] != "Preparing" or disp not in ("rider", "drop"):
        return False, "Not allowed now."
    run("UPDATE orders SET disp=? WHERE id=?", (disp, oid))
    core.set_status(oid, "Ready for Dispatch", sid)
    if disp == "rider":
        riders.assign_order(oid)
    else:
        core.set_status(oid, "Awaiting Drop-off", sid)
        core.tell_customer(o, "the seller will drop your parcel at the collection point.")
    return True, "Ready for dispatch."


def seller_dropped(oid, sid):
    o = _own(oid, sid)
    if not o or o["status"] != "Awaiting Drop-off":
        return False, "Not allowed now."
    core.set_status(oid, "Ready for Dispatch", sid)
    riders.assign_order(oid)
    return True, "Drop-off confirmed."


# ---------- rider ----------
def _mine(oid, rid):
    o = core.order(oid)
    return o if o and o["rider_id"] == rid else None


def rider_accept(oid, rid):
    o = _mine(oid, rid)
    if not o or o["status"] != "Rider Assigned":
        return False, "Not allowed now."
    core.set_status(oid, "Awaiting Pickup", rid)
    return True, "Task accepted."


def rider_decline(oid, rid):
    o = _mine(oid, rid)
    if not o or o["status"] != "Rider Assigned":
        return False, "Not allowed now."
    run("UPDATE orders SET declined=?, rider_id=NULL WHERE id=?", ((o["declined"] or "") + "," + rid, oid))
    riders.assign_order(oid)
    return True, "Declined. The task was reassigned."


def rider_pickup(oid, rid):
    o = _mine(oid, rid)
    if not o or o["status"] != "Awaiting Pickup":
        return False, "Accept the task first."
    core.set_status(oid, "In Transit", rid)
    core.tell_customer(o, "your parcel is on the way.")
    return True, "In transit."


def suggest(oid):
    """Compatible free lockers, primary hub first. Alternative hub only if the customer allowed it."""
    o = core.order(oid)
    out = []
    for k, hid in enumerate([o["hub1"], o["hub2"]] if o["allow_alt"] else [o["hub1"]]):
        for c in lockers.candidates(hid, o["parcel"]):
            out.append({"hub": hid, "locker": c["id"], "size": c["size"], "alt": k == 1})
        if out:
            break  # use the alternative only if the primary has no space
    return out


def assign_locker(oid, rid, hub, locker):
    """Rider picks the final locker. Reservation is atomic. Assignment is NOT deposit."""
    o = _mine(oid, rid)
    if not o or o["status"] not in ("In Transit", "Awaiting Locker"):
        return False, "Not allowed now."
    allowed = [o["hub1"]] + ([o["hub2"]] if o["allow_alt"] else [])
    if hub not in allowed:
        return False, "That hub is not allowed by the customer."
    if not lockers.reserve(hub, locker, oid, "delivery", core.isetting("reserve_hours")):
        return False, "That locker was just taken. Pick another."
    run("UPDATE orders SET hub=?, locker=?, reserve_until=? WHERE id=?", (hub, locker, now() + core.isetting("reserve_hours") * 3600, oid))
    core.set_status(oid, "Locker Assigned", rid)
    exp = now() + core.isetting("reserve_hours") * 3600
    qrs.issue(oid, "RIDER_DELIVERY", "Rider", rid, exp, hub, locker)
    qrs.issue(oid, "HUB_ACCESS", "Rider", rid, exp, hub, None)
    names = core.hub_names()
    extra = " Your first hub had no free locker, so your second hub is used." if hub != o["hub1"] else ""
    core.tell_customer(o, f"locker {locker} at {names[hub]} was assigned.{extra}")
    return True, f"Locker {locker} at {names[hub]} assigned."


def try_auto_locker(oid):
    """Used when a reservation expires or a locker is faulty: retry automatically; otherwise wait."""
    o = core.order(oid)
    hubs = [o["hub1"]] + ([o["hub2"]] if o["allow_alt"] else [])
    got = lockers.auto_reserve(hubs, o["parcel"], oid, "delivery", core.isetting("reserve_hours"))
    if not got:
        if o["status"] != "Awaiting Locker":
            core.set_status(oid, "Awaiting Locker", "System")
            core.tell_customer(o, "no locker is free at your allowed hubs. Dispatch is paused until one is free.")
            core.note_role("Admin", f"{oid}: awaiting locker.")
        return False
    hub, lk = got
    run("UPDATE orders SET hub=?, locker=?, reserve_until=? WHERE id=?", (hub, lk, now() + core.isetting("reserve_hours") * 3600, oid))
    core.set_status(oid, "Locker Assigned", "System")
    exp = now() + core.isetting("reserve_hours") * 3600
    qrs.issue(oid, "RIDER_DELIVERY", "Rider", o["rider_id"], exp, hub, lk)
    qrs.issue(oid, "HUB_ACCESS", "Rider", o["rider_id"], exp, hub, None)
    core.tell_customer(o, f"locker {lk} at {core.hub_names()[hub]} was assigned.")
    core.note(o["rider_id"], f"{oid}: new locker {lk} at {core.hub_names()[hub]}.")
    return True


def report_locker_issue(oid, rid, text):
    o = _mine(oid, rid)
    if not o or not o["locker"] or o["status"] != "Locker Assigned":
        return False, "No locker is assigned."
    lockers.release(o["hub"], o["locker"])
    lockers.set_off(o["hub"], o["locker"], True)
    run("UPDATE qr_codes SET active=0 WHERE order_id=? AND used=0", (oid,))
    run("UPDATE orders SET hub=NULL, locker=NULL WHERE id=?", (oid,))
    core.set_status(oid, "In Transit", rid)
    core.note_role("Admin", f"{oid}: locker {o['locker']} reported ({text or 'problem'}). It was marked unavailable.")
    core.tell_customer(o, "the assigned locker had a problem. We are finding another one.")
    try_auto_locker(oid)
    return True, "Reported. A new locker is being found."


# ---------- steps triggered by the door-closed confirmation (see services/qr.finish) ----------
def on_deposit(oid):
    o = core.order(oid)
    if o["status"] != "Locker Assigned":
        return
    t = now()
    lockers.occupy(o["hub"], o["locker"], "occupied")
    run("UPDATE orders SET deposited_at=?, expires_at=?, reserve_until=NULL WHERE id=?", (t, t + core.isetting("pickup_hours") * 3600, oid))
    core.set_status(oid, "Parcel Deposited", o["rider_id"])
    o = core.order(oid)
    names = core.hub_names()
    core.tell_customer(o, f"your parcel is in locker {o['locker']} at {names[o['hub']]}. Collect it within {core.isetting('pickup_hours')} hours.")
    core.note(o["seller_id"], f"{oid}: deposited in a locker.")
    if o["pay_status"] == "Paid":
        _make_ready(o)
    else:
        core.tell_customer(o, "payment is due. Pay now to activate your pickup QR.")


def on_collect(oid):
    o = core.order(oid)
    if o["status"] != "Ready for Customer Pickup":
        return
    lockers.release(o["hub"], o["locker"])
    run("UPDATE orders SET collected_at=? WHERE id=?", (now(), oid))
    core.set_status(oid, "Collected", o["customer_id"])
    core.tell_customer(o, "collected. Thank you.")
    core.note(o["seller_id"], f"{oid}: collected by the customer.")


# ---------- reads that respect privacy ----------
def customer_orders(cid):
    return q("SELECT * FROM orders WHERE customer_id=? ORDER BY created DESC", (cid,))


def seller_orders(sid):
    """No phone, no address. Customer NAME is allowed for sellers."""
    return q("SELECT o.id,o.status,o.pay_status,o.parcel,o.hub1,o.hub2,o.disp,o.product_total,o.delivery_fee,o.locker_fee,o.total,o.created,p.cname AS customer_name "
             "FROM orders o JOIN order_private p ON p.order_id=o.id WHERE o.seller_id=? ORDER BY o.created DESC", (sid,))


def rider_tasks(rid):
    """Delivery ID, parcel size, pickup point, hub and locker only. No name, phone, address or product details."""
    return q("SELECT id,status,parcel,hub,locker,disp,seller_id FROM orders WHERE rider_id=? ORDER BY created DESC", (rid,))


def admin_orders():
    return q("SELECT * FROM orders ORDER BY created DESC")


def private_of(oid, masked=True):
    p = one("SELECT * FROM order_private WHERE order_id=?", (oid,)) or {}
    if masked and p:
        return {"cname": p["cname"], "phone": core.mask_phone(p["phone"]), "address": "(hidden)"}
    return p


def receipt_html(oid):
    o = core.order(oid)
    rows = "".join(f"<tr><td>{i['name']}</td><td>{i['size'] or '-'}</td><td>{i['qty']}</td><td>Rs {i['unit_price']:,}</td><td>Rs {i['unit_price']*i['qty']:,}</td></tr>" for i in core.items_of(oid))
    return (f"<html><body style='font-family:Arial'><h2>Receipt {oid}</h2><table border='1' cellpadding='6' cellspacing='0'>"
            f"<tr><th>Item</th><th>Size</th><th>Qty</th><th>Price</th><th>Amount</th></tr>{rows}"
            f"<tr><td colspan='4'>Delivery fee</td><td>Rs {o['delivery_fee']:,}</td></tr><tr><td colspan='4'>Locker fee</td><td>Rs {o['locker_fee']:,}</td></tr>"
            f"<tr><td colspan='4'><b>Total</b></td><td><b>Rs {o['total']:,}</b></td></tr></table><p>Payment: {o['pay_status']} (simulated)</p></body></html>")

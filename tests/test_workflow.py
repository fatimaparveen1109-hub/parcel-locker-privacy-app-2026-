"""End-to-end test of the shared workflow (services only). Run:  python tests/test_workflow.py
Uses a temporary local SQLite file; never touches your Supabase database."""
import os
import sys
import tempfile

os.environ.pop("DATABASE_URL", None)
os.environ["PPL_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["DEMO_MODE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import config
from db import q, one
from services import auth, core, orders, returns, wallets, housekeeping, riders, lockers, qr, comms

FAILS = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def scan_flow(order_id, qtype_access, qtype, who_id, hub, locker, role, qtype_holder_pin=False):
    a = qr.current(order_id, "HUB_ACCESS", who_id)
    ra = qr.verify(a["text"], hub, None)
    r = qr.verify(qr.current(order_id, qtype, who_id)["text"], hub, locker)
    return ra, r


def test_full_workflow():
    ok(db.one("SELECT COUNT(*) n FROM users")["n"] == 6, "seed: admin + 2 sellers + 3 riders")
    ok(db.one("SELECT COUNT(*) n FROM products")["n"] == 8, "seed: 8 products")
    ok(db.one("SELECT COUNT(*) n FROM hubs")["n"] == 5, "seed: 5 hubs")
    # accounts
    uid, err = auth.register("Customer", "Amna", "amna@x.com", "03001234567", "secret1")
    ok(uid and uid.startswith("CUS"), "customer registered " + str(uid))
    u, err = auth.login("Customer", "amna@x.com", "secret1")
    ok(u and u["id"] == uid, "customer logs in again with the same account")
    ok(auth.login("Seller", "amna@x.com", "secret1")[0] is None, "a customer email cannot log in as Seller")
    ok(auth.register("Seller", "X", "amna@x.com", "", "secret1")[0] is None, "one email = one account")
    sid, _ = auth.register("Seller", "New Seller", "ns@x.com", "", "secret1")
    ok(auth.login("Seller", "ns@x.com", "secret1")[0] is None, "pending seller cannot log in")
    auth.set_user_status(sid, "active")
    ok(auth.login("Seller", "ns@x.com", "secret1")[0] is not None, "approved seller can log in")
    for _ in range(5):
        auth.login("Admin", config.ADMIN_EMAIL, "wrong")
    ok("locked" in auth.login("Admin", config.ADMIN_EMAIL, config.ADMIN_PASSWORD)[1], "admin locked after 5 failures")
    db.meta_set("admin_lock", 0)
    ok(auth.login("Admin", config.ADMIN_EMAIL, config.ADMIN_PASSWORD)[0] is not None, "admin login works")
    cust = auth.get(uid)
    # order: shoes (Noor Fashion SEL-002), pay later
    shoes = one("SELECT * FROM products WHERE name='Running Shoes'")
    contact = {"name": "Amna", "phone": "03001234567", "area": "DHA", "block": "Phase 6", "street": "St 1", "house": "12", "landmark": ""}
    oid, err = orders.place_order(cust, [{"product_id": shoes["id"], "size": "42", "qty": 2}], contact, "H-DHA", "H-CLF", True, "later")
    o = core.order(oid)
    ok(oid and o["total"] == 13000 + 90 and o["seller_id"] == "SEL-002", "order placed total %s" % (o and o["total"]))
    ok(one("SELECT stock FROM products WHERE id=?", (shoes["id"],))["stock"] == 38, "stock reserved")
    mix = orders.place_order(cust, [{"product_id": shoes["id"], "size": "42", "qty": 1}, {"product_id": 1, "size": "", "qty": 1}], contact, "H-DHA", "H-CLF", True, "later")
    ok(mix[0] is None, "mixed-seller cart refused")
    so = orders.seller_orders("SEL-002")[0]
    ok("phone" not in so and "address" not in so and so["customer_name"] == "Amna", "seller sees name only, no phone or address")
    # seller flow
    ok(orders.seller_accept(oid, "SEL-001")[0] is False, "another seller cannot accept")
    orders.seller_accept(oid, "SEL-002")
    orders.seller_prepare(oid, "SEL-002")
    ok(orders.seller_ready(oid, "SEL-002", "rider")[0], "ready for dispatch")
    o = core.order(oid)
    ok(o["status"] == "Rider Assigned" and o["rider_id"].startswith("RID-"), "auto-assigned " + str(o["rider_id"]))
    rid = o["rider_id"]
    rt = orders.rider_tasks(rid)[0]
    ok(set(rt.keys()) == {"id", "status", "parcel", "hub", "locker", "disp", "seller_id"}, "rider sees only task fields")
    ok(orders.rider_pickup(oid, rid)[0] is False, "must accept before pickup")
    orders.rider_accept(oid, rid)
    orders.rider_pickup(oid, rid)
    sug = orders.suggest(oid)
    ok(sug and sug[0]["hub"] == "H-DHA" and not sug[0]["alt"], "suggests primary hub first")
    ok(orders.assign_locker(oid, rid, "H-SDR", "L1")[0] is False, "hub not chosen by customer is refused")
    ok(orders.assign_locker(oid, rid, sug[0]["hub"], sug[0]["locker"])[0], "locker assigned")
    o = core.order(oid)
    ok(o["status"] == "Locker Assigned" and o["parcel"] == "M" and one("SELECT size FROM lockers WHERE hub_id=? AND id=?", (o["hub"], o["locker"]))["size"] in ("M", "L"), "compatible size locker")
    ok(lockers.reserve(o["hub"], o["locker"], "OTHER", "delivery", 1) is False, "one compartment cannot hold two orders")
    # QR: rules
    deliver = qr.current(oid, "RIDER_DELIVERY", rid)
    access = qr.current(oid, "HUB_ACCESS", rid)
    ok(deliver["text"].startswith("PPL|RIDER_DELIVERY|" + oid + "|") and len(deliver["pin"]) == 6, "real QR text + 6 digit PIN")
    r = qr.verify(deliver["text"], o["hub"], o["locker"])
    ok(r["result"] == "NO_HUB_ACCESS", "locker QR refused without hub room access")
    ok(qr.verify(access["text"], "H-CLF", None)["result"] == "WRONG_LOCKER", "room QR refused at the wrong hub")
    ok(qr.verify(access["text"], o["hub"], None)["result"] == "VALID", "hub room QR valid")
    ok(qr.verify(access["text"], o["hub"], None)["result"] == "ALREADY_USED", "room QR is single use")
    ok(qr.verify(deliver["text"], o["hub"], "L9")["result"] == "WRONG_LOCKER", "wrong locker refused")
    r = qr.verify(deliver["text"], o["hub"], o["locker"])
    ok(r["result"] == "VALID", "delivery QR valid after room access")
    ok(core.order(oid)["status"] == "Locker Assigned", "scan alone does not deposit")
    ok(qr.finish(r["qr_id"])[0], "door closed confirms deposit")
    o = core.order(oid)
    ok(o["status"] == "Parcel Deposited" and o["expires_at"] - o["deposited_at"] == 48 * 3600, "deposited with 48h window")
    ok(qr.finish(r["qr_id"])[0] is False, "confirmation works only once")
    ok(qr.current(oid, "CUSTOMER_PICKUP", uid) is None, "pickup QR not issued before payment")
    # payment
    ok(orders.pay(oid, uid, "Demo Card", True, "k1")[0] is False and core.order(oid)["pay_status"] == "Payment Failed", "failed payment, retry possible")
    ok(orders.pay(oid, "CUS-9999", "Demo Card")[0] is False, "other customer cannot pay my order")
    ok(orders.pay(oid, uid, "Demo Card", False, "k2")[0], "payment succeeds on retry")
    o = core.order(oid)
    ok(o["status"] == "Ready for Customer Pickup", "paid -> ready for pickup")
    pk, ac = qr.current(oid, "CUSTOMER_PICKUP", uid), qr.current(oid, "HUB_ACCESS", uid)
    ok(pk and ac and pk["text"] != deliver["text"], "customer QR differs from rider QR")
    ok(qr.verify(pk["text"], o["hub"], o["locker"])["result"] == "NO_HUB_ACCESS", "pickup needs room access first")
    ok(qr.verify(ac["text"], o["hub"], None)["result"] == "VALID", "customer room QR valid")
    for i in range(5):
        qr.verify("PPL|CUSTOMER_PICKUP|%s|wrongtoken" % oid, o["hub"], o["locker"])
    ok(qr.verify(pk["text"], o["hub"], o["locker"])["result"] == "TOO_MANY_ATTEMPTS", "5 wrong attempts lock the QR")
    newpk = qr.issue(oid, "CUSTOMER_PICKUP", "Customer", uid, o["expires_at"], o["hub"], o["locker"])
    ok(newpk["text"] != pk["text"], "regenerated QR is different")
    ok(qr.verify(pk["text"], o["hub"], o["locker"])["result"] in ("INVALID",), "old QR no longer works")
    pin = qr.verify(newpk["pin"], o["hub"], o["locker"], oid)
    ok(pin["result"] == "VALID", "PIN fallback works")
    ok(qr.finish(pin["qr_id"])[0], "pickup confirmed")
    o = core.order(oid)
    ok(o["status"] == "Collected" and one("SELECT order_id FROM lockers WHERE hub_id=? AND id=?", (o["hub"], o["locker"]))["order_id"] is None, "collected and locker freed")
    ok(qr.verify(newpk["text"], o["hub"], o["locker"])["result"] == "ALREADY_USED", "pickup QR cannot be reused")
    # wallets
    ws, wr = wallets.wallet("Seller", "SEL-002"), wallets.wallet("Rider", rid)
    ok(ws["pending"] == 13000 and ws["available"] == 0, "seller money pending during return window")
    ok(wr["available"] == 30, "rider money available after deposit")
    # return flow
    ok(returns.request(uid, oid, "Damaged", "box broken", None)[0] is None, "photo required for Damaged")
    rr, err = returns.request(uid, oid, "Damaged", "box broken", "aGVsbG8=")
    ok(rr, "return requested " + str(rr))
    ok(returns.request(uid, oid, "Damaged", "again", "aGVsbG8=")[0] is None, "no duplicate open return")
    returns.decide(rr, True, "ok")
    r1 = one("SELECT * FROM returns WHERE id=?", (rr,))
    ok(r1["status"] == "Locker Assigned" and r1["locker"], "return approved, locker reserved: %s %s" % (r1["hub"], r1["locker"]))
    cr, ca = qr.current(oid, "CUSTOMER_RETURN", uid), qr.current(oid, "HUB_ACCESS", uid)
    ok(qr.verify(ca["text"], r1["hub"], None)["result"] == "VALID", "return room access")
    v = qr.verify(cr["text"], r1["hub"], r1["locker"])
    ok(v["result"] == "VALID", "return QR valid")
    qr.finish(v["qr_id"])
    r1 = one("SELECT * FROM returns WHERE id=?", (rr,))
    ok(r1["status"] == "Return Deposited" and r1["rider_id"], "return deposited, rider " + str(r1["rider_id"]))
    rrid = r1["rider_id"]
    ra, rq = qr.current(oid, "HUB_ACCESS", rrid), qr.current(oid, "RIDER_RETURN", rrid)
    qr.verify(ra["text"], r1["hub"], None)
    v = qr.verify(rq["text"], r1["hub"], r1["locker"])
    ok(v["result"] == "VALID", "rider return QR valid")
    qr.finish(v["qr_id"])
    ok(one("SELECT status FROM returns WHERE id=?", (rr,))["status"] == "Return Collected", "return collected by rider")
    ok(returns.seller_inspect(rr, "SEL-001", True)[0] is False, "only the right seller inspects")
    ok(returns.seller_inspect(rr, "SEL-002", True)[0], "seller inspects OK")
    o = core.order(oid)
    ok(o["refund_type"] == "full" and one("SELECT stock FROM products WHERE id=?", (shoes["id"],))["stock"] == 40, "full refund + stock restored")
    ok(wallets.wallet("Seller", "SEL-002")["total"] == 0, "seller wallet reversed after refund")
    # second order: pay now, collect, return window releases money
    wm = one("SELECT * FROM products WHERE name='Wireless Earbuds'")
    o2, _ = orders.place_order(cust, [{"product_id": wm["id"], "size": "", "qty": 1}], contact, "H-DHA", "H-CLF", True, "now")
    orders.pay(o2, uid, "Demo Wallet Balance")
    orders.seller_accept(o2, "SEL-001"); orders.seller_prepare(o2, "SEL-001"); orders.seller_ready(o2, "SEL-001", "rider")
    r2 = core.order(o2)["rider_id"]
    orders.rider_accept(o2, r2); orders.rider_pickup(o2, r2)
    s = orders.suggest(o2)[0]
    orders.assign_locker(o2, r2, s["hub"], s["locker"])
    for t in ("HUB_ACCESS", "RIDER_DELIVERY"):
        c = qr.current(o2, t, r2)
        res = qr.verify(c["text"], s["hub"], s["locker"] if t != "HUB_ACCESS" else None)
    qr.finish(res["qr_id"])
    ok(core.order(o2)["status"] == "Ready for Customer Pickup", "pay-now order is ready right after deposit")
    ok(qr.current(o2, "CUSTOMER_PICKUP", uid) is not None, "pickup QR issued because it is paid")
    qa = qr.current(o2, "CUSTOMER_PICKUP", uid)
    ok(qa["text"] != newpk["text"], "every order has a different QR")
    # expiry
    db.set_offset(49)
    housekeeping.run_all(True)
    ok(core.order(o2)["status"] == "Expired (Admin Review)", "48h expiry -> Admin review")
    ok(qr.verify(qa["text"], s["hub"], s["locker"])["result"] in ("INVALID", "EXPIRED"), "expired QR rejected")
    ok(housekeeping.extend_pickup(o2, 24)[0] and core.order(o2)["status"] == "Ready for Customer Pickup", "admin extends, new QR issued")
    db.set_offset(0)
    # alternative hub / both full / retry
    for hid in ("H-DHA",):
        db.run("UPDATE lockers SET order_id='X', res_kind='occupied' WHERE hub_id=? AND order_id IS NULL", (hid,))
    shirt = one("SELECT * FROM products WHERE name='Cotton Shirt'")
    o3, _ = orders.place_order(cust, [{"product_id": shirt["id"], "size": "M", "qty": 1}], contact, "H-DHA", "H-CLF", True, "now")
    orders.pay(o3, uid, "Demo Card")
    orders.seller_accept(o3, "SEL-002"); orders.seller_prepare(o3, "SEL-002"); orders.seller_ready(o3, "SEL-002", "drop")
    ok(core.order(o3)["status"] == "Awaiting Drop-off", "seller drop-off method")
    orders.seller_dropped(o3, "SEL-002")
    r3 = core.order(o3)["rider_id"]
    orders.rider_accept(o3, r3); orders.rider_pickup(o3, r3)
    sg = orders.suggest(o3)
    ok(sg and sg[0]["hub"] == "H-CLF" and sg[0]["alt"], "alternative hub suggested when primary is full")
    o4, _ = orders.place_order(cust, [{"product_id": shirt["id"], "size": "S", "qty": 1}], contact, "H-DHA", "H-CLF", False, "now")
    orders.pay(o4, uid, "Demo Card")
    orders.seller_accept(o4, "SEL-002"); orders.seller_prepare(o4, "SEL-002"); orders.seller_ready(o4, "SEL-002", "rider")
    r4 = core.order(o4)["rider_id"]
    orders.rider_accept(o4, r4); orders.rider_pickup(o4, r4)
    ok(orders.suggest(o4) == [], "no alternative when the customer did not allow it")
    ok(orders.try_auto_locker(o4) is False and core.order(o4)["status"] == "Awaiting Locker", "awaiting locker when primary is full")
    db.run("UPDATE lockers SET order_id=NULL, res_kind=NULL WHERE order_id='X'")
    housekeeping.run_all(True)
    ok(core.order(o4)["status"] == "Locker Assigned", "housekeeping assigns a locker once one is free")
    # complaints, chat privacy
    ok(comms.send("seller", uid, o3, "Customer", uid, "call me 0300 1234567")[0] is False, "phone number blocked in chat")
    ok(comms.send("seller", uid, o3, "Customer", uid, "Is it ready?")[0], "normal chat message sent")
    tid, _ = comms.new_ticket(uid, o3, "Delivery issue", "late")
    ok(tid, "complaint ticket " + str(tid))
    ok(core.unread_count(uid) > 0 and core.unread_count("CUS-1999") == 0, "notifications are per user")
    # cancel + accept timeout
    o5, _ = orders.place_order(cust, [{"product_id": shirt["id"], "size": "L", "qty": 1}], contact, "H-DHA", "H-CLF", True, "now")
    ok(orders.cancel(o5, uid)[0], "customer cancels before acceptance")
    o6, _ = orders.place_order(cust, [{"product_id": shirt["id"], "size": "L", "qty": 1}], contact, "H-DHA", "H-CLF", True, "later")
    db.set_offset(13)
    housekeeping.run_all(True)
    ok(core.order(o6)["status"] == "Cancelled", "seller did not accept in 12h -> auto-cancel")
    db.set_offset(0)
    ok(wallets.payout("Rider", rid)[0] in (True, False), "payout function runs")
    print("\nFAILS:", FAILS if FAILS else "none")
    assert not FAILS


if __name__ == "__main__":
    test_full_workflow()
    print("ALL PASS")

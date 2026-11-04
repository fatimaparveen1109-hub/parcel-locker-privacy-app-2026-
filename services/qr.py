"""QR and PIN engine. Real, scannable QR text:  PPL|TYPE|ORDER_ID|TOKEN
Every QR is new and different (random nonce). Only SHA-256 hashes are stored; the raw token is re-derived on the server
(HMAC with APP_SECRET) so it can be shown again to its rightful holder without being stored in plain text.
All checks happen on the server. verify() is a pure function of the database, so it can later become the real /scan API."""
import hmac
import hashlib
import secrets
import segno
import io

import config
from db import q, one, run, now, sha
from integrations import LOCKER
from services import core, lockers

TYPES = ("HUB_ACCESS", "RIDER_DELIVERY", "CUSTOMER_PICKUP", "CUSTOMER_RETURN", "RIDER_RETURN")
LOCKER_TYPES = ("RIDER_DELIVERY", "CUSTOMER_PICKUP", "CUSTOMER_RETURN", "RIDER_RETURN")
ACCESS_WINDOW = 1800
MAX_ATTEMPTS = 5


def _d(what, nonce, oid, qtype):
    return hmac.new(config.APP_SECRET.encode(), f"{what}|{nonce}|{oid}|{qtype}".encode(), hashlib.sha256).hexdigest()


def _token(nonce, oid, qtype):
    return _d("t", nonce, oid, qtype)[:32]


def _pin(nonce, oid, qtype):
    return str(int(_d("p", nonce, oid, qtype)[:8], 16) % 1000000).zfill(6)


def text_of(row):
    return f"PPL|{row['qtype']}|{row['order_id']}|{_token(row['nonce'], row['order_id'], row['qtype'])}"


def pin_of(row):
    return _pin(row["nonce"], row["order_id"], row["qtype"])


def issue(order_id, qtype, holder_role, holder_id, expires, hub=None, locker=None):
    """Create a NEW QR (and PIN). Older unused QR for the same order, type and holder is invalidated."""
    run("UPDATE qr_codes SET active=0 WHERE order_id=? AND qtype=? AND holder_id=? AND used=0", (order_id, qtype, holder_id))
    nonce = secrets.token_hex(12)
    run("INSERT INTO qr_codes(order_id,qtype,holder_role,holder_id,nonce,token_hash,pin_hash,hub_id,locker_id,expires,used,done,attempts,active,created) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,0,0,0,1,?)",
        (order_id, qtype, holder_role, holder_id, nonce, sha(_token(nonce, order_id, qtype)), sha(order_id + _pin(nonce, order_id, qtype)),
         hub, locker, int(expires), now()))
    core.audit("System", f"QR issued {qtype} for {order_id}")
    return current(order_id, qtype, holder_id)


def current(order_id, qtype, holder_id):
    """The newest QR for this holder, with raw text and PIN (only the holder's own page may call this)."""
    r = one("SELECT * FROM qr_codes WHERE order_id=? AND qtype=? AND holder_id=? ORDER BY id DESC LIMIT 1", (order_id, qtype, holder_id))
    if not r:
        return None
    return {"id": r["id"], "text": text_of(r), "pin": pin_of(r), "used": bool(r["used"]), "active": bool(r["active"]),
            "expired": r["expires"] < now(), "expires": r["expires"], "type": qtype, "hub": r["hub_id"], "locker": r["locker_id"]}


def png_bytes(text):
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=8, border=2)
    return buf.getvalue()


def svg_inline(text):
    return segno.make(text, error="m").svg_inline(scale=4, dark="#0F172A", light="#FFFFFF", border=1)


def _log(oid, qtype, role, hub, locker, result, detail=""):
    run("INSERT INTO scans(ts,order_id,qtype,role,hub_id,locker_id,result,detail) VALUES(?,?,?,?,?,?,?,?)",
        (now(), oid, qtype, role, hub, locker, result, detail))
    if result not in ("VALID",):
        core.audit("Scanner", f"Rejected scan {result} {qtype or ''} {oid or ''}")


def _has_access(oid, role, hub):
    return bool(one("SELECT 1 FROM scans WHERE order_id=? AND qtype='HUB_ACCESS' AND result='VALID' AND role=? AND hub_id=? AND ts>?",
                    (oid, role, hub, now() - ACCESS_WINDOW)))


def _state_ok(qtype, o, rt):
    if qtype == "RIDER_DELIVERY":
        return o["status"] == "Locker Assigned"
    if qtype == "CUSTOMER_PICKUP":
        return o["status"] == "Ready for Customer Pickup"
    if qtype == "CUSTOMER_RETURN":
        return bool(rt) and rt["status"] == "Locker Assigned"
    if qtype == "RIDER_RETURN":
        return bool(rt) and rt["status"] == "Return Deposited"
    return True


def verify(scanned, hub_id, locker_id, order_id=None):
    """Result codes: VALID, INVALID, EXPIRED, ALREADY_USED, PAYMENT_PENDING, WRONG_LOCKER, NO_HUB_ACCESS, NOT_READY, TOO_MANY_ATTEMPTS."""
    scanned = (scanned or "").strip()
    rows = []
    if scanned.startswith("PPL|"):
        parts = scanned.split("|")
        if len(parts) != 4 or parts[1] not in TYPES:
            _log(None, None, None, hub_id, locker_id, "INVALID", "bad format")
            return {"result": "INVALID", "message": "This is not a valid locker QR."}
        _, qtype, oid, token = parts
        r = one("SELECT * FROM qr_codes WHERE order_id=? AND qtype=? AND token_hash=?", (oid, qtype, sha(token)))
        if not r:
            for w in q("SELECT id FROM qr_codes WHERE order_id=? AND qtype=? AND active=1 AND used=0", (oid, qtype)):
                run("UPDATE qr_codes SET attempts=attempts+1 WHERE id=?", (w["id"],))
            _log(oid, qtype, None, hub_id, locker_id, "INVALID", "wrong token")
            return {"result": "INVALID", "message": "Wrong or unknown QR."}
        if not r["active"] and not r["used"]:
            _log(oid, qtype, r["holder_role"], hub_id, locker_id, "INVALID", "replaced")
            return {"result": "INVALID", "message": "This QR was replaced by a newer one."}
        if r["attempts"] >= MAX_ATTEMPTS and not r["used"]:
            _log(oid, qtype, r["holder_role"], hub_id, locker_id, "TOO_MANY_ATTEMPTS")
            return {"result": "TOO_MANY_ATTEMPTS", "message": "Too many wrong attempts. Regenerate the QR."}
    else:  # PIN fallback: needs the order id
        if not order_id or not scanned.isdigit():
            return {"result": "INVALID", "message": "Enter the Order ID and the 6-digit PIN."}
        oid = order_id.strip()
        r = None
        for c in q("SELECT * FROM qr_codes WHERE order_id=? AND active=1 ORDER BY id DESC", (oid,)):
            if hmac.compare_digest(sha(oid + scanned), c["pin_hash"]):
                r = c
                break
        if not r:
            wrong = q("SELECT id FROM qr_codes WHERE order_id=? AND active=1 AND used=0", (oid,))
            for w in wrong:
                run("UPDATE qr_codes SET attempts=attempts+1 WHERE id=?", (w["id"],))
            _log(oid, None, None, hub_id, locker_id, "INVALID", "wrong pin")
            return {"result": "INVALID", "message": "Wrong PIN."}
        if r["attempts"] >= MAX_ATTEMPTS and not r["used"]:
            _log(oid, r["qtype"], r["holder_role"], hub_id, locker_id, "TOO_MANY_ATTEMPTS")
            return {"result": "TOO_MANY_ATTEMPTS", "message": "Too many wrong attempts."}
        qtype = r["qtype"]

    def deny(code, msg):
        _log(oid, qtype, r["holder_role"], hub_id, locker_id, code)
        return {"result": code, "message": msg, "qtype": qtype, "order_id": oid}

    if r["used"]:
        return deny("ALREADY_USED", "This QR was already used.")
    if not r["active"]:
        return deny("INVALID", "This QR was replaced by a newer one.")
    if r["expires"] < now():
        return deny("EXPIRED", "This QR has expired.")
    o = core.order(oid)
    rt = one("SELECT * FROM returns WHERE order_id=? ORDER BY created DESC LIMIT 1", (oid,))
    if qtype == "CUSTOMER_PICKUP" and o["pay_status"] != "Paid":
        return deny("PAYMENT_PENDING", "Payment is not verified. The locker stays closed.")
    if r["hub_id"] and hub_id and r["hub_id"] != hub_id:
        return deny("WRONG_LOCKER", "This QR is for a different hub.")
    if qtype in LOCKER_TYPES and r["locker_id"] and locker_id and r["locker_id"] != locker_id:
        return deny("WRONG_LOCKER", "This QR is for a different locker.")
    if not _state_ok(qtype, o, rt):
        return deny("NOT_READY", "This order is not at the right step for this QR.")
    if qtype in LOCKER_TYPES and not _has_access(oid, r["holder_role"], r["hub_id"]):
        return deny("NO_HUB_ACCESS", "Scan the hub room access QR first.")
    run("UPDATE qr_codes SET used=1 WHERE id=? AND used=0", (r["id"],))
    _log(oid, qtype, r["holder_role"], r["hub_id"], r["locker_id"], "VALID")
    opened = LOCKER.unlock(r["hub_id"], r["locker_id"]) if qtype in LOCKER_TYPES else True
    return {"result": "VALID", "message": "Locker %s is OPEN (simulated)." % (r["locker_id"] or "door") if opened else "Locker did not respond.",
            "qtype": qtype, "order_id": oid, "qr_id": r["id"], "hub": r["hub_id"], "locker": r["locker_id"]}


def finish(qr_id):
    """Called when the door sensor / 'Door closed' button confirms. Moves the order forward exactly once."""
    from services import orders, returns
    r = one("SELECT * FROM qr_codes WHERE id=?", (qr_id,))
    if not r or not r["used"] or r["done"]:
        return False, "Nothing to confirm."
    run("UPDATE qr_codes SET done=1 WHERE id=? AND done=0", (qr_id,))
    t = r["qtype"]
    if t == "RIDER_DELIVERY":
        orders.on_deposit(r["order_id"])
    elif t == "CUSTOMER_PICKUP":
        orders.on_collect(r["order_id"])
    elif t == "CUSTOMER_RETURN":
        returns.on_return_deposit(r["order_id"])
    elif t == "RIDER_RETURN":
        returns.on_return_pickup(r["order_id"])
    return True, "Door closed. Status updated."


def recent_scans(limit=50, order_id=None):
    if order_id:
        return q("SELECT * FROM scans WHERE order_id=? ORDER BY id DESC LIMIT ?", (order_id, limit))
    return q("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,))

"""Small helpers shared by every service: settings, notifications, audit, order events."""
import config
from db import q, one, run, now


def setting(k):
    r = one("SELECT v FROM settings WHERE k=?", (k,))
    return r["v"] if r else config.DEFAULTS[k]


def isetting(k):
    return int(setting(k))


def set_setting(k, v):
    run("UPDATE settings SET v=? WHERE k=?", (str(v), k))


def note(user_id, text):
    if user_id:
        run("INSERT INTO notifications(user_id,body,seen,ts) VALUES(?,?,0,?)", (user_id, text, now()))


def note_role(role, text):
    for u in q("SELECT id FROM users WHERE role=? AND status='active'", (role,)):
        note(u["id"], text)


def audit(actor, text):
    run("INSERT INTO audit(ts,actor,body) VALUES(?,?,?)", (now(), actor, text))


def order(oid):
    return one("SELECT * FROM orders WHERE id=?", (oid,))


def set_status(oid, status, actor="System"):
    run("UPDATE orders SET status=?, updated=? WHERE id=?", (status, now(), oid))
    run("INSERT INTO events(order_id,status,actor,ts) VALUES(?,?,?,?)", (oid, status, actor, now()))
    audit(actor, f"{oid} -> {status}")


def tell_customer(o, text):
    note(o["customer_id"], f"{o['id']}: {text}")


def hub_names():
    return {h["id"]: h["name"] for h in q("SELECT * FROM hubs ORDER BY name")}


def items_of(oid):
    return q("SELECT i.*, p.name FROM order_items i JOIN products p ON p.id=i.product_id WHERE i.order_id=?", (oid,))


def mask_phone(p):
    p = p or ""
    return ("*" * max(0, len(p) - 3)) + p[-3:] if p else "-"


def mask_email(e):
    return e[:1] + "***" + e[e.find("@"):] if "@" in e else "***"


# ---------- notifications (per user) ----------
def unread_count(uid):
    return one("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND seen=0", (uid,))["n"]


def notes_of(uid, limit=100):
    return q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))


def mark_all_seen(uid):
    run("UPDATE notifications SET seen=1 WHERE user_id=?", (uid,))


def max_note_id(uid):
    return one("SELECT COALESCE(MAX(id),0) m FROM notifications WHERE user_id=?", (uid,))["m"]


def new_notes(uid, after_id):
    return q("SELECT * FROM notifications WHERE user_id=? AND id>? ORDER BY id", (uid, after_id))

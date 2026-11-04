import config
from db import q, one, run, now
from services import core


def load(rider_id):
    marks = ",".join("?" * len(config.ACTIVE_RIDER))
    a = one(f"SELECT COUNT(*) n FROM orders WHERE rider_id=? AND status IN ({marks})", (rider_id, *config.ACTIVE_RIDER))["n"]
    b = one("SELECT COUNT(*) n FROM returns WHERE rider_id=? AND status='Return Deposited'", (rider_id,))["n"]
    return a + b


def pick(exclude=()):
    cap = core.isetting("rider_capacity")
    best = None
    for r in q("SELECT id FROM users WHERE role='Rider' AND status='active'"):
        if r["id"] in exclude:
            continue
        n = load(r["id"])
        if n < cap and (best is None or n < best[1]):
            best = (r["id"], n)
    return best[0] if best else None


def assign_order(oid):
    o = core.order(oid)
    declined = [x for x in (o["declined"] or "").split(",") if x]
    rid = pick(declined)
    if not rid:
        core.set_status(oid, "Pending Assignment", "System")
        core.note_role("Admin", f"{oid}: no rider is available.")
        return None
    run("UPDATE orders SET rider_id=? WHERE id=?", (rid, oid))
    core.set_status(oid, "Rider Assigned", "System")
    core.note(rid, f"New delivery task {oid}.")
    core.tell_customer(o, "a rider was assigned to your parcel.")
    core.audit("System", f"Auto-assigned {oid} to {rid}")
    return rid

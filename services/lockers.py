"""Locker allocation. Atomic: a compartment can never hold two orders."""
import config
from db import q, one, run, now

RANK_SQL = "(CASE size WHEN 'S' THEN 1 WHEN 'M' THEN 2 ELSE 3 END)"


def candidates(hub_id, parcel):
    return q(f"SELECT id, size FROM lockers WHERE hub_id=? AND order_id IS NULL AND status='ok' AND {RANK_SQL}>=? ORDER BY {RANK_SQL}, id",
             (hub_id, config.RANK[parcel]))


def reserve(hub_id, locker_id, order_id, kind, hours):
    """Returns True only if THIS call got the compartment."""
    n = run("UPDATE lockers SET order_id=?, res_kind=?, res_until=? WHERE hub_id=? AND id=? AND order_id IS NULL AND status='ok'",
            (order_id, kind, now() + int(hours * 3600), hub_id, locker_id))
    return n == 1


def auto_reserve(hub_ids, parcel, order_id, kind, hours):
    for hid in hub_ids:
        if not one("SELECT 1 FROM hubs WHERE id=? AND active=1", (hid,)):
            continue
        for c in candidates(hid, parcel):
            if reserve(hid, c["id"], order_id, kind, hours):
                return hid, c["id"]
    return None


def release(hub_id, locker_id):
    if hub_id and locker_id:
        run("UPDATE lockers SET order_id=NULL, res_kind=NULL, res_until=NULL WHERE hub_id=? AND id=?", (hub_id, locker_id))


def occupy(hub_id, locker_id, kind="occupied"):
    run("UPDATE lockers SET res_kind=?, res_until=NULL WHERE hub_id=? AND id=?", (kind, hub_id, locker_id))


def set_off(hub_id, locker_id, off):
    run("UPDATE lockers SET status=? WHERE hub_id=? AND id=?", ("off" if off else "ok", hub_id, locker_id))


def grid(hub_id):
    return q("SELECT * FROM lockers WHERE hub_id=? ORDER BY id", (hub_id,))


def counts():
    rows = q("SELECT hub_id, status, order_id, res_kind FROM lockers")
    out = {}
    for r in rows:
        h = out.setdefault(r["hub_id"], {"free": 0, "occupied": 0, "reserved": 0, "off": 0})
        if r["status"] == "off":
            h["off"] += 1
        elif not r["order_id"]:
            h["free"] += 1
        elif r["res_kind"] in ("occupied", "return_in"):
            h["occupied"] += 1
        else:
            h["reserved"] += 1
    return out

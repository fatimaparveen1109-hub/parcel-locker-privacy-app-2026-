"""Database layer. PostgreSQL (Supabase) when DATABASE_URL is set, otherwise a local SQLite file for testing.
All SQL used by the app is portable between the two."""
import os
import re
import sqlite3
import threading
import time
import secrets
import hashlib
import hmac

import config

DATABASE_URL = config.secret("DATABASE_URL")
IS_PG = bool(DATABASE_URL)
SQLITE_PATH = os.environ.get("PPL_DB_PATH", "ppl_local.db")
LOCK = threading.RLock()
_state = {"conn": None, "ready": False, "offset": 0, "tx": 0}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v BIGINT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, role TEXT, name TEXT, email TEXT UNIQUE, salt TEXT, pw TEXT, status TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS user_private(user_id TEXT PRIMARY KEY, phone TEXT, area TEXT, block TEXT, street TEXT, house TEXT, landmark TEXT);
CREATE TABLE IF NOT EXISTS hubs(id TEXT PRIMARY KEY, name TEXT, area TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS lockers(id TEXT, hub_id TEXT, size TEXT, status TEXT, order_id TEXT, res_kind TEXT, res_until BIGINT, PRIMARY KEY(hub_id, id));
CREATE TABLE IF NOT EXISTS products(id {AUTO}, seller_id TEXT, name TEXT, img TEXT, price INTEGER, sizes TEXT, stock INTEGER, parcel TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, customer_id TEXT, seller_id TEXT, rider_id TEXT, status TEXT, pay_status TEXT, pay_timing TEXT, disp TEXT,
  hub1 TEXT, hub2 TEXT, allow_alt INTEGER, hub TEXT, locker TEXT, parcel TEXT, product_total INTEGER, delivery_fee INTEGER, locker_fee INTEGER, total INTEGER,
  created BIGINT, updated BIGINT, reserve_until BIGINT, deposited_at BIGINT, expires_at BIGINT, collected_at BIGINT, rem24 INTEGER, rem6 INTEGER,
  refund_type TEXT, declined TEXT, last_try BIGINT);
CREATE TABLE IF NOT EXISTS order_items(order_id TEXT, product_id INTEGER, size TEXT, qty INTEGER, unit_price INTEGER);
CREATE TABLE IF NOT EXISTS order_private(order_id TEXT PRIMARY KEY, cname TEXT, phone TEXT, address TEXT);
CREATE TABLE IF NOT EXISTS events(id {AUTO}, order_id TEXT, status TEXT, actor TEXT, ts BIGINT);
CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, order_id TEXT, method TEXT, amount INTEGER, status TEXT, idem TEXT, ts BIGINT);
CREATE TABLE IF NOT EXISTS qr_codes(id {AUTO}, order_id TEXT, qtype TEXT, holder_role TEXT, holder_id TEXT, nonce TEXT, token_hash TEXT, pin_hash TEXT,
  hub_id TEXT, locker_id TEXT, expires BIGINT, used INTEGER, done INTEGER, attempts INTEGER, active INTEGER, created BIGINT);
CREATE TABLE IF NOT EXISTS scans(id {AUTO}, ts BIGINT, order_id TEXT, qtype TEXT, role TEXT, hub_id TEXT, locker_id TEXT, result TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS returns(id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT, reason TEXT, body TEXT, photo TEXT, status TEXT, admin_note TEXT,
  hub TEXT, locker TEXT, rider_id TEXT, refund_amount INTEGER, created BIGINT, updated BIGINT);
CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT, category TEXT, body TEXT, status TEXT, reply TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS messages(id {AUTO}, channel TEXT, customer_id TEXT, order_id TEXT, sender_role TEXT, sender_id TEXT, body TEXT, ts BIGINT);
CREATE TABLE IF NOT EXISTS notifications(id {AUTO}, user_id TEXT, body TEXT, seen INTEGER, ts BIGINT);
CREATE TABLE IF NOT EXISTS audit(id {AUTO}, ts BIGINT, actor TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS logins(id {AUTO}, ts BIGINT, user_id TEXT, role TEXT, email_masked TEXT, ok INTEGER);
CREATE TABLE IF NOT EXISTS payouts(id {AUTO}, role TEXT, owner_id TEXT, amount INTEGER, ts BIGINT);
"""


def schema_sql(pg):
    return SCHEMA.replace("{AUTO}", "BIGSERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT").strip() + "\n"


def _connect():
    if IS_PG:
        import psycopg2
        import psycopg2.extras
        c = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor, connect_timeout=15)
        c.autocommit = True
        return c
    c = sqlite3.connect(SQLITE_PATH, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _exec(sql, args=()):
    with LOCK:
        if _state["conn"] is None:
            _state["conn"] = _connect()
        for attempt in (0, 1):
            try:
                if IS_PG:
                    cur = _state["conn"].cursor()
                    cur.execute(sql.replace("?", "%s"), args)
                    return cur
                return _state["conn"].execute(sql, args)
            except Exception as e:
                if IS_PG and attempt == 0 and _state["tx"] == 0 and e.__class__.__name__ in ("OperationalError", "InterfaceError"):
                    _state["conn"] = _connect()
                    continue
                raise


_local = threading.local()


def _boot():
    if _state["ready"] or getattr(_local, "booting", False):
        return
    with LOCK:
        if _state["ready"]:
            return
        _local.booting = True
        try:
            for stmt in schema_sql(IS_PG).split(";"):
                if stmt.strip():
                    cur = _exec(stmt)
                    if IS_PG:
                        cur.close()
            r = _exec("SELECT v FROM meta WHERE k='offset'").fetchone()
            _state["offset"] = int(dict(r)["v"]) if r else 0
            import seed
            seed.run()
        finally:
            _local.booting = False
        _state["ready"] = True


def q(sql, args=()):
    _boot()
    cur = _exec(sql, args)
    rows = [dict(r) for r in cur.fetchall()]
    if IS_PG:
        cur.close()
    return rows


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def run(sql, args=()):
    _boot()
    cur = _exec(sql, args)
    n = cur.rowcount
    if IS_PG:
        cur.close()
    return n


class tx:
    """Atomic block: `with tx(): ...` (checkout, locker allocation, payments)."""
    def __enter__(self):
        _boot()
        LOCK.acquire()
        _exec("BEGIN").close() if IS_PG else _exec("BEGIN IMMEDIATE")
        _state["tx"] += 1
        return self

    def __exit__(self, et, ev, tb):
        try:
            c = _exec("ROLLBACK" if et else "COMMIT")
            if IS_PG:
                c.close()
        finally:
            _state["tx"] -= 1
            LOCK.release()
        return False


def now():
    return int(time.time()) + _state["offset"] * 3600


def set_offset(hours):
    _state["offset"] = int(hours)
    run("INSERT INTO meta(k,v) VALUES('offset',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (int(hours),))


def get_offset():
    return _state["offset"]


def next_id(prefix, start=1000):
    with LOCK:
        r = one("SELECT v FROM meta WHERE k=?", (prefix,))
        n = (r["v"] if r else start) + 1
        run("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (prefix, n))
        return f"{prefix}-{n:03d}" if start < 1000 else f"{prefix}-{n}"


def meta_get(k, default=0):
    r = one("SELECT v FROM meta WHERE k=?", (k,))
    return r["v"] if r else default


def meta_set(k, v):
    run("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, int(v)))


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000).hex()


def check_pw(pw, salt, stored):
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def new_salt():
    return secrets.token_hex(8)


def sha(x):
    return hashlib.sha256((config.APP_SECRET + "|" + str(x)).encode()).hexdigest()

import re
from db import q, one, run, now, next_id, hash_pw, check_pw, new_salt, meta_get, meta_set
from services import core

PREFIX = {"Seller": "SEL", "Rider": "RID"}


def register(role, name, email, phone, pw):
    email = (email or "").strip().lower()
    if role not in ("Customer", "Seller", "Rider"):
        return None, "Invalid role."
    if not (name or "").strip() or not re.match(r"^\S+@\S+\.\S+$", email) or len(pw or "") < 6:
        return None, "Enter a name, a valid email and a password of 6 or more characters."
    if role == "Customer" and not (phone or "").strip():
        return None, "Phone number is required for customers."
    if one("SELECT 1 FROM users WHERE email=?", (email,)):
        return None, "This email is already registered. One email can only have one role."
    uid = next_id("CUS", 1000) if role == "Customer" else next_id(PREFIX[role], 0)
    salt = new_salt()
    status = "active" if role == "Customer" else "pending"
    run("INSERT INTO users VALUES(?,?,?,?,?,?,?,?)", (uid, role, name.strip(), email, salt, hash_pw(pw, salt), status, now()))
    run("INSERT INTO user_private(user_id,phone) VALUES(?,?)", (uid, (phone or "").strip()))
    core.audit(uid, f"New {role} account ({status})")
    if status == "pending":
        core.note_role("Admin", f"New {role} account request from {core.mask_email(email)}.")
    return uid, ""


def _log(uid, role, email, ok):
    run("INSERT INTO logins(ts,user_id,role,email_masked,ok) VALUES(?,?,?,?,?)", (now(), uid, role, core.mask_email(email), 1 if ok else 0))


def login(role, email, pw):
    email = (email or "").strip().lower()
    if role == "Admin" and meta_get("admin_lock", 0) > now():
        return None, "Admin account is locked for 15 minutes after too many wrong attempts."
    u = one("SELECT * FROM users WHERE email=? AND role=?", (email, role))
    if not u or not check_pw(pw or "", u["salt"], u["pw"]):
        _log("-", role, email or "x@x", False)
        if role == "Admin":
            f = meta_get("admin_fail", 0) + 1
            meta_set("admin_fail", f)
            if f >= 5:
                meta_set("admin_lock", now() + 900)
                meta_set("admin_fail", 0)
        return None, "Email or password is incorrect."
    if u["status"] == "pending":
        return None, "Your account is waiting for admin approval."
    if u["status"] != "active":
        return None, "This account is suspended. Contact the admin."
    if role == "Admin":
        meta_set("admin_fail", 0)
    _log(u["id"], role, email, True)
    return u, ""


def get(uid):
    return one("SELECT * FROM users WHERE id=?", (uid,))


def private(uid):
    return one("SELECT * FROM user_private WHERE user_id=?", (uid,)) or {}


def save_profile(uid, phone, area, block, street, house, landmark):
    run("UPDATE user_private SET phone=?, area=?, block=?, street=?, house=?, landmark=? WHERE user_id=?",
        (phone, area, block, street, house, landmark, uid))


def set_user_status(uid, status, actor="Admin"):
    run("UPDATE users SET status=? WHERE id=?", (status, uid))
    core.audit(actor, f"User {uid} -> {status}")
    core.note(uid, f"Your account is now {status}.")


def reject_request(uid):
    run("DELETE FROM user_private WHERE user_id=?", (uid,))
    run("DELETE FROM users WHERE id=? AND status='pending'", (uid,))
    core.audit("Admin", f"Rejected account request {uid}")


def demo_accounts(role):
    import config
    return [u for u in q("SELECT id,name,email FROM users WHERE role=? AND status='active'", (role,))
            if u["id"] in [d[0] for d in config.DEMO_USERS]]

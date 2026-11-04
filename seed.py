"""First-run data: hubs, lockers, settings, admin account, and demo users/products when DEMO_MODE is true."""
import config
import db


def run():
    if not db.one("SELECT 1 FROM hubs"):
        for hid, name, area in config.HUBS:
            db.run("INSERT INTO hubs VALUES(?,?,?,1)", (hid, name, area))
            for i, size in enumerate(config.LOCKER_SIZES, 1):
                db.run("INSERT INTO lockers VALUES(?,?,?,'ok',NULL,NULL,NULL)", (f"L{i}", hid, size))
    for k, v in config.DEFAULTS.items():
        if not db.one("SELECT 1 FROM settings WHERE k=?", (k,)):
            db.run("INSERT INTO settings VALUES(?,?)", (k, v))
    # admin: exactly one, credentials always follow the secrets
    salt = db.new_salt()
    adm = db.one("SELECT * FROM users WHERE role='Admin'")
    if not adm:
        db.run("INSERT INTO users VALUES('ADM-001','Admin','Administrator',?,?,?,'active',?)",
               (config.ADMIN_EMAIL.lower(), salt, db.hash_pw(config.ADMIN_PASSWORD, salt), db.now()))
    elif not db.check_pw(config.ADMIN_PASSWORD, adm["salt"], adm["pw"]) or adm["email"] != config.ADMIN_EMAIL.lower():
        db.run("UPDATE users SET email=?, salt=?, pw=? WHERE id='ADM-001'",
               (config.ADMIN_EMAIL.lower(), salt, db.hash_pw(config.ADMIN_PASSWORD, salt)))
    if config.DEMO_MODE and not db.one("SELECT 1 FROM users WHERE id='SEL-001'"):
        for uid, role, name, email in config.DEMO_USERS:
            s = db.new_salt()
            db.run("INSERT INTO users VALUES(?,?,?,?,?,?,'active',?)", (uid, role, name, email, s, db.hash_pw(config.DEMO_PASSWORD, s), db.now()))
            db.run("INSERT INTO user_private(user_id) VALUES(?)", (uid,))
        db.meta_set("SEL", 2)
        db.meta_set("RID", 3)
        for sel, name, img, price, sizes, stock, parcel in config.PRODUCTS:
            db.run("INSERT INTO products(seller_id,name,img,price,sizes,stock,parcel,active) VALUES(?,?,?,?,?,?,?,1)",
                   (sel, name, img, price, sizes, stock, parcel))

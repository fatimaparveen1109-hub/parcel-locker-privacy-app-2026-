from db import q, one, run
from services import core


def all_active():
    return q("SELECT p.*, u.name AS seller_name FROM products p JOIN users u ON u.id=p.seller_id WHERE p.active=1 ORDER BY p.id")


def get(pid):
    return one("SELECT p.*, u.name AS seller_name FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?", (pid,))


def of_seller(sid):
    return q("SELECT * FROM products WHERE seller_id=? ORDER BY id", (sid,))


def update(pid, sid, price, stock, active):
    if price <= 0 or stock < 0:
        return False, "Price must be above 0 and stock cannot be negative."
    n = run("UPDATE products SET price=?, stock=?, active=? WHERE id=? AND seller_id=?", (int(price), int(stock), 1 if active else 0, pid, sid))
    return (n == 1), ("Saved." if n == 1 else "Not your product.")


def add(sid, name, price, sizes, stock, parcel, img):
    if not (name or "").strip() or price <= 0 or stock < 0:
        return False, "Enter a name, a price above 0 and stock of 0 or more."
    run("INSERT INTO products(seller_id,name,img,price,sizes,stock,parcel,active) VALUES(?,?,?,?,?,?,?,1)",
        (sid, name.strip(), (img or "").strip(), int(price), (sizes or "").replace(" ", ""), int(stock), parcel))
    core.audit(sid, f"Added product {name}")
    return True, "Product added. Put its photo in assets/ with the image name you typed."

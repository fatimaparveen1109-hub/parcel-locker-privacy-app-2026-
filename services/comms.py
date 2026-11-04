"""Chat and complaint tickets. Phone numbers and emails are blocked in chat messages."""
import re
from db import q, one, run, now, next_id
from services import core

PII = re.compile(r"(\+?\d[\d\s\-]{8,}\d)|@")


def send(channel, customer_id, order_id, sender_role, sender_id, body):
    body = (body or "").strip()
    if not body:
        return False, "Write a message first."
    if PII.search(body):
        return False, "Phone numbers and emails are not allowed in chat."
    run("INSERT INTO messages(channel,customer_id,order_id,sender_role,sender_id,body,ts) VALUES(?,?,?,?,?,?,?)",
        (channel, customer_id, order_id or "", sender_role, sender_id, body, now()))
    if sender_role == "Customer":
        if channel == "seller" and order_id:
            core.note(core.order(order_id)["seller_id"], f"New message on {order_id}.")
        elif channel == "admin":
            core.note_role("Admin", "New support message from a customer.")
    else:
        core.note(customer_id, f"New message from {sender_role.lower()}.")
    return True, "Sent."


def thread(channel, customer_id=None, seller_id=None):
    if customer_id:
        return q("SELECT * FROM messages WHERE channel=? AND customer_id=? ORDER BY id", (channel, customer_id))
    if seller_id:
        return q("SELECT m.* FROM messages m JOIN orders o ON o.id=m.order_id WHERE m.channel='seller' AND o.seller_id=? ORDER BY m.id", (seller_id,))
    return q("SELECT * FROM messages WHERE channel=? ORDER BY id", (channel,))


def new_ticket(customer_id, order_id, category, body):
    if not order_id or not (body or "").strip():
        return None, "Choose an order and describe the problem."
    tid = next_id("TKT")
    run("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?)", (tid, order_id, customer_id, category, body.strip(), "Open", "", now()))
    core.note(customer_id, f"Complaint {tid} opened for {order_id}.")
    core.note_role("Admin", f"New complaint {tid} for {order_id}.")
    return tid, ""


def tickets_of(customer_id):
    return q("SELECT * FROM tickets WHERE customer_id=? ORDER BY created DESC", (customer_id,))


def all_tickets():
    return q("SELECT * FROM tickets ORDER BY created DESC")


def update_ticket(tid, status, reply):
    t = one("SELECT * FROM tickets WHERE id=?", (tid,))
    run("UPDATE tickets SET status=?, reply=? WHERE id=?", (status, reply or "", tid))
    core.note(t["customer_id"], f"Complaint {tid} is now {status}." + (" Admin replied." if reply else ""))
    core.audit("Admin", f"Ticket {tid} -> {status}")

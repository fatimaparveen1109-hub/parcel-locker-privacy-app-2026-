"""Simulated wallets derived from orders. Pending -> Available. No real money moves anywhere."""
from db import q, one, run, now
from services import core

DEPOSITED = ("Parcel Deposited", "Ready for Customer Pickup", "Collected", "Expired (Admin Review)", "Returned to Seller")


def shares(o):
    if o["pay_status"] != "Paid":
        return []
    full = o["refund_type"] == "full"
    prod_ref = o["refund_type"] in ("full", "product")
    window = core.isetting("return_days") * 86400
    done = o["status"] == "Collected" and o["collected_at"] and now() > o["collected_at"] + window
    pct = core.isetting("commission_pct")
    seller_amt = o["product_total"] * (100 - pct) // 100
    out = [
        {"wallet": "Seller", "owner": o["seller_id"], "amount": seller_amt, "state": "Reversed" if prod_ref else ("Available" if done else "Pending"), "order": o["id"]},
        {"wallet": "Rider", "owner": o["rider_id"] or "Unassigned", "amount": o["delivery_fee"],
         "state": "Reversed" if full else ("Available" if o["status"] in DEPOSITED else "Pending"), "order": o["id"]},
        {"wallet": "Locker operator", "owner": "LOCK-OP", "amount": o["locker_fee"], "state": "Reversed" if full else ("Available" if done else "Pending"), "order": o["id"]},
    ]
    if pct and o["product_total"] - seller_amt:
        out.append({"wallet": "Platform", "owner": "PLATFORM", "amount": o["product_total"] - seller_amt,
                    "state": "Reversed" if prod_ref else ("Available" if done else "Pending"), "order": o["id"]})
    return out


def all_shares():
    rows = []
    for o in q("SELECT * FROM orders WHERE pay_status='Paid'"):
        rows += shares(o)
    return rows


def wallet(wallet_name, owner=None):
    rows = [r for r in all_shares() if r["wallet"] == wallet_name and (owner is None or r["owner"] == owner)]
    pend = sum(r["amount"] for r in rows if r["state"] == "Pending")
    avail = sum(r["amount"] for r in rows if r["state"] == "Available")
    paid = one("SELECT COALESCE(SUM(amount),0) s FROM payouts WHERE role=?" + (" AND owner_id=?" if owner else ""), (wallet_name, owner) if owner else (wallet_name,))["s"]
    return {"rows": rows, "pending": pend, "available": avail - paid, "paid_out": paid, "total": pend + avail}


def payout(wallet_name, owner):
    w = wallet(wallet_name, owner)
    if w["available"] <= 0:
        return False, "Nothing available to pay out."
    run("INSERT INTO payouts(role,owner_id,amount,ts) VALUES(?,?,?,?)", (wallet_name, owner, w["available"], now()))
    core.audit("Admin", f"Simulated payout Rs {w['available']} to {owner}")
    core.note(owner, f"A simulated payout of Rs {w['available']:,} was recorded.")
    return True, f"Simulated payout of Rs {w['available']:,} recorded."


def owners(wallet_name):
    return sorted({r["owner"] for r in all_shares() if r["wallet"] == wallet_name})


def statement_csv(wallet_name, owner):
    w = wallet(wallet_name, owner)
    lines = ["order,amount,state"] + [f"{r['order']},{r['amount']},{r['state']}" for r in w["rows"]]
    lines.append(f"TOTAL pending,{w['pending']},")
    lines.append(f"TOTAL available,{w['available']},")
    return "\n".join(lines)

"""Constants and secrets access. No secrets live in code."""
import os

APP_NAME = "Privacy Parcel Locker"


def secret(name, default=None):
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets[name]) if name in st.secrets else default
    except Exception:
        return default


DEMO_MODE = str(secret("DEMO_MODE", "true")).lower() == "true"
APP_SECRET = secret("APP_SECRET", "dev-secret-change-me")
ADMIN_EMAIL = secret("ADMIN_EMAIL", "admin@parcellocker.pk")
ADMIN_PASSWORD = secret("ADMIN_PASSWORD", "Admin@Strict2026!")
USING_DEFAULT_ADMIN = secret("ADMIN_PASSWORD") is None
DEMO_PASSWORD = "Demo@123"

RANK = {"S": 1, "M": 2, "L": 3}
SIZE_NAME = {"S": "Small", "M": "Medium", "L": "Large"}

STATUS_FLOW = ["Order Placed", "Accepted", "Preparing", "Ready for Dispatch", "Rider Assigned", "Awaiting Pickup",
               "In Transit", "Locker Assigned", "Parcel Deposited", "Ready for Customer Pickup", "Collected"]
ACTIVE_RIDER = ["Rider Assigned", "Awaiting Pickup", "In Transit", "Locker Assigned", "Awaiting Locker"]
DONE = ["Collected", "Cancelled", "Rejected", "Returned to Seller"]
IN_LOCKER = ["Parcel Deposited", "Ready for Customer Pickup"]

DEFAULTS = {"delivery_fee": "30", "locker_fee": "60", "return_days": "7", "pickup_hours": "48",
            "accept_hours": "12", "pay_hours": "24", "reserve_hours": "2", "rider_capacity": "3",
            "collection_point": "Hub Collection Desk", "commission_pct": "0"}

# hub id, name, area
HUBS = [("H-DHA", "DHA Hub", "DHA"), ("H-CLF", "Clifton Hub", "Clifton"), ("H-SDR", "Saddar Hub", "Saddar"),
        ("H-GUL", "Gulshan-e-Iqbal Hub", "Gulshan-e-Iqbal"), ("H-PEC", "PECHS Hub", "PECHS")]
LOCKER_SIZES = ["S", "S", "S", "S", "M", "M", "M", "L"]

# demo address helper (manual entry always works)
AREAS = {
    "DHA": {"hub": "H-DHA", "blocks": ["Phase 1", "Phase 2", "Phase 4", "Phase 5", "Phase 6", "Phase 7", "Phase 8"], "street": "Khayaban-e-Shahbaz"},
    "Clifton": {"hub": "H-CLF", "blocks": ["Block 2", "Block 4", "Block 5", "Block 8", "Block 9"], "street": "Clifton Road"},
    "Saddar": {"hub": "H-SDR", "blocks": ["Zaibunnisa Street", "Elphinstone Street", "Empress Market area"], "street": "Abdullah Haroon Road"},
    "Gulshan-e-Iqbal": {"hub": "H-GUL", "blocks": ["Block 1", "Block 3", "Block 5", "Block 10", "Block 13"], "street": "Main University Road"},
    "PECHS": {"hub": "H-PEC", "blocks": ["Block 2", "Block 3", "Block 6"], "street": "Tariq Road"},
}

# seller_id, name, image key, price, sizes, stock, parcel size
DEMO_USERS = [("SEL-001", "Seller", "Karim Traders", "seller1@demo.pk"), ("SEL-002", "Seller", "Noor Fashion", "seller2@demo.pk"),
              ("RID-001", "Rider", "Bilal Ahmed", "rider1@demo.pk"), ("RID-002", "Rider", "Sana Khan", "rider2@demo.pk"),
              ("RID-003", "Rider", "Imran Ali", "rider3@demo.pk")]
PRODUCTS = [
    ("SEL-001", "Wireless Earbuds", "earbuds", 3500, "", 50, "S"), ("SEL-001", "Smart Watch", "smartwatch", 7800, "", 40, "S"),
    ("SEL-001", "Travel Backpack", "backpack", 4200, "", 30, "L"), ("SEL-001", "Sunglasses", "sunglasses", 2200, "", 60, "S"),
    ("SEL-002", "Running Shoes", "shoes", 6500, "40,41,42,43,44", 40, "M"), ("SEL-002", "Cotton Shirt", "shirt", 1600, "S,M,L", 80, "S"),
    ("SEL-002", "Hoodie", "hoodie", 3900, "S,M,L,XL", 50, "M"), ("SEL-002", "Cap", "cap", 900, "", 90, "S"),
]
RETURN_REASONS = ["Damaged", "Wrong item", "Wrong size", "Not as described", "Changed my mind"]
SELLER_FAULT = ["Damaged", "Wrong item", "Wrong size", "Not as described"]

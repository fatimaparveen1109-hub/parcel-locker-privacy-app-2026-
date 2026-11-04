"""Virtual locker controller for demos. Scan with the phone camera, paste the QR text, or type Order ID + PIN.
The server checks everything (services/qr.py). The order moves forward only after 'Door closed' is confirmed.
Later this page is replaced by the real controller calling the same verify() logic."""
import streamlit as st

from db import q
from services import qr as qrs, core
import ui


def _decode(photo):
    try:
        import cv2
        import numpy as np
    except Exception:
        return None, "Camera decoding is not installed. Paste the QR text instead."
    img = cv2.imdecode(np.frombuffer(photo.getvalue(), np.uint8), cv2.IMREAD_COLOR)
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    return (text or None), ("" if text else "No QR found. Hold the QR closer and try again.")


def render(user=None):
    st.title("Locker scanner (demo device)")
    st.caption("This page acts like the scanner on a locker. Real hardware will call the same server check later.")
    hubs = core.hub_names()
    c1, c2 = st.columns(2)
    hub = c1.selectbox("Hub", list(hubs), format_func=hubs.get, key="sc_hub")
    lk = [r["id"] for r in q("SELECT id FROM lockers WHERE hub_id=? ORDER BY id", (hub,))]
    locker = c2.selectbox("Locker", [""] + lk, key="sc_lk", format_func=lambda x: x or "No locker (hub room door)")
    method = st.radio("How to scan", ["Camera", "Paste QR text", "Order ID + PIN"], horizontal=True, key="sc_method")
    scanned, order_id = None, None
    if method == "Camera":
        photo = st.camera_input("Point the camera at the QR and take a photo", key="sc_cam")
        if photo is not None:
            scanned, err = _decode(photo)
            if err:
                st.warning(err)
    elif method == "Paste QR text":
        scanned = st.text_input("QR text (starts with PPL|)", key="sc_text")
    else:
        order_id = st.text_input("Order ID", key="sc_oid")
        scanned = st.text_input("6-digit PIN", key="sc_pin")
    if st.button("Check QR", type="primary", key="sc_go") and scanned:
        res = qrs.verify(scanned, hub, locker or None, order_id)
        st.session_state["scan_res"] = res
        st.session_state.pop("scan_done", None)
    res = st.session_state.get("scan_res")
    if res:
        if res["result"] == "VALID":
            st.success(f"VALID. {res['message']}")
            if res.get("qtype") == "HUB_ACCESS":
                st.info("Hub room access granted for 30 minutes. Now scan the locker QR.")
            elif not st.session_state.get("scan_done"):
                st.warning("Place or take the parcel, close the door, then confirm.")
                if st.button("Door closed (confirm)", key="sc_close"):
                    ok, msg = qrs.finish(res["qr_id"])
                    st.session_state["scan_done"] = msg
                    st.rerun()
            if st.session_state.get("scan_done"):
                st.success(st.session_state["scan_done"])
        else:
            st.error(f"DENY: {res['result']}. {res['message']}")
    st.subheader("Recent scans")
    ui.table([{"Time": ui.fmt(s["ts"]), "Order": s["order_id"] or "-", "Type": s["qtype"] or "-", "Result": s["result"], "Hub": s["hub_id"] or "-", "Locker": s["locker_id"] or "-"}
              for s in qrs.recent_scans(15)], "No scans yet.")

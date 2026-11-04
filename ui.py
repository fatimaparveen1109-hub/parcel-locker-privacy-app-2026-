"""Look and feel + small reusable components. No emojis anywhere."""
import base64
import os
from datetime import datetime
from functools import lru_cache

import pandas as pd
import streamlit as st

import config
from services import qr as qrs

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');
html, body, [class*="css"], .stApp {font-family: 'Inter', system-ui, sans-serif;}
h1, h2, h3, h4 {font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important; letter-spacing: -.02em;}
#MainMenu, footer, [data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {display: none !important;}
.block-container {max-width: 1150px; padding-top: 1rem; padding-bottom: 4rem;}
.brand {display:flex; align-items:center; gap:10px; font: 800 19px 'Plus Jakarta Sans', sans-serif;}
.brand i {width:28px; height:28px; border-radius:9px; background:linear-gradient(135deg,#2563EB,#7C3AED); display:inline-grid; place-items:center;}
.brand i::after {content:""; width:10px; height:10px; border-radius:50%; background:#fff;}
.mu {opacity:.7; font-size:.92rem;}
.badge {display:inline-block; padding:2px 11px; border-radius:99px; font-size:.78rem; font-weight:700; background:rgba(127,127,127,.2);}
.badge.ok {background:#16A34A; color:#fff;} .badge.wa {background:#F59E0B; color:#2b2100;} .badge.er {background:#DC2626; color:#fff;} .badge.bl {background:#2563EB; color:#fff;}
.hero {display:grid; grid-template-columns:1.05fr .95fr; gap:36px; align-items:center; padding:46px 40px; border-radius:24px; color:#fff;
  background:linear-gradient(135deg,#0F172A 0%,#1E3A8A 55%,#5B21B6 100%); margin:14px 0 8px;}
.hero h1 {font-size:clamp(2rem,4.6vw,3.3rem); font-weight:800; line-height:1.08; margin:0 0 14px; color:#fff;}
.hero h1 em {font-style:normal; color:#5EEAD4;} .hero p {font-size:1.1rem; color:#CBD5E1; max-width:46ch;}
.hero .tag {display:inline-block; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.25); border-radius:99px; padding:4px 14px; font-size:.8rem; font-weight:600; margin-bottom:16px;}
.hero .pic {background:#fff; border-radius:18px; padding:10px; box-shadow:0 30px 60px rgba(0,0,0,.35);} .hero .pic img {width:100%; border-radius:12px; display:block;}
.ph {display:grid; place-items:center; min-height:150px; border-radius:12px; background:rgba(127,127,127,.15); color:#64748B; font-weight:600; text-align:center; padding:12px;}
.steps {display:grid; grid-template-columns:repeat(5,1fr); gap:14px;}
.step, .feat div {border:1px solid rgba(127,127,127,.3); border-radius:16px; padding:16px;}
.step b {display:block; font-family:'Plus Jakarta Sans',sans-serif;} .step::before {content:attr(data-n); display:grid; place-items:center; width:30px; height:30px; border-radius:10px; background:#2563EB; color:#fff; font-weight:800; margin-bottom:8px;}
.feat {display:grid; grid-template-columns:repeat(3,1fr); gap:14px;} .feat b {display:block; margin-bottom:4px;}
.pimg {border-radius:14px; overflow:hidden; background:#fff; aspect-ratio:1/1; display:grid; place-items:center; margin-bottom:8px;}
.pimg img {width:100%; height:100%; object-fit:contain;}
.qrbox {background:#fff; padding:8px; display:inline-block; border-radius:12px; border:1px solid #E2E8F0;}
.lk {display:grid; grid-template-columns:repeat(8,1fr); gap:6px; margin:6px 0 14px;}
.lk span {font-size:.72rem; text-align:center; padding:7px 2px; border-radius:8px; background:rgba(127,127,127,.14); border:1.5px solid rgba(127,127,127,.35);}
.lk .oc {background:#DBEAFE; border-color:#2563EB; color:#1E3A8A;} .lk .rv {background:#EDE9FE; border-color:#7C3AED; color:#4C1D95;} .lk .of {background:#FEE2E2; border-color:#DC2626; color:#7F1D1D;}
div[role="radiogroup"] {gap:4px; flex-wrap:wrap;}
div[role="radiogroup"] > label {background:rgba(127,127,127,.1); padding:6px 14px; border-radius:10px; font-weight:600;}
.stButton > button, .stDownloadButton > button {border-radius:10px; font-weight:600;}
@media (max-width: 900px) {.hero {grid-template-columns:1fr; padding:28px 22px;} .steps {grid-template-columns:1fr 1fr;} .feat {grid-template-columns:1fr 1fr;}}
@media (max-width: 560px) {.steps, .feat {grid-template-columns:1fr;}}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def rs(n):
    return f"Rs {int(n):,}"


def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%d %b %H:%M") if ts else "-"


def left_text(ts, now_ts):
    s = max(0, int(ts - now_ts))
    return f"{s // 3600}h {s % 3600 // 60}m"


@lru_cache(maxsize=None)
def _img_uri(key):
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = os.path.join(ASSETS, key + ext)
        if os.path.exists(p):
            mime = "png" if ext == ".png" else "webp" if ext == ".webp" else "jpeg"
            with open(p, "rb") as f:
                return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode()
    return None


def product_img(key, name):
    uri = _img_uri(key or "")
    inner = f'<img src="{uri}" alt="{name}">' if uri else f'<div class="ph">{name}<br><span class="mu">add assets/{key}.jpg</span></div>'
    return f'<div class="pimg">{inner}</div>'


def hero_img():
    uri = _img_uri("hero_locker")
    return f'<div class="pic"><img src="{uri}" alt="Automated parcel lockers"></div>' if uri else '<div class="pic"><div class="ph">Add assets/hero_locker.jpg</div></div>'


def badge(text, kind=""):
    return f'<span class="badge {kind}">{text}</span>'


def status_kind(s):
    if s in ("Collected", "Ready for Customer Pickup", "Paid", "Success", "Resolved", "Refunded", "Approved", "active"):
        return "ok"
    if s in ("Cancelled", "Rejected", "Expired (Admin Review)", "Payment Failed", "Failed", "Inspection Failed", "suspended"):
        return "er"
    if s.startswith("Awaiting") or s in ("Payment Pending", "Pending Assignment", "Requested", "Open", "pending", "Under Review"):
        return "wa"
    return "bl"


def sb(s):
    return badge(s, status_kind(s))


def table(rows, empty="Nothing here yet."):
    if not rows:
        st.caption(empty)
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True)


def boxes(items):
    cols = st.columns(len(items))
    for c, (label, value) in zip(cols, items):
        c.metric(label, value)


def nav(role, options):
    key = f"nav_{role}"
    if "_goto" in st.session_state and st.session_state["_goto"] in options:
        st.session_state[key] = st.session_state.pop("_goto")
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    return st.radio("Menu", options, key=key, horizontal=True, label_visibility="collapsed")


def goto(page):
    st.session_state["_goto"] = page
    st.rerun()


def flash(msg):
    st.session_state["flash"] = msg


def show_qr(info, label, key, hint=""):
    """Show one QR (image, PIN, download). `info` comes from services.qr.current()."""
    with st.container(border=True):
        st.markdown(f"**{label}**")
        if hint:
            st.caption(hint)
        if not info:
            st.caption("Not available yet.")
            return
        if info["used"]:
            st.success("This QR was used.")
            return
        if not info["active"]:
            st.warning("This QR was replaced by a newer one.")
            return
        if info["expired"]:
            st.error("This QR has expired.")
            return
        st.markdown(f'<div class="qrbox">{qrs.svg_inline(info["text"])}</div>', unsafe_allow_html=True)
        st.markdown(f"PIN: **{info['pin']}**  \n<span class='mu'>Valid until {fmt(info['expires'])}. Single use.</span>", unsafe_allow_html=True)
        st.download_button("Download QR (PNG)", qrs.png_bytes(info["text"]), file_name=f"{info['type']}_{key}.png", mime="image/png", key=f"dl_{key}")


def notes_list(rows):
    if not rows:
        st.caption("No notifications yet.")
    for n in rows:
        st.markdown(f"{n['body']}  \n<span class='mu'>{fmt(n['ts'])}</span>", unsafe_allow_html=True)


def lockers_html(rows):
    out = []
    for r in rows:
        cls = "of" if r["status"] == "off" else ("" if not r["order_id"] else ("oc" if r["res_kind"] in ("occupied", "return_in") else "rv"))
        out.append(f'<span class="{cls}" title="{r["order_id"] or "Free"}">{r["id"]} {r["size"]}</span>')
    return '<div class="lk">' + "".join(out) + "</div>"

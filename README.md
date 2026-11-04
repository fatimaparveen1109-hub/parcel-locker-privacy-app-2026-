# Privacy Parcel Locker (Streamlit + Supabase)

One web app, one shared database, four dashboards (Customer, Seller, Rider, Admin) connected through one order workflow.
Payments, refunds and locker unlocking are **simulated**. No real money moves and no hardware is controlled.

## What is inside

| File / folder | Purpose |
|---|---|
| `app.py` | Start file. Top bar, routing, notifications toast |
| `config.py` | Hubs, products, areas, defaults, secrets access |
| `db.py`, `seed.py`, `schema.sql` | Database (Supabase Postgres, or a local file for testing) and first-run data |
| `services/` | All business rules: orders, payments, lockers, riders, QR, returns, wallets, housekeeping, chat |
| `views/` | Screens only: landing, login, customer, seller, rider, admin, scanner, notifications, info pages |
| `integrations.py` | The ONE place to plug in the real QR system and the real locker controller later |
| `assets/` | Your photos (9 files, already included) |
| `tests/test_workflow.py` | Automatic test of the whole workflow |

## Deploy, step by step (new repository, your old ones stay untouched)

### 1. GitHub
1. github.com > **New repository** > name `privacy-parcel-locker` > Public or Private > Create.
2. **Add file > Upload files**. Drag the CONTENTS of this folder (not the folder itself). Keep the folders `services`, `views`, `assets`, `tests`.
3. The hidden folder `.streamlit/` may not upload by drag and drop. The app works without it. If you want it, use **Add file > Create new file**, type `.streamlit/config.toml` and paste the file contents.
4. Click **Commit changes**. Check that `app.py` is in the main page of the repository, and that `assets/` shows 9 photos.

### 2. Supabase (database)
1. supabase.com > New project > choose a strong database password and save it.
2. Project > **Connect** > copy the **connection pooler** string (Transaction or Session pooler), not the direct one. Streamlit Cloud may not reach the direct host (IPv6). Check the current Supabase docs if the screen looks different.
3. Replace `[YOUR-PASSWORD]` in that string with your database password. If the password has special characters (@ : / #), URL-encode them.
4. You do NOT need to run `schema.sql`: the app creates the tables on first start. (Use it only if you prefer to create them yourself in the SQL editor.)

### 3. Streamlit Community Cloud
1. share.streamlit.io > **Create app** > pick your repository > branch `main` > main file `app.py`.
2. **Advanced settings**: choose Python 3.11 (safest for the packages) and paste your **Secrets**:
```
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:6543/postgres"
ADMIN_EMAIL = "your-admin@example.com"
ADMIN_PASSWORD = "a-long-strong-password"
APP_SECRET = "a-long-random-text-used-to-protect-QR-tokens"
DEMO_MODE = "true"
```
3. Deploy. The first start takes a few minutes. If it shows an error, copy the red text and send it to your helper.

### 4. First login
- **Admin**: the email and password you put in Secrets. Only one admin exists. If you do not set them, the demo admin is `admin@parcellocker.pk` / `Admin@Strict2026!`. Change this before sharing the link.
- **Customer**: Create account first, then log in. The account is saved in the database, so you log in again later with the same account.
- **Seller / Rider** (DEMO_MODE true): use the **Quick demo login** list. Password for demo accounts: `Demo@123`. New seller/rider accounts need Admin approval (Admin > Users).
- Set `DEMO_MODE = "false"` for real use: demo accounts and the quick login list are not created.

## Test it by hand (the whole chain)
1. Customer: create account, log in, add **Running Shoes** (Noor Fashion) to the cart, pick area and two hubs, choose **Pay after the parcel is in the locker**, place the order.
2. Seller (Noor Fashion): Accept, Start preparing, choose Rider pickup, Ready for dispatch. A rider is assigned automatically.
3. Rider: Accept task, Confirm pickup, choose a suggested locker, Assign. Two QR codes appear one after the other.
4. Open **Scanner** (top bar). Hub = the order's hub, locker = empty. Paste the Step 1 QR text (or use camera / Order ID + PIN). Then pick the locker, scan Step 2, press **Door closed**. Status becomes Parcel Deposited.
5. Customer: **My Locker** shows payment due. Pay Now (tick "Simulate a failed payment" first to see Retry). Now the room QR and pickup QR appear. Scan both in the scanner. Status becomes Collected.
6. Customer: Returns, request a return (photo needed for most reasons). Admin approves. A new locker is reserved. Customer scans return QRs, a rider collects, the seller inspects, a simulated refund is recorded.
7. Admin: Overview boxes, Orders, Money (the Rs split into Seller, Rider, Locker operator), Settlements, Scan Log, Audit Log.
8. Demo shortcuts (Admin > Settings): **Simulate +49 hours** (pickup expiry), **Skip return window** (seller payout becomes Available).

## Run the automatic test on your computer
```
pip install -r requirements.txt
python tests/test_workflow.py
```
It uses a temporary local file and never touches Supabase.

## How the QR system works
- QR text: `PPL|TYPE|ORDER_ID|TOKEN`. Types: HUB_ACCESS, RIDER_DELIVERY, CUSTOMER_PICKUP, CUSTOMER_RETURN, RIDER_RETURN.
- Every QR is new and different. It has a 6-digit PIN as a fallback. Only hashes are stored in the database.
- Server checks: right type, not used, not expired (pickup = 48 hours), payment verified, right hub and locker, hub room access scanned first, max 5 wrong attempts. Results: VALID, INVALID, EXPIRED, ALREADY_USED, PAYMENT_PENDING, WRONG_LOCKER, NO_HUB_ACCESS, NOT_READY, TOO_MANY_ATTEMPTS.
- The order moves forward only after **Door closed** is confirmed (later: the door sensor).

## Later: real QR system and real lockers
- Replace the bodies of the classes in `integrations.py` and keep `services/qr.py` `verify()` and `finish()` as the single check. Wrap them in a small API (`/scan`, `/door-event`) hosted on a separate server, because Streamlit cannot receive hardware requests. Do not invent the other group's API: wait for their specification.

## Honest limitations
- Payments, refunds, QR unlocking and the scanner are simulated. The camera takes one photo at a time (not live video) and may need good light.
- Streamlit has no background scheduler. Expiries, reminders and auto-cancel run when someone opens a page (or from Admin > Settings > Run housekeeping now).
- Refreshing the browser logs you out (Streamlit sessions). Your account and data stay saved.
- Address search is a demo list of Karachi areas; manual entry always works. Live address suggestions are not connected.
- Free tiers have limits and can change (Streamlit apps may sleep, Supabase free projects may pause when unused). Check their current pages.
- Photos: the 9 included photos are cropped screenshots. Some show brand names or logos. For a public project replace them with free-licence photos (Unsplash, Pexels) using the same file names.

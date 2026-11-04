-- PostgreSQL (Supabase). The app creates these tables automatically on first run.
-- You only need this file if you prefer to create the tables yourself in the Supabase SQL editor.
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v BIGINT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, role TEXT, name TEXT, email TEXT UNIQUE, salt TEXT, pw TEXT, status TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS user_private(user_id TEXT PRIMARY KEY, phone TEXT, area TEXT, block TEXT, street TEXT, house TEXT, landmark TEXT);
CREATE TABLE IF NOT EXISTS hubs(id TEXT PRIMARY KEY, name TEXT, area TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS lockers(id TEXT, hub_id TEXT, size TEXT, status TEXT, order_id TEXT, res_kind TEXT, res_until BIGINT, PRIMARY KEY(hub_id, id));
CREATE TABLE IF NOT EXISTS products(id BIGSERIAL PRIMARY KEY, seller_id TEXT, name TEXT, img TEXT, price INTEGER, sizes TEXT, stock INTEGER, parcel TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, customer_id TEXT, seller_id TEXT, rider_id TEXT, status TEXT, pay_status TEXT, pay_timing TEXT, disp TEXT,
  hub1 TEXT, hub2 TEXT, allow_alt INTEGER, hub TEXT, locker TEXT, parcel TEXT, product_total INTEGER, delivery_fee INTEGER, locker_fee INTEGER, total INTEGER,
  created BIGINT, updated BIGINT, reserve_until BIGINT, deposited_at BIGINT, expires_at BIGINT, collected_at BIGINT, rem24 INTEGER, rem6 INTEGER,
  refund_type TEXT, declined TEXT, last_try BIGINT);
CREATE TABLE IF NOT EXISTS order_items(order_id TEXT, product_id INTEGER, size TEXT, qty INTEGER, unit_price INTEGER);
CREATE TABLE IF NOT EXISTS order_private(order_id TEXT PRIMARY KEY, cname TEXT, phone TEXT, address TEXT);
CREATE TABLE IF NOT EXISTS events(id BIGSERIAL PRIMARY KEY, order_id TEXT, status TEXT, actor TEXT, ts BIGINT);
CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, order_id TEXT, method TEXT, amount INTEGER, status TEXT, idem TEXT, ts BIGINT);
CREATE TABLE IF NOT EXISTS qr_codes(id BIGSERIAL PRIMARY KEY, order_id TEXT, qtype TEXT, holder_role TEXT, holder_id TEXT, nonce TEXT, token_hash TEXT, pin_hash TEXT,
  hub_id TEXT, locker_id TEXT, expires BIGINT, used INTEGER, done INTEGER, attempts INTEGER, active INTEGER, created BIGINT);
CREATE TABLE IF NOT EXISTS scans(id BIGSERIAL PRIMARY KEY, ts BIGINT, order_id TEXT, qtype TEXT, role TEXT, hub_id TEXT, locker_id TEXT, result TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS returns(id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT, reason TEXT, body TEXT, photo TEXT, status TEXT, admin_note TEXT,
  hub TEXT, locker TEXT, rider_id TEXT, refund_amount INTEGER, created BIGINT, updated BIGINT);
CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, order_id TEXT, customer_id TEXT, category TEXT, body TEXT, status TEXT, reply TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS messages(id BIGSERIAL PRIMARY KEY, channel TEXT, customer_id TEXT, order_id TEXT, sender_role TEXT, sender_id TEXT, body TEXT, ts BIGINT);
CREATE TABLE IF NOT EXISTS notifications(id BIGSERIAL PRIMARY KEY, user_id TEXT, body TEXT, seen INTEGER, ts BIGINT);
CREATE TABLE IF NOT EXISTS audit(id BIGSERIAL PRIMARY KEY, ts BIGINT, actor TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS logins(id BIGSERIAL PRIMARY KEY, ts BIGINT, user_id TEXT, role TEXT, email_masked TEXT, ok INTEGER);
CREATE TABLE IF NOT EXISTS payouts(id BIGSERIAL PRIMARY KEY, role TEXT, owner_id TEXT, amount INTEGER, ts BIGINT);

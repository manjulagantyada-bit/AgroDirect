# AgroDirect – Full-stack marketplace prototype

A Flask + SQLite prototype connecting farmers and buyers. Includes account registration/login, farmer product management, buyer cart/order requests, order history, and admin order-status controls.

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Create and activate a virtual environment (recommended):
   - Windows: `py -m venv .venv` then `.venv\Scripts\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Start: `python app.py`
6. Open `http://127.0.0.1:5000`

## Local demo logins

- Farmer: `farmer@agrodirect.test` / `Farmer@123`
- Buyer: `buyer@agrodirect.test` / `Buyer@123`
- Admin: `admin@agrodirect.test` / `Admin@123`

The app creates `agrodirect.db` on first run and seeds sample listings. You can also register your own farmer and buyer accounts.

## Features

- Marketplace search, category filter, price sorting
- Farmer and buyer registration; password hashes stored in SQLite
- Farmer dashboard: add, edit and remove listings
- Buyer cart and order requests
- Server-side stock checks and stock reduction at checkout
- Buyer order history and role-protected order details
- Admin dashboard and order-status updates

## Important prototype limitations

- This is a learning/demo prototype, not a production marketplace.
- No payment gateway, SMS/OTP, email notifications, delivery partner integration, image upload service, or dispute/refund workflow is connected.
- Add CSRF protection, rate limiting, email verification, password reset, secure production secrets, HTTPS, backups, logging, privacy/terms pages and deployment hardening before public launch.
- Demo accounts and sample listings are seeded automatically. Remove demo credentials and change the secret key before deployment.
- Do not use real customer personal data in a public demo.

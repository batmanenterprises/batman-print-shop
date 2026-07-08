# Batman Enterprises — Online Print Ordering

Students scan a QR → upload a file → pay through a secure Razorpay checkout
(GPay, PhonePe, Paytm, BHIM all built in) → the order **only appears in your
dashboard once payment is actually confirmed** — automatically, with the
order ID attached. You download the file, print it, and mark it
Printed → Delivered.

---

## 1. Set up Razorpay (do this first)

1. Go to **razorpay.com** → Sign Up. Use your shop's email + phone.
2. You can start immediately in **Test Mode** — no KYC needed yet, good for setting everything up.
3. Go to **Settings → API Keys → Generate Test Key**. Copy the **Key ID** and **Key Secret**.
4. Go to **Settings → Webhooks → Add New Webhook**:
   - URL: `https://YOUR-LIVE-URL/webhook/razorpay` (you'll fill this in once deployed — see step 3 below)
   - Active events: check **`payment.captured`**
   - Save, then copy the **Webhook Secret** it gives you.
5. When you're ready to accept **real** payments, complete KYC (Settings → Account & Settings → KYC): you'll need your **PAN, Aadhaar, and a bank account** (a personal savings account is fine for a sole proprietor). Takes 1–3 business days. Then switch to **Live Keys** the same way.

**On fees:** standard bank-account UPI is generally fee-free under RBI's zero-MDR rule, but Razorpay may still apply a small platform/technology fee — check the exact number shown on your own Razorpay pricing page after signup, since this can vary and affects your margins.

---

## 2. Add your keys as environment variables (don't hardcode them in the file)

You'll set these on Render (or wherever you deploy) as **Environment Variables**:

| Key | Value |
|---|---|
| `RAZORPAY_KEY_ID` | from step 1 |
| `RAZORPAY_KEY_SECRET` | from step 1 |
| `RAZORPAY_WEBHOOK_SECRET` | from step 1 |
| `FLASK_SECRET_KEY` | any random long text you make up |

Shop name, prices, and admin password are already set directly in `app.py`.

---

## 3. Deploy on Render.com

1. Push this folder to a GitHub repo (same as before — drag and drop all files via GitHub's "upload files").
2. On Render: **New → Web Service** → connect your repo.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app`
5. Instance Type: Free (or paid for always-on, no sleep delay)
6. Add all 4 environment variables from the table above.
7. Deploy. Copy your live URL (e.g. `https://batman-print-shop.onrender.com`).
8. Go back to Razorpay → Webhooks → paste this URL as `https://your-url/webhook/razorpay`, save.

---

## 4. Daily workflow

1. Student scans your QR → fills the form → taps **Pay Now** → pays via GPay/PhonePe/Paytm/BHIM inside the secure checkout.
2. The moment payment succeeds, Razorpay confirms it to your server (two ways: instantly in the browser, and again via webhook as a backup) — the order flips to **Paid** and appears on your `/admin` dashboard automatically. No manual checking needed.
3. Download the file, print it.
4. Mark **Printed**, then **Delivered** once handed over.
5. If someone abandons payment partway, their order just won't show up — you can still peek at it via **"Show unpaid/abandoned orders"** on the dashboard if needed.

---

## 5. What's in this project
- `app.py` — all logic: order creation, Razorpay order + signature verification, webhook handler, admin routes
- `templates/` — order form, payment/receipt page, admin login & dashboard
- `static/style.css` — the visual theme
- `static/images/shop-qr.png` — your official GPay Business QR (used only as a manual fallback)
- `static/images/print-hero.jpg` — the illustration shown while a print job is in the queue
- `orders.db` — auto-created SQLite database, all order records
- `uploads/` — auto-created, stores uploaded files

## 6. Notes
- The **manual QR fallback** on the payment page does not auto-confirm — if a customer uses it, you'll need to check your bank/UPI app yourself and mark them Paid manually via **"Show unpaid orders"**.
- Test everything in **Test Mode** first (Razorpay gives you fake card/UPI credentials for testing) before switching to Live Keys.

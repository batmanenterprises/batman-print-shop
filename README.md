# {{ Your Shop Name }} — Online Print Ordering

A simple web app for your print shop:
- Students scan a QR code → open a page → upload their file, pick B&W/Color, pages, copies
- They see a total price and a UPI QR (pre-filled with the exact amount) to pay
- You log into `/admin`, see every order, download the file, print it, and mark it Paid → Printed → Delivered

No printer automation, no local software needed on your side beyond a browser. Files are stored on the server; you just download and print like any normal file.

---

## 1. Before you deploy — edit `app.py`

Open `app.py` and change the top **CONFIG** section:

```python
SHOP_NAME = "Your Shop Name"
UPI_ID = "yourshopname@upi"        # <-- YOUR real UPI ID (from any UPI app)
UPI_PAYEE_NAME = "Your Shop Name"
PRICE_PER_PAGE_BW = 2.0
PRICE_PER_PAGE_COLOR = 5.0
ADMIN_PASSWORD = "changeme123"      # <-- pick a real password, don't leave this default
```

That's the only file you need to touch to get started.

---

## 2. Deploy online (Render.com — free tier available, easiest for beginners)

1. Create a free account at **render.com**.
2. Push this folder to a **GitHub repository** (create a free GitHub account if you don't have one, create a new repo, upload all these files — GitHub's website lets you drag-and-drop files, no git command line needed).
3. In Render, click **New → Web Service**, connect your GitHub repo.
4. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free (or the cheapest paid tier for always-on uptime — free tier sleeps after inactivity, which means the first visitor after a while waits ~30 seconds for it to wake up)
5. Add an **Environment Variable**: `FLASK_SECRET_KEY` = any random long text string (this keeps admin logins secure).
6. Deploy. Render gives you a URL like `https://yourshop.onrender.com` — that's your live website.

**Note on file storage:** Render's free/basic tiers don't keep uploaded files permanently across restarts (the disk resets). For a shop actually taking daily orders, add a **Render Disk** (a few rupees/month) under your service's Settings → Disks, mounted at `/opt/render/project/src/uploads` — this keeps uploaded files safely between restarts. Alternatively, download and print each file the same day and this usually isn't an issue.

### Alternative host: PythonAnywhere or Railway.app
Both work similarly — upload the code, set the same Build/Start commands, add the environment variable, deploy. If you want, tell me which one you pick and I'll give you the exact click-by-click steps for that specific platform.

---

## 3. Make your QR code

Once your site is live at your URL:
1. Go to any free QR generator (e.g. `qr-code-generator.com` or Google "free QR code generator").
2. Paste your live URL (e.g. `https://yourshop.onrender.com`).
3. Download the QR image, print it, stick it up in your shop and share it with students (WhatsApp groups, college noticeboard, Instagram).

---

## 4. Your daily workflow

1. Student scans QR → uploads file → pays your UPI ID directly (money lands straight in your bank account, same as any UPI payment).
2. You open `https://yourshop.onrender.com/admin`, log in with your password.
3. You see the order, check your UPI app to confirm the payment actually came in, click **Mark Paid**.
4. Download the file, print it.
5. Click **Mark Printed**, then **Mark Delivered** once you've handed it over.

---

## 5. Local files reference
- `app.py` — all the logic (routes, pricing, database)
- `templates/` — the pages (order form, receipt, admin dashboard)
- `static/style.css` — visual styling
- `orders.db` — created automatically, stores all order records (SQLite — no separate database server needed)
- `uploads/` — created automatically, stores uploaded files

---

## 6. Things to consider adding later (optional)
- Auto page-counting for PDFs (right now students type in page count themselves — trusts them to be honest; you can double-check after download before printing)
- SMS/WhatsApp auto-notify when status changes to Printed
- A payment gateway (Razorpay/Cashfree) instead of manual UPI confirmation, if order volume grows and manual checking becomes a bottleneck

Happy to help with any of these whenever you're ready.

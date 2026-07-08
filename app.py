"""
Batman Enterprises - Online Print Ordering App
------------------------------------------------
Students scan a QR code -> upload file + choose options -> pay via Razorpay
(real UPI checkout: GPay/PhonePe/Paytm/BHIM all inside one secure flow) ->
Razorpay confirms payment automatically (via signature check + webhook) ->
order only then appears as "Paid" in your dashboard -> you download, print,
mark Printed/Delivered, and hand-deliver it.

HOW TO CUSTOMIZE (do this before deploying):
1. Edit the CONFIG section below - shop name, prices, admin password.
2. Sign up at razorpay.com, get your Key ID + Key Secret (Settings > API Keys)
   and paste them below. Start with TEST keys while you're setting things up.
3. In Razorpay Dashboard > Settings > Webhooks, add a webhook pointing to
   https://YOUR-LIVE-URL/webhook/razorpay, subscribe to "payment.captured",
   and paste the Webhook Secret it gives you below.
4. See README.md for full deployment steps (Render.com).
"""

import os
import sqlite3
import uuid
import hmac
import hashlib
import json
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, render_template,
    session, send_from_directory, flash, abort, jsonify
)
import razorpay

# ============== CONFIG - EDIT THESE ==============
SHOP_NAME = "Batman Enterprises"
UPI_ID = "8010500400@okbizaxis"           # kept only as a QR fallback, see /qr route
UPI_PAYEE_NAME = "Batman Enterprises"
PRICE_PER_PAGE_BW = 2.0
PRICE_PER_PAGE_COLOR = 10.0
ADMIN_PASSWORD = "Mrunal@1198"

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_xxxxxxxxxxxxxx")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "xxxxxxxxxxxxxxxxxxxxxxxx")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "xxxxxxxxxxxxxxxxxxxxxxxx")
# ===================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "orders.db")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
MAX_FILE_SIZE_MB = 25

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ---------------- Database helpers ----------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            student_name TEXT,
            roll_no TEXT,
            phone TEXT,
            filename TEXT,
            original_filename TEXT,
            print_type TEXT,
            pages INTEGER,
            copies INTEGER,
            amount REAL,
            notes TEXT,
            status TEXT DEFAULT 'pending',   -- pending -> paid -> printed -> delivered
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            created_at TEXT
        )
    """)
    # add columns if upgrading an older database that predates Razorpay fields
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    for col in ("razorpay_order_id", "razorpay_payment_id"):
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT")
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def mark_paid(razorpay_order_id, razorpay_payment_id):
    """Marks the matching order as paid. Safe to call more than once
    (e.g. from both the browser callback and the webhook)."""
    conn = get_db()
    row = conn.execute(
        "SELECT id, status FROM orders WHERE razorpay_order_id = ?", (razorpay_order_id,)
    ).fetchone()
    if row and row["status"] == "pending":
        conn.execute(
            "UPDATE orders SET status = 'paid', razorpay_payment_id = ? WHERE id = ?",
            (razorpay_payment_id, row["id"]),
        )
        conn.commit()
    conn.close()


# ---------------- Student-facing pages ----------------
@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        shop_name=SHOP_NAME,
        price_bw=PRICE_PER_PAGE_BW,
        price_color=PRICE_PER_PAGE_COLOR,
    )


@app.route("/submit", methods=["POST"])
def submit_order():
    student_name = request.form.get("student_name", "").strip()
    roll_no = ""  # roll number field removed from the order form
    phone = request.form.get("phone", "").strip()
    print_type = request.form.get("print_type", "bw")
    pages = request.form.get("pages", "1")
    copies = request.form.get("copies", "1")
    notes = request.form.get("notes", "").strip()
    file = request.files.get("file")

    if not student_name or not phone or not file or file.filename == "":
        flash("Please fill all required fields and choose a file.")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("File type not allowed. Use PDF, DOC/DOCX, or JPG/PNG.")
        return redirect(url_for("index"))

    try:
        pages = max(1, int(pages))
        copies = max(1, int(copies))
    except ValueError:
        pages, copies = 1, 1

    price_per_page = PRICE_PER_PAGE_COLOR if print_type == "color" else PRICE_PER_PAGE_BW
    amount = round(price_per_page * pages * copies, 2)

    order_id = uuid.uuid4().hex[:8]
    ext = file.filename.rsplit(".", 1)[1].lower()
    stored_filename = f"{order_id}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, stored_filename))

    # Create the matching Razorpay order up front, so the payment can be
    # tied back to this exact order_id via receipt/notes.
    razorpay_order_id = None
    try:
        rzp_order = rzp_client.order.create({
            "amount": int(round(amount * 100)),  # paise
            "currency": "INR",
            "receipt": order_id,
            "notes": {"order_id": order_id, "student_name": student_name},
        })
        razorpay_order_id = rzp_order["id"]
    except Exception as e:
        # Falls back to manual QR flow if Razorpay keys aren't set up yet
        app.logger.warning(f"Razorpay order creation failed: {e}")

    conn = get_db()
    conn.execute(
        """INSERT INTO orders
           (id, student_name, roll_no, phone, filename, original_filename,
            print_type, pages, copies, amount, notes, status, razorpay_order_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (order_id, student_name, roll_no, phone, stored_filename, file.filename,
         print_type, pages, copies, amount, notes, razorpay_order_id,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("confirmation", order_id=order_id))


@app.route("/confirmation/<order_id>")
def confirmation(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order:
        abort(404)

    return render_template(
        "confirmation.html",
        order=order,
        shop_name=SHOP_NAME,
        razorpay_key_id=RAZORPAY_KEY_ID,
        amount_paise=int(round(order["amount"] * 100)),
    )


@app.route("/verify_payment", methods=["POST"])
def verify_payment():
    """Called by the browser right after Razorpay Checkout succeeds.
    Verifies the cryptographic signature before trusting it, then marks paid."""
    data = request.get_json(force=True)
    try:
        rzp_client.utility.verify_payment_signature({
            "razorpay_order_id": data["razorpay_order_id"],
            "razorpay_payment_id": data["razorpay_payment_id"],
            "razorpay_signature": data["razorpay_signature"],
        })
    except razorpay.errors.SignatureVerificationError:
        return jsonify({"ok": False, "error": "signature_invalid"}), 400

    mark_paid(data["razorpay_order_id"], data["razorpay_payment_id"])
    return jsonify({"ok": True})


@app.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    """Backup confirmation path: Razorpay calls this server-to-server the
    moment a payment captures, even if the customer closed their browser
    right after paying. This is what makes confirmation reliable."""
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        abort(400)

    event = json.loads(raw_body)
    if event.get("event") == "payment.captured":
        payment = event["payload"]["payment"]["entity"]
        mark_paid(payment["order_id"], payment["id"])

    return jsonify({"ok": True})


@app.route("/api/status/<order_id>")
def api_status(order_id):
    conn = get_db()
    order = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order:
        abort(404)
    return jsonify({"status": order["status"]})


@app.route("/qr/<order_id>")
def payment_qr(order_id):
    return redirect(url_for("static", filename="images/shop-qr.png"))


# ---------------- Admin (you) pages ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong password.")
    return render_template("admin_login.html", shop_name=SHOP_NAME)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


def require_admin():
    return bool(session.get("is_admin"))


@app.route("/admin")
def admin_dashboard():
    if not require_admin():
        return redirect(url_for("admin_login"))
    show_all = request.args.get("show_all") == "1"
    conn = get_db()
    if show_all:
        orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    else:
        orders = conn.execute(
            "SELECT * FROM orders WHERE status != 'pending' ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return render_template("admin_dashboard.html", orders=orders, shop_name=SHOP_NAME, show_all=show_all)


@app.route("/admin/status/<order_id>/<new_status>", methods=["POST"])
def update_status(order_id, new_status):
    if not require_admin():
        return redirect(url_for("admin_login"))
    if new_status not in ("pending", "paid", "printed", "delivered"):
        abort(400)
    conn = get_db()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/download/<order_id>")
def download_file(order_id):
    if not require_admin():
        return redirect(url_for("admin_login"))
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order:
        abort(404)
    return send_from_directory(
        UPLOAD_DIR, order["filename"],
        as_attachment=True, download_name=order["original_filename"]
    )


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

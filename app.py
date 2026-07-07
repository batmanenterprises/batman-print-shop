"""
Local Print Shop - Online Print Ordering App
---------------------------------------------
Students scan a QR code -> upload file + choose options -> see UPI QR to pay
-> you (admin) see the order in a dashboard, download the file, print it,
mark it Paid/Printed, and hand-deliver it.

HOW TO CUSTOMIZE (do this before deploying):
1. Edit the CONFIG section below - set your shop name, UPI ID, prices.
2. Set a real ADMIN_PASSWORD (used to log into /admin).
3. See README.md for how to deploy this online (Render.com, free/cheap).
"""

import os
import sqlite3
import uuid
import io
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, render_template,
    session, send_from_directory, flash, abort
)
import qrcode

# ============== CONFIG - EDIT THESE ==============
SHOP_NAME = "Batman Enterprises"
UPI_ID = "gpay-12207534085@okbizaxis"
UPI_PAYEE_NAME = "Batman Enterprises"
PRICE_PER_PAGE_BW = 2.0               # rupees per page, black & white
PRICE_PER_PAGE_COLOR = 10.0           # rupees per page, color
ADMIN_PASSWORD = "Mrunal@1198"        # your admin login password
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
            print_type TEXT,      -- 'color' or 'bw'
            pages INTEGER,
            copies INTEGER,
            amount REAL,
            notes TEXT,
            status TEXT DEFAULT 'pending',   -- pending -> paid -> printed -> delivered
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
    roll_no = request.form.get("roll_no", "").strip()
    phone = request.form.get("phone", "").strip()
    print_type = request.form.get("print_type", "bw")
    pages = request.form.get("pages", "1")
    copies = request.form.get("copies", "1")
    notes = request.form.get("notes", "").strip()
    file = request.files.get("file")

    # basic validation
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

    conn = get_db()
    conn.execute(
        """INSERT INTO orders
           (id, student_name, roll_no, phone, filename, original_filename,
            print_type, pages, copies, amount, notes, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (order_id, student_name, roll_no, phone, stored_filename, file.filename,
         print_type, pages, copies, amount, notes, datetime.now().isoformat(timespec="seconds")),
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
    )


@app.route("/qr/<order_id>")
def payment_qr(order_id):
    """Generates a UPI QR code image pre-filled with the exact order amount."""
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order:
        abort(404)

    upi_link = (
        f"upi://pay?pa={UPI_ID}&pn={UPI_PAYEE_NAME.replace(' ', '%20')}"
        f"&am={order['amount']}&cu=INR&tn=Print%20Order%20{order_id}"
    )
    img = qrcode.make(upi_link)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return app.response_class(buf.read(), mimetype="image/png")


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
    if not session.get("is_admin"):
        return False
    return True


@app.route("/admin")
def admin_dashboard():
    if not require_admin():
        return redirect(url_for("admin_login"))
    conn = get_db()
    orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", orders=orders, shop_name=SHOP_NAME)


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

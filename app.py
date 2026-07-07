"""
Batman Enterprises - Online Print Ordering App
------------------------------------------------
Students scan QR -> upload file + choose options -> see UPI QR to pay
-> Admin sees ONLY PAID orders in dashboard, downloads file, prints, delivers.
"""

import os
import sqlite3
import uuid
import io
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, render_template,
    session, send_from_directory, flash, abort, jsonify
)
import qrcode

# ============== CONFIG - EDIT THESE ==============
SHOP_NAME = "Batman Enterprises"
UPI_ID = "8010500400@okbizaxis"
UPI_PAYEE_NAME = "Batman Enterprises"
PRICE_PER_PAGE_BW = 2.0
PRICE_PER_PAGE_COLOR = 10.0
ADMIN_PASSWORD = "Mrunal@1198"
# ===================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "orders.db")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
MAX_FILE_SIZE_MB = 25

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "batman-print-shop-secret-key-2024")
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024


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
            phone TEXT,
            filename TEXT,
            original_filename TEXT,
            print_type TEXT,
            pages INTEGER,
            copies INTEGER,
            amount REAL,
            notes TEXT,
            status TEXT DEFAULT 'pending',
            payment_method TEXT DEFAULT '',
            created_at TEXT
        )
    """)

    # Auto-migration: add payment_method column if missing
    try:
        conn.execute("SELECT payment_method FROM orders LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- Student Pages ----------------
@app.route("/")
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
    phone = request.form.get("phone", "").strip()
    print_type = request.form.get("print_type", "bw")
    pages = request.form.get("pages", "1")
    copies = request.form.get("copies", "1")
    notes = request.form.get("notes", "").strip()
    file = request.files.get("file")

    if not student_name or not phone or not file or file.filename == "":
        flash("Please fill all required fields and choose a file.", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("File type not allowed. Use PDF, DOC/DOCX, or JPG/PNG.", "error")
        return redirect(url_for("index"))

    try:
        pages = max(1, int(pages))
        copies = max(1, int(copies))
    except ValueError:
        pages, copies = 1, 1

    price_per_page = PRICE_PER_PAGE_COLOR if print_type == "color" else PRICE_PER_PAGE_BW
    amount = round(price_per_page * pages * copies, 2)

    order_id = uuid.uuid4().hex[:8].upper()
    ext = file.filename.rsplit(".", 1)[1].lower()
    stored_filename = f"{order_id}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, stored_filename))

    conn = get_db()
    conn.execute(
        """INSERT INTO orders
           (id, student_name, phone, filename, original_filename,
            print_type, pages, copies, amount, notes, status, payment_method, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)""",
        (order_id, student_name, phone, stored_filename, file.filename,
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

    note = f"Print Order {order_id}"
    pa = UPI_ID
    pn = UPI_PAYEE_NAME.replace(" ", "%20")
    am = order["amount"]
    common = f"pa={pa}&pn={pn}&am={am}&cu=INR&tn={note.replace(' ', '%20')}"

    upi_links = {
        "gpay": f"tez://upi/pay?{common}",
        "phonepe": f"phonepe://pay?{common}",
        "paytm": f"paytmmp://pay?{common}",
        "bhim": f"bhim://pay?{common}",
        "generic": f"upi://pay?{common}",
    }

    return render_template(
        "confirmation.html",
        order=order,
        shop_name=SHOP_NAME,
        upi_links=upi_links,
        upi_id=UPI_ID,
    )


@app.route("/api/status/<order_id>")
def api_status(order_id):
    conn = get_db()
    order = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order:
        abort(404)
    return {"status": order["status"]}


@app.route("/api/confirm-payment/<order_id>", methods=["POST"])
def confirm_payment(order_id):
    data = request.get_json(silent=True) or {}
    method = data.get("method", "upi")

    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        abort(404)

    conn.execute(
        "UPDATE orders SET payment_method = ? WHERE id = ?",
        (method, order_id)
    )
    conn.commit()
    conn.close()

    return {"success": True, "message": "Payment confirmation recorded. Please wait for shop to verify."}


@app.route("/qr/<order_id>")
def payment_qr(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order:
        abort(404)

    upi_link = (
        f"upi://pay?pa={UPI_ID}&pn={UPI_PAYEE_NAME.replace(' ', '%20')}"
        f"&am={order['amount']}&cu=INR&tn=Print%20Order%20{order_id}"
    )
    img = qrcode.make(upi_link, box_size=10, border=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return app.response_class(buf.read(), mimetype="image/png")


# ---------------- Admin Pages ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong password.", "error")
    return render_template("admin_login.html", shop_name=SHOP_NAME)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


def require_admin():
    return session.get("is_admin", False)


@app.route("/admin")
def admin_dashboard():
    if not require_admin():
        return redirect(url_for("admin_login"))
    conn = get_db()
    rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    orders = [dict(row) for row in rows]
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
    return jsonify({"success": True, "status": new_status})


@app.route("/admin/delete/<order_id>", methods=["POST"])
def delete_order(order_id):
    if not require_admin():
        return redirect(url_for("admin_login"))
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order:
        filepath = os.path.join(UPLOAD_DIR, order["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
    conn.close()
    return jsonify({"success": True})


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
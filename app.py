import os
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("AGRO_DB_PATH", os.path.join(BASE_DIR, "agrodirect.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-before-deployment")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 phone TEXT NOT NULL,
 location TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('farmer','buyer','admin')),
 password_hash TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 farmer_id INTEGER NOT NULL REFERENCES users(id),
 name TEXT NOT NULL,
 category TEXT NOT NULL,
 description TEXT DEFAULT '',
 price REAL NOT NULL CHECK(price > 0),
 quantity REAL NOT NULL CHECK(quantity >= 0),
 unit TEXT NOT NULL,
 location TEXT NOT NULL,
 image_url TEXT DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 buyer_id INTEGER NOT NULL REFERENCES users(id),
 total REAL NOT NULL,
 delivery_address TEXT NOT NULL,
 phone TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Pending',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 order_id INTEGER NOT NULL REFERENCES orders(id),
 product_id INTEGER NOT NULL REFERENCES products(id),
 farmer_id INTEGER NOT NULL REFERENCES users(id),
 product_name TEXT NOT NULL,
 quantity REAL NOT NULL,
 unit TEXT NOT NULL,
 unit_price REAL NOT NULL
);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        # Demo accounts are for local evaluation only. Change/remove before deployment.
        demo = [
            ("Demo Farmer", "farmer@agrodirect.test", "9000000001", "Kadapa", "farmer", "Farmer@123"),
            ("Demo Buyer", "buyer@agrodirect.test", "9000000002", "Tirupati", "buyer", "Buyer@123"),
            ("Demo Admin", "admin@agrodirect.test", "9000000003", "Andhra Pradesh", "admin", "Admin@123"),
        ]
        for name, email, phone, location, role, password in demo:
            conn.execute(
                "INSERT OR IGNORE INTO users(name,email,phone,location,role,password_hash,created_at) VALUES(?,?,?,?,?,?,?)",
                (name,email,phone,location,role,generate_password_hash(password),datetime.utcnow().isoformat())
            )
        farmer = conn.execute("SELECT id FROM users WHERE email='farmer@agrodirect.test'").fetchone()
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0 and farmer:
            sample = [
                ("Fresh Tomatoes","Vegetables","Farm-fresh tomatoes",28,120,"kg","Kadapa","🍅"),
                ("Sweet Mangoes","Fruits","Seasonal mangoes",75,80,"kg","Chittoor","🥭"),
                ("Organic Rice","Grains","Locally grown rice",54,300,"kg","Nellore","🌾"),
                ("Fresh Carrots","Vegetables","Freshly harvested carrots",36,90,"kg","Madanapalle","🥕"),
                ("Bananas","Fruits","Fresh bananas",42,100,"dozen","Anantapur","🍌"),
                ("Fresh Milk","Dairy","Fresh local dairy product",56,40,"litre","Proddatur","🥛"),
            ]
            conn.executemany("""INSERT INTO products(farmer_id,name,category,description,price,quantity,unit,location,image_url,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [(farmer["id"],n,c,d,p,q,u,l,e,datetime.utcnow().isoformat()) for n,c,d,p,q,u,l,e in sample])
        conn.commit()

@app.before_request
def ensure_db():
    init_db()

def current_user():
    if "user_id" not in session:
        return None
    return db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "All")
    sort = request.args.get("sort", "new")
    sql = """SELECT p.*, u.name AS farmer_name FROM products p JOIN users u ON u.id=p.farmer_id
             WHERE p.active=1 AND p.quantity>0"""
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.location LIKE ? OR p.description LIKE ? OR u.name LIKE ?)"
        params += [f"%{q}%"] * 4
    if category != "All":
        sql += " AND p.category=?"
        params.append(category)
    sql += " ORDER BY " + ("p.price ASC" if sort == "low" else "p.price DESC" if sort == "high" else "p.created_at DESC")
    products = db().execute(sql, params).fetchall()
    return render_template("index.html", products=products, q=q, category=category, sort=sort)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip().lower()
        phone=request.form.get("phone","").strip()
        location=request.form.get("location","").strip()
        role=request.form.get("role","buyer")
        password=request.form.get("password","")
        if not all([name,email,phone,location,password]) or role not in ("farmer","buyer"):
            flash("Please complete all fields with a valid account type.", "error")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
        elif not phone.isdigit() or len(phone) != 10:
            flash("Enter a valid 10-digit phone number.", "error")
        else:
            try:
                db().execute("""INSERT INTO users(name,email,phone,location,role,password_hash,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (name,email,phone,location,role,generate_password_hash(password),datetime.utcnow().isoformat()))
                db().commit()
                flash("Account created. Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        user=db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user=current_user()
    if user["role"] == "farmer":
        products=db().execute("SELECT * FROM products WHERE farmer_id=? ORDER BY created_at DESC",(user["id"],)).fetchall()
        orders=db().execute("""SELECT DISTINCT o.*, b.name buyer_name FROM orders o
            JOIN order_items oi ON oi.order_id=o.id JOIN users b ON b.id=o.buyer_id
            WHERE oi.farmer_id=? ORDER BY o.created_at DESC""",(user["id"],)).fetchall()
        return render_template("farmer_dashboard.html", products=products, orders=orders)
    if user["role"] == "buyer":
        orders=db().execute("SELECT * FROM orders WHERE buyer_id=? ORDER BY created_at DESC",(user["id"],)).fetchall()
        return render_template("buyer_dashboard.html", orders=orders)
    stats={
        "users": db().execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "products": db().execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "orders": db().execute("SELECT COUNT(*) FROM orders").fetchone()[0],
    }
    users=db().execute("SELECT id,name,email,role,location,created_at FROM users ORDER BY created_at DESC").fetchall()
    orders=db().execute("SELECT o.*,u.name buyer_name FROM orders o JOIN users u ON u.id=o.buyer_id ORDER BY o.created_at DESC").fetchall()
    return render_template("admin_dashboard.html", stats=stats, users=users, orders=orders)

@app.route("/product/new", methods=["GET","POST"])
@role_required("farmer")
def product_new():
    if request.method == "POST":
        f=request.form
        try:
            price=float(f.get("price","0")); quantity=float(f.get("quantity","0"))
        except ValueError:
            price=quantity=0
        name=f.get("name","").strip()
        category=f.get("category","")
        unit=f.get("unit","")
        location=f.get("location","").strip()
        if not name or category not in ("Vegetables","Fruits","Grains","Dairy","Other") or unit not in ("kg","gram","litre","piece","dozen","bag") or price<=0 or quantity<=0 or not location:
            flash("Check product details, price, quantity and location.", "error")
        else:
            db().execute("""INSERT INTO products(farmer_id,name,category,description,price,quantity,unit,location,image_url,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (current_user()["id"],name,category,f.get("description","").strip(),price,quantity,unit,location,f.get("image_url","").strip(),datetime.utcnow().isoformat()))
            db().commit()
            flash("Product published successfully.", "success")
            return redirect(url_for("dashboard"))
    return render_template("product_form.html", product=None)

@app.route("/product/<int:product_id>/edit", methods=["GET","POST"])
@role_required("farmer")
def product_edit(product_id):
    product=db().execute("SELECT * FROM products WHERE id=? AND farmer_id=?",(product_id,current_user()["id"])).fetchone()
    if not product: abort(404)
    if request.method == "POST":
        f=request.form
        try: price=float(f.get("price","0")); quantity=float(f.get("quantity","0"))
        except ValueError: price=quantity=0
        if not f.get("name","").strip() or price<=0 or quantity<0 or not f.get("location","").strip():
            flash("Enter valid product details.", "error")
        else:
            db().execute("""UPDATE products SET name=?,category=?,description=?,price=?,quantity=?,unit=?,location=?,image_url=?
                WHERE id=? AND farmer_id=?""",
                (f.get("name","").strip(),f.get("category"),f.get("description","").strip(),price,quantity,f.get("unit"),f.get("location","").strip(),f.get("image_url","").strip(),product_id,current_user()["id"]))
            db().commit()
            flash("Product updated.", "success")
            return redirect(url_for("dashboard"))
    return render_template("product_form.html", product=product)

@app.post("/product/<int:product_id>/delete")
@role_required("farmer")
def product_delete(product_id):
    db().execute("UPDATE products SET active=0 WHERE id=? AND farmer_id=?",(product_id,current_user()["id"]))
    db().commit()
    flash("Product removed from marketplace.", "success")
    return redirect(url_for("dashboard"))

@app.post("/checkout")
@role_required("buyer")
def checkout():
    user=current_user()
    address=request.form.get("address","").strip()
    phone=request.form.get("phone","").strip()
    cart=request.form.get("cart","")
    # Cart quantities are revalidated against live stock on the server.
    import json
    try: items=json.loads(cart)
    except Exception: items=[]
    if not address or not phone.isdigit() or len(phone)!=10 or not isinstance(items,list) or not items:
        flash("Enter delivery details and add valid products.", "error")
        return redirect(url_for("index"))
    conn=db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        validated=[]; total=0
        for item in items:
            pid=int(item.get("id")); qty=float(item.get("quantity"))
            p=conn.execute("SELECT * FROM products WHERE id=? AND active=1",(pid,)).fetchone()
            if not p or qty<=0 or qty>p["quantity"]:
                raise ValueError("One or more products are unavailable or have insufficient stock.")
            validated.append((p,qty)); total += p["price"]*qty
        cur=conn.execute("INSERT INTO orders(buyer_id,total,delivery_address,phone,status,created_at) VALUES(?,?,?,?,?,?)",
            (user["id"],total,address,phone,"Pending",datetime.utcnow().isoformat()))
        order_id=cur.lastrowid
        for p,qty in validated:
            conn.execute("INSERT INTO order_items(order_id,product_id,farmer_id,product_name,quantity,unit,unit_price) VALUES(?,?,?,?,?,?,?)",
                (order_id,p["id"],p["farmer_id"],p["name"],qty,p["unit"],p["price"]))
            conn.execute("UPDATE products SET quantity=quantity-? WHERE id=?",(qty,p["id"]))
        conn.commit()
        flash(f"Order #{order_id} placed successfully. This prototype does not collect online payments.", "success")
    except (ValueError, TypeError, KeyError, sqlite3.Error) as ex:
        conn.rollback()
        flash(str(ex) or "Could not place order.", "error")
    return redirect(url_for("dashboard"))

@app.post("/order/<int:order_id>/status")
@role_required("admin")
def order_status(order_id):
    status=request.form.get("status")
    if status not in ("Pending","Confirmed","Ready for pickup","Completed","Cancelled"):
        abort(400)
    db().execute("UPDATE orders SET status=? WHERE id=?",(status,order_id))
    db().commit()
    flash("Order status updated.", "success")
    return redirect(url_for("dashboard"))

@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):
    user=current_user()
    order=db().execute("""SELECT o.*,u.name buyer_name FROM orders o JOIN users u ON u.id=o.buyer_id WHERE o.id=?""",(order_id,)).fetchone()
    if not order: abort(404)
    if user["role"] == "buyer" and order["buyer_id"] != user["id"]: abort(403)
    items=db().execute("SELECT * FROM order_items WHERE order_id=?",(order_id,)).fetchall()
    if user["role"] == "farmer" and not any(i["farmer_id"] == user["id"] for i in items): abort(403)
    return render_template("order_detail.html", order=order, items=items)

@app.errorhandler(403)
def forbidden(e): return render_template("error.html", code=403, message="You do not have permission to view this page."),403
@app.errorhandler(404)
def not_found(e): return render_template("error.html", code=404, message="The page or record was not found."),404

if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=int(os.environ.get("PORT",5000)))

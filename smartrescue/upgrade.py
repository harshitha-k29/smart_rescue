import os

if not os.path.exists("app.py"):
    raise SystemExit("Run this inside your project folder (the one that contains app.py).")

FILES = {}

FILES["requirements.txt"] = r'''Flask>=3.0
gunicorn>=21.2
waitress>=3.0
'''

FILES["Procfile"] = r'''web: gunicorn app:app
'''

FILES["serve.py"] = r'''import os
from waitress import serve
from app import app

if __name__ == "__main__":
    serve(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
'''

FILES["README.txt"] = r'''SmartRescue

Run locally:   python app.py        (or: python serve.py for a production-style server)
Environment variables:
  ADMIN_EMAIL, ADMIN_PASSWORD   creates the admin account on start (password 8+ chars)
  SECRET_KEY                    long random string (set this when deploying)
  DB_PATH                       where the SQLite file lives (put it on a persistent disk)
  PRODUCTION=1                  marks cookies Secure (use only behind HTTPS)
  HOST, PORT                    bind address and port
Deploy: any host that runs Python (Render, Railway, a VPS). Start command: gunicorn app:app
SQLite needs a persistent disk. Hosts with temporary disks will lose data on redeploy.
For many users, move to PostgreSQL.
'''

FILES["load_samples.py"] = r'''import sys, time, random, secrets
from werkzeug.security import generate_password_hash
import app as A

A.init_db()
c = A.sqlite3.connect(A.DB, isolation_level=None)
EMAIL = "sample.seller@smartrescue.invalid"

if len(sys.argv) > 1 and sys.argv[1] == "remove":
    ids = [r[0] for r in c.execute("SELECT id FROM listings WHERE sample=1")]
    for i in ids:
        for t in ("claims", "hist", "reports"):
            c.execute("DELETE FROM %s WHERE %s=?" % (t, "lid"), (i,))
        c.execute("DELETE FROM listings WHERE id=?", (i,))
    c.execute("DELETE FROM users WHERE email=?", (EMAIL,))
    print("Removed", len(ids), "sample listings")
    raise SystemExit

row = c.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
if row:
    sid = row[0]
else:
    sid = A.rid("u")
    c.execute("INSERT INTO users(id,email,pw,name,role,area,phone,regno,cats,need,radius,verified,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (sid, EMAIL, generate_password_hash(secrets.token_hex(16)), "Sample Seller (placeholder)", "seller",
               "Koramangala", "", "", "", 0, 0, 1, time.time()))
now = time.time()
for name, cat, mrp, stor in random.sample(A.CATALOG, min(35, len(A.CATALOG))):
    h = random.choice([3, 5, 9, 14, 20, 30, 45, 60, 90, 130])
    donate = random.random() < 0.15
    cost = round(mrp * 0.72, 2)
    price = 0 if donate else round(mrp * random.choice([0.5, 0.6, 0.7, 0.8]), 2)
    lid = A.rid("l")
    c.execute("INSERT INTO listings(id,seller,name,cat,orig,cost,qty,price,minp,exp,mode,area,batch,stor,ver,created,sample) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
              (lid, sid, name, cat, mrp, cost, random.choice([10, 20, 40, 60, 120]), price, 0, now + h * 3600,
               "donate" if donate else "sale", random.choice(list(A.AREA)), "", stor, "Sample listing (not a real product)", now))
    c.execute("INSERT INTO hist VALUES(?,?,?)", (lid, now, "Sample listing created"))
print("Added sample listings. Remove them with: python load_samples.py remove")
'''

FILES["app.py"] = r'''import os, re, math, time, hmac, sqlite3, secrets
from functools import wraps
from flask import Flask, g, request, session, redirect, render_template, flash, abort, jsonify
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DB_PATH", os.path.join(BASE, "smartrescue_v2.db"))
H = 3600


def _secret():
    s = os.environ.get("SECRET_KEY")
    if s:
        return s
    p = os.path.join(BASE, ".secret_key")
    if not os.path.exists(p):
        with open(p, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(p) as fh:
        return fh.read().strip()


app = Flask(__name__)
app.secret_key = _secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("PRODUCTION") == "1",
                  PERMANENT_SESSION_LIFETIME=14 * 86400, MAX_CONTENT_LENGTH=1024 * 1024)

MULT = {"Dairy": 1, "Bakery": 1.15, "Produce": 1, "Packaged food": 0.8, "Ready-to-eat": 1.1,
        "Frozen": 0.7, "Beverages": 1, "Meat & Fish": 1.1, "Pharmacy (OTC)": 0.5}
CATS = list(MULT)
ICON = {"Dairy": "&#129371;", "Bakery": "&#127838;", "Produce": "&#127813;", "Packaged food": "&#128230;",
        "Ready-to-eat": "&#127857;", "Frozen": "&#10052;", "Beverages": "&#129380;",
        "Meat & Fish": "&#127831;", "Pharmacy (OTC)": "&#128138;"}
AREA = {"Koramangala": (12.9352, 77.6245), "Indiranagar": (12.9784, 77.6408), "HSR Layout": (12.9116, 77.6389),
        "Jayanagar": (12.925, 77.5938), "Whitefield": (12.9698, 77.75), "Malleshwaram": (13.0035, 77.5648),
        "BTM Layout": (12.9166, 77.6101), "Electronic City": (12.8452, 77.6602), "Yelahanka": (13.1007, 77.5963),
        "Rajajinagar": (12.9911, 77.5524), "JP Nagar": (12.9063, 77.5857), "Marathahalli": (12.9591, 77.6974)}
CATALOG = [
    ("Toned Milk 500ml", "Dairy", 27, "Keep chilled 2-8 C"), ("Full Cream Milk 1L", "Dairy", 70, "Keep chilled 2-8 C"),
    ("Curd 400g", "Dairy", 40, "Keep chilled 2-8 C"), ("Paneer 200g", "Dairy", 90, "Keep chilled 2-8 C"),
    ("Butter 100g", "Dairy", 58, "Keep chilled 2-8 C"), ("Cheese Slices 200g", "Dairy", 140, "Keep chilled 2-8 C"),
    ("Buttermilk 200ml", "Dairy", 15, "Keep chilled 2-8 C"), ("Sweet Lassi 200ml", "Dairy", 25, "Keep chilled 2-8 C"),
    ("Flavoured Yogurt 100g", "Dairy", 25, "Keep chilled 2-8 C"), ("Fresh Cream 250ml", "Dairy", 65, "Keep chilled 2-8 C"),
    ("Sandwich Bread 400g", "Bakery", 45, "Cool dry place"), ("Multigrain Bread 400g", "Bakery", 55, "Cool dry place"),
    ("Pav (6 pcs)", "Bakery", 30, "Cool dry place"), ("Cream Rolls (pack of 4)", "Bakery", 25, "Cool dry place"),
    ("Veg Puff", "Bakery", 20, "Cool dry place"), ("Plum Cake 250g", "Bakery", 90, "Cool dry place"),
    ("Butter Croissant", "Bakery", 45, "Cool dry place"), ("Burger Buns (4 pcs)", "Bakery", 40, "Cool dry place"),
    ("Garlic Breadloaf", "Bakery", 65, "Cool dry place"),
    ("Tomatoes (per kg)", "Produce", 40, "Cool, ventilated"), ("Onions (per kg)", "Produce", 35, "Cool, ventilated"),
    ("Potatoes (per kg)", "Produce", 30, "Cool, ventilated"), ("Bananas (per dozen)", "Produce", 60, "Room temperature"),
    ("Apples (per kg)", "Produce", 180, "Cool"), ("Spinach (per bunch)", "Produce", 20, "Keep chilled"),
    ("Coriander (per bunch)", "Produce", 15, "Keep chilled"), ("Capsicum (per kg)", "Produce", 80, "Cool"),
    ("Carrots (per kg)", "Produce", 60, "Cool"), ("Grapes (per kg)", "Produce", 120, "Keep chilled"),
    ("Papaya (per kg)", "Produce", 50, "Room temperature"), ("Cauliflower (each)", "Produce", 40, "Cool"),
    ("Green Chillies 200g", "Produce", 20, "Keep cool"), ("Fresh Mint 100g", "Produce", 15, "Keep chilled"),
    ("Idli/Dosa Batter 1kg", "Packaged food", 70, "Keep chilled 2-8 C"), ("Sprouts 200g", "Packaged food", 40, "Keep chilled"),
    ("Cut Fruit Bowl 250g", "Packaged food", 80, "Keep chilled"), ("Tofu 200g", "Packaged food", 90, "Keep chilled"),
    ("Ready Chapati (10 pcs)", "Packaged food", 60, "Keep chilled"), ("Poha Mix 250g", "Packaged food", 35, "Dry place"),
    ("Veg Sandwich", "Ready-to-eat", 60, "Keep chilled"), ("Meal Box", "Ready-to-eat", 120, "Keep chilled"),
    ("Salad Bowl", "Ready-to-eat", 100, "Keep chilled"), ("Samosa (4 pcs)", "Ready-to-eat", 40, "Room temperature, same day"),
    ("Khaman Dhokla 200g", "Ready-to-eat", 50, "Keep chilled"),
    ("Frozen Green Peas 500g", "Frozen", 110, "Keep frozen at -18 C"), ("Frozen Paratha (5 pcs)", "Frozen", 100, "Keep frozen at -18 C"),
    ("Ice Cream Tub 500ml", "Frozen", 250, "Keep frozen at -18 C"), ("Frozen French Fries 400g", "Frozen", 140, "Keep frozen at -18 C"),
    ("Fresh Orange Juice 200ml", "Beverages", 60, "Keep chilled"), ("Cold Coffee 200ml", "Beverages", 70, "Keep chilled"),
    ("Tender Coconut Water 200ml", "Beverages", 45, "Keep chilled"), ("Mango Milkshake 250ml", "Beverages", 50, "Keep chilled"),
    ("Chicken 500g", "Meat & Fish", 160, "Keep chilled 0-4 C"), ("Eggs (dozen)", "Meat & Fish", 84, "Cool"),
    ("Fish Fillet 500g", "Meat & Fish", 300, "Keep chilled 0-4 C"), ("Mutton 500g", "Meat & Fish", 380, "Keep chilled 0-4 C"),
    ("ORS Sachet", "Pharmacy (OTC)", 22, "Cool dry place"), ("Glucose Powder 200g", "Pharmacy (OTC)", 60, "Cool dry place"),
]
NAV = {
    "seller": [("/dash", "Dashboard"), ("/market", "Marketplace"), ("/add", "Add Product"), ("/inv", "Inventory"),
               ("/claims", "Requests"), ("/finance", "Profit and Loss"), ("/impact", "Impact"), ("/notifs", "Notifications")],
    "buyer": [("/dash", "Dashboard"), ("/market", "Marketplace"), ("/claims", "My Orders"), ("/notifs", "Notifications")],
    "ngo": [("/dash", "Dashboard"), ("/market", "Donations"), ("/claims", "My Requests"), ("/impact", "Impact"), ("/notifs", "Notifications")],
    "admin": [("/dash", "Dashboard"), ("/market", "Marketplace"), ("/inv", "All Listings"), ("/admin/users", "Users"),
              ("/impact", "Impact"), ("/notifs", "Notifications"), ("/settings", "Settings")],
}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,pw,name,role,area,phone,regno,cats,need INT,radius INT,verified INT DEFAULT 0,created REAL);
CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY,seller,name,cat,orig REAL,cost REAL,qty INT,price REAL,
  minp REAL,exp REAL,mode,area,batch,stor,ver,created REAL,removed INT DEFAULT 0,a24 INT DEFAULT 0,a6 INT DEFAULT 0,x0 INT DEFAULT 0,sample INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,lid,uid,qty INT,type,status,price REAL,created REAL,done REAL,pickup);
CREATE TABLE IF NOT EXISTS expenses(id TEXT PRIMARY KEY,seller,descr,amt REAL,ts REAL);
CREATE TABLE IF NOT EXISTS notifs(id TEXT PRIMARY KEY,uid,msg,ts REAL,rd INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,lid,uid,ts REAL);
CREATE TABLE IF NOT EXISTS hist(lid,ts REAL,msg);
CREATE TABLE IF NOT EXISTS cfg(k PRIMARY KEY,v REAL);
"""


def init_db():
    c = sqlite3.connect(DB, isolation_level=None)
    c.executescript(SCHEMA)
    for k, v in [("red", 6), ("orange", 24), ("amber", 72)] + [("m_" + n, m) for n, m in MULT.items()]:
        c.execute("INSERT OR IGNORE INTO cfg VALUES(?,?)", (k, v))
    ae, ap = os.environ.get("ADMIN_EMAIL", "").strip().lower(), os.environ.get("ADMIN_PASSWORD", "")
    if ae and len(ap) >= 8 and not c.execute("SELECT 1 FROM users WHERE email=?", (ae,)).fetchone():
        c.execute("INSERT INTO users(id,email,pw,name,role,area,phone,regno,cats,need,radius,verified,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  ("u" + secrets.token_hex(3), ae, generate_password_hash(ap), "SmartRescue Admin", "admin", "", "", "", "", 0, 0, 1, time.time()))
    c.close()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB, timeout=10, isolation_level=None)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def _close(e):
    d = g.pop("db", None)
    if d:
        d.close()


def q(sql, a=()): return db().execute(sql, a).fetchall()
def q1(sql, a=()): return db().execute(sql, a).fetchone()
def ex(sql, a=()): return db().execute(sql, a)
def cf(): return {r["k"]: r["v"] for r in q("SELECT * FROM cfg")}
def rid(p): return p + os.urandom(3).hex()


def inr(n):
    n = round(float(n or 0), 2)
    neg = n < 0
    w, d = f"{abs(n):.2f}".split(".")
    if len(w) > 3:
        h, t = w[:-3], w[-3:]
        parts = []
        while len(h) > 2:
            parts.insert(0, h[-2:]); h = h[:-2]
        if h: parts.insert(0, h)
        w = ",".join(parts + [t])
    return Markup(("-" if neg else "") + "&#8377;" + w + ("" if d == "00" else "." + d))


def dt(t): return time.strftime("%d %b %Y %H:%M", time.localtime(t)) if t else "-"
def hrs(l): return (l["exp"] - time.time()) / H
def claimed(l): return q1("SELECT COALESCE(SUM(qty),0) s FROM claims WHERE lid=? AND status!='rejected'", (l["id"],))["s"]
def avail(l): return max(0, l["qty"] - claimed(l))
def claimable(l): return not l["removed"] and hrs(l) > 0 and avail(l) > 0
def dp(l): return 100 if l["mode"] == "donate" else (round((1 - l["price"] / l["orig"]) * 100) if l["orig"] > 0 else 0)


def urg(l):
    h, c = hrs(l), cf()
    if h <= 0: return ("grey", "Expired")
    if h < c["red"]: return ("red", "Critical")
    if h < c["orange"]: return ("orange", "Urgent")
    if h <= c["amber"]: return ("amber", "Soon")
    return ("green", "Fresh")


def left(t):
    s = t - time.time()
    if s <= 0: return "Expired"
    m = int(s // 60); d = m // 1440; h = m % 1440 // 60
    if d >= 1: return f"{d}d {h}h remaining"
    if h >= 1: return f"{h}h {m % 60}m remaining"
    return f"{m}m {int(s % 60)}s remaining"


def status(l):
    if l["removed"]: return "Removed"
    cs = q("SELECT * FROM claims WHERE lid=? AND status!='rejected'", (l["id"],))
    n = sum(c["qty"] for c in cs)
    if n >= l["qty"] and n > 0:
        if all(c["status"] == "completed" for c in cs):
            return "Donated" if l["mode"] == "donate" else "Completed"
        return "Pending Pickup" if any(c["status"] == "approved" for c in cs) else "Claimed"
    if l["exp"] <= time.time(): return "Expired"
    return "Partially Claimed" if n else "Available"


def note(uid, msg): ex("INSERT INTO notifs(id,uid,msg,ts) VALUES(?,?,?,?)", (rid("n"), uid, msg, time.time()))
def hist(lid, msg): ex("INSERT INTO hist VALUES(?,?,?)", (lid, time.time(), msg))


def csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals.update(inr=inr, dt=dt, urg=urg, left=left, avail=avail, status=status, dp=dp,
                             CATS=CATS, ICON=ICON, AREAS=list(AREA), hrs=hrs, csrf=csrf)
app.jinja_env.filters["slug"] = lambda s: re.sub(r"[^a-z]", "", s.lower())


def sweep():
    c, now = cf(), time.time()
    for l in q("SELECT * FROM listings WHERE removed=0"):
        h = (l["exp"] - now) / H
        if h <= 0:
            for k in q("SELECT * FROM claims WHERE lid=? AND status IN ('requested','approved')", (l["id"],)):
                ex("UPDATE claims SET status='rejected' WHERE id=?", (k["id"],))
                hist(l["id"], "Claim " + k["id"] + " auto-cancelled: listing expired")
                note(k["uid"], l["name"] + " expired; your request was cancelled.")
            if not l["x0"]:
                ex("UPDATE listings SET x0=1 WHERE id=?", (l["id"],))
                hist(l["id"], "Expired")
                note(l["seller"], l["name"] + " has expired and is no longer claimable.")
        else:
            if h < c["orange"] and not l["a24"]:
                ex("UPDATE listings SET a24=1 WHERE id=?", (l["id"],))
                note(l["seller"], f"{l['name']} expires in under {int(c['orange'])} hours.")
            if h < c["red"] and not l["a6"]:
                ex("UPDATE listings SET a6=1 WHERE id=?", (l["id"],))
                note(l["seller"], l["name"] + " is now in critical expiry status.")


def me():
    uid = session.get("uid")
    return q1("SELECT * FROM users WHERE id=?", (uid,)) if uid else None


@app.before_request
def _pre():
    if request.endpoint == "static":
        return
    if request.method == "POST":
        t, sent = session.get("_csrf"), request.form.get("_csrf") or request.headers.get("X-CSRF", "")
        if not t or not sent or not hmac.compare_digest(t, sent):
            abort(400)
    sweep()


@app.after_request
def _hdr(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "same-origin"
    return r


def _err(e):
    c = getattr(e, "code", 500)
    msg = {400: "Bad request or expired form. Reload the page and try again.", 403: "You do not have access to that.",
           404: "Page not found."}.get(c, "Something went wrong.")
    return render_template("page.html", title=f"Error {c}", note=msg, actions=[("/", "Home")], sts=[], charts=[],
                           alerts=None, ctitle="", claims=None, reports=None), c


for _c in (400, 403, 404, 500):
    app.register_error_handler(_c, _err)


@app.context_processor
def _ctx():
    u = me()
    return dict(me=u, nav=NAV.get(u["role"], []) if u else [],
                unread=q1("SELECT COUNT(*) n FROM notifs WHERE uid=? AND rd=0", (u["id"],))["n"] if u else 0)


def need(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = me()
            if not u: return redirect("/login?next=" + request.path)
            if roles and u["role"] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco


def safe_next(n): return n if n and n.startswith("/") and not n.startswith("//") else "/dash"


ATT = {}


def throttled(ip):
    now = time.time()
    ATT[ip] = [t for t in ATT.get(ip, []) if now - t < 600]
    return len(ATT[ip]) >= 10


@app.route("/register", methods=["GET", "POST"])
def register():
    if me(): return redirect("/dash")
    if request.method == "GET": return render_template("register.html", f={}, sel=[])
    f = request.form
    role, email, name = f.get("role"), f.get("email", "").strip().lower(), f.get("name", "").strip()
    pw, area, regno = f.get("password", ""), f.get("area"), f.get("regno", "").strip()
    phone = re.sub(r"[^0-9+]", "", f.get("phone", ""))[:15]
    cats = [c for c in f.getlist("cats") if c in CATS]
    try:
        need_q, radius = int(f.get("need") or 0), int(f.get("radius") or 10)
    except ValueError:
        need_q, radius = -1, 0
    err = None
    if role not in ("seller", "buyer", "ngo"): err = "Choose an account type."
    elif not name or len(name) > 80: err = "Enter your business or organisation name (max 80 characters)."
    elif not EMAIL.match(email): err = "Enter a valid email address."
    elif len(pw) < 8: err = "Password must be at least 8 characters."
    elif area not in AREA: err = "Choose your area."
    elif role != "seller" and not cats: err = "Choose at least one category you accept."
    elif need_q < 0 or not 1 <= radius <= 100: err = "Check the quantity and pickup radius."
    elif role == "ngo" and not regno: err = "NGOs must enter a registration number. An admin verifies it before you can request donations."
    elif q1("SELECT 1 FROM users WHERE email=?", (email,)): err = "That email is already registered."
    if err:
        flash(err, "err")
        return render_template("register.html", f=f, sel=cats), 400
    uid = rid("u")
    ex("INSERT INTO users(id,email,pw,name,role,area,phone,regno,cats,need,radius,verified,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
       (uid, email, generate_password_hash(pw), name, role, area, phone, regno, ",".join(cats), need_q, radius,
        0 if role == "ngo" else 1, time.time()))
    session.clear(); session["uid"] = uid; session.permanent = True
    flash("Welcome to SmartRescue." + (" Your NGO account is awaiting admin verification." if role == "ngo" else ""), "ok")
    return redirect("/dash")


@app.route("/login", methods=["GET", "POST"])
def login():
    if me(): return redirect("/dash")
    nxt = safe_next(request.values.get("next"))
    if request.method == "GET": return render_template("login.html", nxt=nxt)
    ip = request.remote_addr or "x"
    if throttled(ip):
        flash("Too many attempts. Try again in a few minutes.", "err")
        return render_template("login.html", nxt=nxt), 429
    u = q1("SELECT * FROM users WHERE email=?", (request.form.get("email", "").strip().lower(),))
    if not u or not check_password_hash(u["pw"], request.form.get("password", "")):
        ATT.setdefault(ip, []).append(time.time())
        flash("Wrong email or password.", "err")
        return render_template("login.html", nxt=nxt), 401
    session.clear(); session["uid"] = u["id"]; session.permanent = True
    return redirect(nxt)


@app.post("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.get("/")
def landing():
    if me(): return redirect("/dash")
    f = fin()
    act = sum(1 for l in q("SELECT * FROM listings WHERE removed=0") if claimable(l))
    return render_template("landing.html", f=f, act=act, users=q1("SELECT COUNT(*) n FROM users WHERE role!='admin'")["n"])


def calc(o):
    h = (o["exp"] - time.time()) / H
    d = 10 if h > 72 else 25 if h > 24 else 40 if h > 6 else 55
    d *= cf().get("m_" + o["cat"], 1)
    if o["qty"] > 50: d += 5
    if o["strat"] == "fast": d += 10
    if o["strat"] == "value": d -= 5
    d = max(0, min(70, round(d)))
    price = round(o["orig"] * (1 - d / 100), 2)
    fl = False
    if price < o["minp"]:
        price, fl = o["minp"], True
    return dict(h=round(h, 1), price=price, floored=fl, pct=round((1 - price / o["orig"]) * 100, 1),
                disc=round(o["orig"] - price, 2), proceeds=round(price * o["qty"], 2),
                profit=round((price - o["cost"]) * o["qty"], 2), critical=h < cf()["red"])


@app.post("/calc")
@need("seller")
def calc_api():
    j = request.get_json(silent=True) or {}
    try:
        o = dict(cat=j["cat"], orig=float(j["orig"]), cost=float(j.get("cost") or 0), qty=int(j["qty"]),
                 minp=float(j.get("minp") or 0), exp=float(j["exp"]), strat=j.get("strat", "bal"))
    except Exception:
        return jsonify(error="Enter price, quantity and expiry."), 400
    if o["orig"] <= 0 or o["qty"] < 1 or o["exp"] <= time.time():
        return jsonify(error="Enter a positive price, quantity and a future expiry."), 400
    return jsonify(calc(o))


def matches(l):
    out = []
    for u in q("SELECT * FROM users WHERE role IN ('buyer','ngo')"):
        s, w = 0, []
        cats = (u["cats"] or "").split(",")
        if l["cat"] in cats: s += 40; w.append("accepts " + l["cat"])
        else: w.append("does not list " + l["cat"])
        a = avail(l)
        s += round(20 * min(a, u["need"]) / max(a, u["need"], 1))
        w.append(f"usually needs about {u['need']} units, {a} available")
        s += 15 if hrs(l) >= 6 else 5
        w.append("enough shelf life for pickup" if hrs(l) >= 6 else "very little shelf life left")
        p, r = AREA.get(u["area"]), AREA.get(l["area"])
        if p and r:
            la, lb = math.radians(p[0]), math.radians(r[0])
            x = math.sin((lb - la) / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin(math.radians(r[1] - p[1]) / 2) ** 2
            d = 12742 * math.asin(math.sqrt(x))
            if d <= u["radius"]: s += 15
            w.append(f"about {d:.1f} km away (estimated between area centres, not GPS)")
        if (u["role"] == "ngo") == (l["mode"] == "donate"):
            s += 10; w.append("matches " + ("donation" if l["mode"] == "donate" else "purchase") + " preference")
        out.append(dict(u=u, s=s, w="; ".join(w), tag="Strong match" if s >= 75 else "Good match" if s >= 50 else "Weak match"))
    return sorted(out, key=lambda m: -m["s"])


def fin(sid=None, cat=""):
    ls = {l["id"]: l for l in q("SELECT * FROM listings") if (not sid or l["seller"] == sid) and (not cat or l["cat"] == cat)}
    o = dict(rev=0, cogs=0, disc=0, don=0, sold=0, donu=0, loss=0, lossu=0, pot=0, potp=0, risk=0, nsales=0, ndon=0, red=set())
    am = cf()["amber"]
    for c in q("SELECT * FROM claims WHERE status='completed'"):
        l = ls.get(c["lid"])
        if not l: continue
        o["red"].add(l["id"])
        if c["type"] == "sale":
            o["rev"] += c["price"] * c["qty"]; o["cogs"] += l["cost"] * c["qty"]
            o["disc"] += (l["orig"] - c["price"]) * c["qty"]; o["sold"] += c["qty"]; o["nsales"] += 1
        else:
            o["don"] += l["orig"] * c["qty"]; o["donu"] += c["qty"]; o["ndon"] += 1
    for l in ls.values():
        if l["removed"]: continue
        a, h = avail(l), hrs(l)
        if h <= 0:
            o["loss"] += a * l["cost"]; o["lossu"] += a
        else:
            if l["mode"] == "sale":
                o["pot"] += a * l["price"]; o["potp"] += a * (l["price"] - l["cost"])
            if h < am: o["risk"] += a * l["orig"]
    o["gp"] = o["rev"] - o["cogs"]
    o["exp"] = sum(e["amt"] for e in q("SELECT * FROM expenses") if not sid or e["seller"] == sid)
    o["net"] = o["gp"] - o["exp"]
    return o


def daily(sid, key):
    t = time.localtime()
    z = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
    cs = q("SELECT c.*,l.seller FROM claims c JOIN listings l ON l.id=c.lid WHERE c.status='completed'")
    out = []
    for i in range(6, -1, -1):
        s = z - i * 86400
        v = 0
        for c in cs:
            if (sid and c["seller"] != sid) or not (s <= c["done"] < s + 86400): continue
            v += (c["price"] * c["qty"] if c["type"] == "sale" else 0) if key == "rev" else c["qty"]
        out.append((time.strftime("%d %b", time.localtime(s)), v))
    return out


def claim_rows(where="1=1", a=()):
    return q("SELECT c.*,l.name,l.orig,l.seller,u.name uname FROM claims c JOIN listings l ON l.id=c.lid "
             "JOIN users u ON u.id=c.uid WHERE " + where + " ORDER BY c.created DESC", a)


def bar(t, d, money=False): return dict(kind="bar", title=t, data=d, money=money)
def col(t, d, money=False): return dict(kind="col", title=t, data=d, money=money)
UL = (("red", "Critical"), ("orange", "Urgent"), ("amber", "Soon"), ("green", "Fresh"))


@app.get("/dash")
@need()
def dash():
    u = me(); r = u["role"]
    P = dict(title="", note="", actions=[], sts=[], charts=[], alerts=None, ctitle="", claims=None, reports=None)
    allL = q("SELECT * FROM listings WHERE removed=0")
    if r == "seller":
        ls = [l for l in allL if l["seller"] == u["id"]]; f = fin(u["id"])
        act = [l for l in ls if claimable(l)]
        soon = sorted([l for l in act if hrs(l) < cf()["amber"]], key=lambda l: l["exp"])
        mine = claim_rows("l.seller=?", (u["id"],))
        P.update(title="Seller dashboard",
                 actions=[("/add", "Add product"), ("/market", "View marketplace"), ("/inv", "Manage inventory"), ("/finance", "Financial dashboard")],
                 sts=[("Active listings", len(act), ""), ("Approaching expiry", len(soon), "under %d h" % cf()["amber"]),
                      ("Open claims", sum(1 for c in mine if c["status"] in ("requested", "approved")), ""),
                      ("Completed sales", f["nsales"], ""), ("Completed donations", f["ndon"], ""),
                      ("Revenue (completed sales)", inr(f["rev"]), ""), ("At-risk stock value", inr(f["risk"]), "reference price"),
                      ("Inventory losses", inr(f["loss"]), "expired, at cost"), ("Donation value", inr(f["don"]), "not revenue")],
                 alerts=soon, ctitle="Recent transactions", claims=[c for c in mine if c["status"] == "completed"][:5],
                 charts=[bar("Inventory by category (units available)", [(c, sum(avail(l) for l in act if l["cat"] == c)) for c in CATS]),
                         bar("Listings by expiry urgency", [(n, sum(1 for l in act if urg(l)[0] == k)) for k, n in UL]),
                         col("Completed-sale revenue, last 7 days", daily(u["id"], "rev"), True),
                         col("Units rescued, last 7 days", daily(u["id"], "u"))])
    elif r == "buyer":
        L = [l for l in allL if l["mode"] == "sale" and claimable(l)]; mine = claim_rows("c.uid=?", (u["id"],))
        P.update(title="Buyer dashboard", actions=[("/market", "Browse marketplace")],
                 sts=[("Available discounted units", sum(avail(l) for l in L), ""),
                      ("Listings expiring soon", sum(1 for l in L if hrs(l) < cf()["amber"]), ""),
                      ("Listings in your area", sum(1 for l in L if l["area"] == u["area"]), u["area"]),
                      ("Potential savings", inr(sum((l["orig"] - l["price"]) * avail(l) for l in L)), "if every unit were bought"),
                      ("My claims", len(mine), ""), ("Completed orders", sum(1 for c in mine if c["status"] == "completed"), "")],
                 ctitle="My recent orders", claims=mine[:5])
    elif r == "ngo":
        L = [l for l in allL if l["mode"] == "donate" and claimable(l)]; mine = claim_rows("c.uid=?", (u["id"],))
        dn = [c for c in mine if c["status"] == "completed"]
        P.update(title="NGO dashboard", actions=[("/market", "Browse donations")],
                 note="" if u["verified"] else "Your NGO account is awaiting admin verification. You can browse, but you cannot request donations yet.",
                 sts=[("Available donation listings", len(L), ""),
                      ("Awaiting approval", sum(1 for c in mine if c["status"] == "requested"), ""),
                      ("Approved, awaiting collection", sum(1 for c in mine if c["status"] == "approved"), ""),
                      ("Completed donations", len(dn), ""),
                      ("Estimated donation value", inr(sum(c["orig"] * c["qty"] for c in dn)), "reference price"),
                      ("Units received", sum(c["qty"] for c in dn), "")],
                 ctitle="My requests", claims=mine)
    else:
        sc = {}
        for l in allL: sc[status(l)] = sc.get(status(l), 0) + 1
        f = fin()
        P.update(title="Admin dashboard", actions=[("/admin/users", "Manage users")],
                 sts=[("Total listings", len(allL), ""), ("Available", sc.get("Available", 0), ""),
                      ("Claimed / pending", sc.get("Claimed", 0) + sc.get("Pending Pickup", 0) + sc.get("Partially Claimed", 0), ""),
                      ("Completed / donated", sc.get("Completed", 0) + sc.get("Donated", 0), ""),
                      ("Users", q1("SELECT COUNT(*) n FROM users")["n"], ""),
                      ("NGOs awaiting verification", q1("SELECT COUNT(*) n FROM users WHERE role='ngo' AND verified=0")["n"], ""),
                      ("Sales / donations done", f"{f['nsales']} / {f['ndon']}", ""),
                      ("Reports", q1("SELECT COUNT(*) n FROM reports")["n"], "")],
                 charts=[bar("Listings by category", [(c, sum(1 for l in allL if l["cat"] == c)) for c in CATS]),
                         bar("Active listings by urgency", [(n, sum(1 for l in allL if claimable(l) and urg(l)[0] == k)) for k, n in UL])],
                 reports=q("SELECT r.*,l.name,u.name uname FROM reports r JOIN listings l ON l.id=r.lid JOIN users u ON u.id=r.uid"))
    return render_template("page.html", **P)


@app.get("/admin/users")
@need("admin")
def admin_users():
    return render_template("users.html", us=q("SELECT * FROM users ORDER BY created DESC"))


@app.post("/admin/verify/<uid>")
@need("admin")
def admin_verify(uid):
    u = q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u or u["role"] == "admin": abort(404)
    nv = 0 if u["verified"] else 1
    ex("UPDATE users SET verified=? WHERE id=?", (nv, uid))
    note(uid, "Your account was " + ("verified by an admin." if nv else "set to unverified by an admin."))
    return redirect("/admin/users")


@app.get("/market")
def market():
    u = me()
    f = {k: request.args.get(k, "").strip() for k in ("q", "cat", "urg", "maxp", "mind", "area")}
    f["sort"] = request.args.get("sort", "urgency")

    def num(x):
        try: return float(x)
        except ValueError: return None
    mp, md = num(f["maxp"]), num(f["mind"])
    L = [l for l in q("SELECT l.*,u.name sname FROM listings l JOIN users u ON u.id=l.seller WHERE l.removed=0")
         if not u or u["role"] not in ("buyer", "ngo") or (l["mode"] == "donate") == (u["role"] == "ngo")]
    L = [l for l in L if (not f["q"] or f["q"].lower() in l["name"].lower()) and (not f["cat"] or l["cat"] == f["cat"])
         and (not f["urg"] or urg(l)[0] == f["urg"]) and (mp is None or l["price"] <= mp) and (md is None or dp(l) >= md)
         and (not f["area"] or f["area"].lower() in l["area"].lower())]
    key = {"price": lambda l: l["price"], "discount": lambda l: -dp(l), "qty": lambda l: -avail(l),
           "dist": lambda l: 0 if u and l["area"] == u["area"] else 1}.get(f["sort"], lambda l: l["exp"])
    L.sort(key=lambda l: (0 if claimable(l) else 1, key(l)))
    return render_template("market.html", items=L, f=f)


@app.get("/listing/<lid>")
def listing(lid):
    u = me(); l = q1("SELECT * FROM listings WHERE id=?", (lid,))
    if not l or (l["removed"] and not (u and u["role"] == "admin")): abort(404)
    own = bool(u and u["role"] == "seller" and l["seller"] == u["id"])
    return render_template("listing.html", l=l, own=own, ok=claimable(l), seller=q1("SELECT * FROM users WHERE id=?", (l["seller"],)),
                           matches=matches(l) if own else None, h=q("SELECT * FROM hist WHERE lid=? ORDER BY ts", (lid,)))


@app.post("/claim/<lid>")
@need("buyer", "ngo")
def claim(lid):
    u = me(); d = db()
    try:
        qn = int(request.form.get("qty", ""))
    except ValueError:
        flash("Enter a whole quantity.", "err"); return redirect("/listing/" + lid)
    d.execute("BEGIN IMMEDIATE")
    try:
        l = d.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
        err = None
        if not l or l["removed"]: err = "Listing not found."
        elif (u["role"] == "ngo") != (l["mode"] == "donate"):
            err = "NGOs can only request donations; buyers can only claim sale listings."
        elif u["role"] == "ngo" and not u["verified"]: err = "Your NGO account is awaiting admin verification."
        elif l["exp"] <= time.time(): err = "This listing is expired and cannot be claimed."
        elif qn < 1: err = "Quantity must be at least 1."
        elif qn > avail(l): err = f"Only {avail(l)} units are available."
        if err:
            d.execute("ROLLBACK"); flash(err, "err"); return redirect("/listing/" + lid)
        d.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,NULL,NULL)",
                  (rid("c"), lid, u["id"], qn, "donation" if l["mode"] == "donate" else "sale", "requested", l["price"], time.time()))
        hist(lid, f"{qn} units reserved by {u['name']}")
        note(l["seller"], f"{u['name']} requested {qn} units of {l['name']}.")
        d.execute("COMMIT")
    except Exception:
        if d.in_transaction: d.execute("ROLLBACK")
        raise
    flash("Request placed. It is not a completed purchase until the seller approves and handover is completed.", "ok")
    return redirect("/claims")


@app.post("/claim-action/<cid>/<act>")
@need()
def claim_action(cid, act):
    u = me(); c = q1("SELECT * FROM claims WHERE id=?", (cid,))
    if not c or act not in ("approve", "reject", "complete"): abort(404)
    l = q1("SELECT * FROM listings WHERE id=?", (c["lid"],))
    s = u["role"] == "seller" and l["seller"] == u["id"]; own = c["uid"] == u["id"]
    if not ((act == "approve" and s) or (act == "reject" and (s or own)) or (act == "complete" and (s if c["type"] == "sale" else (s or own)))):
        abort(403)
    back = redirect(request.referrer or "/claims")
    if c["status"] != ("approved" if act == "complete" else "requested"):
        flash("Invalid status change.", "err"); return back
    if act != "reject" and l["exp"] <= time.time():
        ex("UPDATE claims SET status='rejected' WHERE id=?", (cid,)); hist(l["id"], "Claim " + cid + " cancelled: expired")
        flash("Listing expired. Request cancelled.", "err"); return back
    if act == "approve":
        sel = q1("SELECT * FROM users WHERE id=?", (l["seller"],))
        pk = f"Pickup at {l['area']} from {sel['name']}" + (f", phone {sel['phone']}" if sel["phone"] else "") + f". Approved {dt(time.time())}"
        ex("UPDATE claims SET status='approved',pickup=? WHERE id=?", (pk, cid)); note(c["uid"], f"Your claim on {
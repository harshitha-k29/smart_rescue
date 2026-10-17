import os

FILES = {}

FILES["requirements.txt"] = r'''Flask>=3.0
'''

FILES["app.py"] = r'''import os, sqlite3, time
from functools import wraps
from flask import Flask, g, request, session, redirect, render_template, flash, abort, jsonify
from markupsafe import Markup

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartrescue.db")
H = 3600
CATS = ["Dairy", "Bakery", "Produce", "Packaged food", "Pharmacy (OTC)"]
ICON = {"Dairy": "&#129371;", "Bakery": "&#127838;", "Produce": "&#127813;",
        "Packaged food": "&#128230;", "Pharmacy (OTC)": "&#128138;"}
AREA = {"Koramangala": (12.9352, 77.6245, "560034"), "Indiranagar": (12.9784, 77.6408, "560038"),
        "HSR Layout": (12.9116, 77.6389, "560102"), "Jayanagar": (12.925, 77.5938, "560011"),
        "Whitefield": (12.9698, 77.75, "560066")}
NAV = {
    "seller": [("/dash", "Dashboard"), ("/market", "Marketplace"), ("/add", "Add / Scan Product"),
               ("/inv", "Inventory"), ("/claims", "Requests"), ("/finance", "Profit and Loss"),
               ("/impact", "Impact"), ("/notifs", "Notifications")],
    "buyer": [("/dash", "Dashboard"), ("/market", "Marketplace"), ("/claims", "My Orders"), ("/notifs", "Notifications")],
    "ngo": [("/dash", "Dashboard"), ("/market", "Donations"), ("/claims", "My Requests"),
            ("/impact", "Impact"), ("/notifs", "Notifications")],
    "admin": [("/dash", "Dashboard"), ("/market", "Marketplace"), ("/inv", "All Listings"),
              ("/impact", "Impact"), ("/notifs", "Notifications"), ("/settings", "Settings")],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name,role,area,cats,need INT,radius INT);
CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY,seller,name,cat,orig REAL,cost REAL,qty INT,price REAL,
  minp REAL,exp REAL,mode,area,batch,stor,ver,created REAL,removed INT DEFAULT 0,a24 INT DEFAULT 0,a6 INT DEFAULT 0,x0 INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,lid,uid,qty INT,type,status,price REAL,created REAL,done REAL,pickup);
CREATE TABLE IF NOT EXISTS expenses(id TEXT PRIMARY KEY,seller,descr,amt REAL,ts REAL);
CREATE TABLE IF NOT EXISTS notifs(id TEXT PRIMARY KEY,uid,msg,ts REAL,rd INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,lid,uid,ts REAL);
CREATE TABLE IF NOT EXISTS hist(lid,ts REAL,msg);
CREATE TABLE IF NOT EXISTS cfg(k PRIMARY KEY,v REAL);
"""


def init_db(reset=False):
    c = sqlite3.connect(DB, isolation_level=None)
    if reset:
        for t in ("users", "listings", "claims", "expenses", "notifs", "reports", "hist", "cfg"):
            c.execute("DROP TABLE IF EXISTS " + t)
    c.executescript(SCHEMA)
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        n = time.time()
        for u in [("s1", "Koramangala Fresh Mart (Demo Seller)", "seller", "Koramangala", "", 0, 0),
                  ("b1", "Anand Provision Store (Demo Buyer)", "buyer", "Indiranagar", "Dairy,Bakery", 30, 8),
                  ("b2", "Sri Sai Caterers (Demo Buyer)", "buyer", "Whitefield", "Produce,Bakery", 50, 20),
                  ("n1", "Annadana Trust (Demo NGO, sample)", "ngo", "Jayanagar", "Produce,Bakery,Dairy", 40, 10),
                  ("n2", "Asha Meals Kitchen (Demo NGO, sample)", "ngo", "HSR Layout", "Bakery,Dairy", 25, 8),
                  ("a1", "Platform Admin (Demo)", "admin", "", "", 0, 0)]:
            c.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", u)
        for k, v in [("red", 6), ("orange", 24), ("amber", 72), ("m_Dairy", 1), ("m_Bakery", 1.15),
                     ("m_Produce", 1), ("m_Packaged food", 0.8), ("m_Pharmacy (OTC)", 0.5)]:
            c.execute("INSERT INTO cfg VALUES(?,?)", (k, v))
        for (i, nm, cat, o, co, q_, p, h, md, ar, mn) in [
            ("l1", "Nandini Toned Milk 500ml", "Dairy", 27, 23, 120, 21, 20, "sale", "Koramangala", 18),
            ("l2", "Britannia Bread 400g", "Bakery", 45, 34, 60, 29, 5, "sale", "Indiranagar", 25),
            ("l3", "Tomatoes (per kg)", "Produce", 40, 28, 80, 26, 50, "sale", "HSR Layout", 22),
            ("l4", "Bananas (per dozen)", "Produce", 60, 42, 50, 0, 30, "donate", "Jayanagar", 0),
            ("l5", "Kashmir Apples (per kg)", "Produce", 180, 130, 30, 140, 120, "sale", "Koramangala", 120),
            ("l6", "Spinach Bunch", "Produce", 20, 12, 100, 10, 14, "sale", "Indiranagar", 8),
            ("l7", "Amul Masti Curd 400g", "Dairy", 40, 32, 45, 28, -6, "sale", "HSR Layout", 24),
            ("l8", "Cream Rolls (pack of 4)", "Bakery", 25, 15, 40, 0, 8, "donate", "Koramangala", 0)]:
            c.execute("INSERT INTO listings(id,seller,name,cat,orig,cost,qty,price,minp,exp,mode,area,batch,stor,ver,created) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (i, "s1", nm, cat, o, co, q_, p, mn, n + h * H, md, ar, "B" + i[1:] + "42", "", "Demo data", n - 80 * H))
            c.execute("INSERT INTO hist VALUES(?,?,?)", (i, n - 80 * H, "Listed (fictional demo data)"))
        for (i, lid, uid, q_, ty, st, p, ago) in [
            ("c1", "l1", "b1", 40, "sale", "completed", 21, 26), ("c2", "l4", "n1", 20, "donation", "completed", 0, 50),
            ("c3", "l5", "b1", 8, "sale", "completed", 140, 74), ("c4", "l3", "b2", 15, "sale", "completed", 26, 6),
            ("c5", "l6", "b2", 20, "sale", "requested", 10, 2)]:
            c.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (i, lid, uid, q_, ty, st, p, n - ago * H, n - (ago - 1) * H if st == "completed" else None, None))
        c.execute("INSERT INTO expenses VALUES('e1','s1','Cold storage electricity (demo)',850,?)", (n - 48 * H,))
        c.execute("INSERT INTO notifs VALUES('n_a','s1','A buyer requested 20 units of Spinach Bunch (demo).',?,0)", (n - 2 * H,))
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


def q(sql, a=()):
    return db().execute(sql, a).fetchall()


def q1(sql, a=()):
    return db().execute(sql, a).fetchone()


def ex(sql, a=()):
    return db().execute(sql, a)


def cf():
    return {r["k"]: r["v"] for r in q("SELECT * FROM cfg")}


def rid(p):
    return p + os.urandom(3).hex()


def inr(n):
    n = round(float(n or 0), 2)
    neg = n < 0
    w, d = f"{abs(n):.2f}".split(".")
    if len(w) > 3:
        h, t = w[:-3], w[-3:]
        parts = []
        while len(h) > 2:
            parts.insert(0, h[-2:])
            h = h[:-2]
        if h:
            parts.insert(0, h)
        w = ",".join(parts + [t])
    return Markup(("-" if neg else "") + "&#8377;" + w + ("" if d == "00" else "." + d))


def dt(t):
    return time.strftime("%d %b %Y %H:%M", time.localtime(t)) if t else "-"


def hrs(l):
    return (l["exp"] - time.time()) / H


def claimed(l):
    return q1("SELECT COALESCE(SUM(qty),0) s FROM claims WHERE lid=? AND status!='rejected'", (l["id"],))["s"]


def avail(l):
    return max(0, l["qty"] - claimed(l))


def claimable(l):
    return not l["removed"] and hrs(l) > 0 and avail(l) > 0


def dp(l):
    return 100 if l["mode"] == "donate" else (round((1 - l["price"] / l["orig"]) * 100) if l["orig"] > 0 else 0)


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


def note(uid, msg):
    ex("INSERT INTO notifs(id,uid,msg,ts) VALUES(?,?,?,?)", (rid("n"), uid, msg, time.time()))


def hist(lid, msg):
    ex("INSERT INTO hist VALUES(?,?,?)", (lid, time.time(), msg))


app.jinja_env.globals.update(inr=inr, dt=dt, urg=urg, left=left, avail=avail, status=status, dp=dp,
                             CATS=CATS, ICON=ICON, AREAS=list(AREA), hrs=hrs)


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
def _b():
    if request.endpoint != "static":
        sweep()

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
            if not u: return redirect("/")
            if roles and u["role"] not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco


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
        w.append(f"needs about {u['need']} units, {a} available")
        s += 15 if hrs(l) >= 6 else 5
        w.append("enough shelf life for pickup" if hrs(l) >= 6 else "very little shelf life left")
        p, r = AREA.get(u["area"]), AREA.get(l["area"])
        if p and r:
            import math
            la, lb = math.radians(p[0]), math.radians(r[0])
            x = math.sin((lb - la) / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin(math.radians(r[1] - p[1]) / 2) ** 2
            d = 12742 * math.asin(math.sqrt(x))
            if d <= u["radius"]: s += 15
            w.append(f"about {d:.1f} km away (estimated from sample area centres, not GPS)")
        if (u["role"] == "ngo") == (l["mode"] == "donate"):
            s += 10; w.append("matches " + ("donation" if l["mode"] == "donate" else "purchase") + " preference")
        out.append(dict(u=u, s=s, w="; ".join(w), tag="Strong match" if s >= 75 else "Good match" if s >= 50 else "Weak match"))
    return sorted(out, key=lambda m: -m["s"])


def fin(sid=None, cat=""):
    ls = {l["id"]: l for l in q("SELECT * FROM listings") if (not sid or l["seller"] == sid) and (not cat or l["cat"] == cat)}
    o = dict(rev=0, cogs=0, disc=0, don=0, sold=0, donu=0, loss=0, lossu=0, pot=0, potp=0, risk=0, nsales=0, ndon=0, red=set())
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
            if h < cf()["amber"]: o["risk"] += a * l["orig"]
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


@app.get("/")
def landing():
    u = me()
    if u: return redirect("/dash")
    return render_template("landing.html", f=fin(), roles=[
        ("s1", "Seller Demo", "List near-expiry stock, get a smart discount, track P and L."),
        ("b1", "Buyer Demo", "Find discounted stock sorted by urgency and claim it."),
        ("n1", "NGO Demo", "Request donation listings and confirm collection."),
        ("a1", "Admin Demo", "Review listings, reports and platform activity.")])


@app.get("/login/<uid>")
def login(uid):
    if not q1("SELECT id FROM users WHERE id=?", (uid,)): abort(404)
    session["uid"] = uid
    nxt = request.args.get("next", "/dash")
    return redirect(nxt if nxt.startswith("/") else "/dash")


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.post("/reset")
def reset():
    init_db(reset=True)
    flash("Demo data reset.", "ok")
    return redirect(request.referrer or "/")


@app.get("/dash")
@need()
def dash():
    u = me(); r = u["role"]; now = time.time()
    P = dict(title="", note="", actions=[], sts=[], charts=[], alerts=None, ctitle="", claims=None, reports=None)
    allL = [l for l in q("SELECT * FROM listings WHERE removed=0")]
    if r == "seller":
        ls = [l for l in allL if l["seller"] == u["id"]]; f = fin(u["id"])
        act = [l for l in ls if claimable(l)]; soon = sorted([l for l in act if hrs(l) < cf()["amber"]], key=lambda l: l["exp"])
        mine = claim_rows("l.seller=?", (u["id"],))
        P.update(title="Seller dashboard", note="Sample records are fictional demo data.",
                 actions=[("/add", "Add product"), ("/add", "Scan product"), ("/market", "View marketplace"),
                          ("/inv", "Manage inventory"), ("/finance", "Financial dashboard")],
                 sts=[("Active listings", len(act), ""), ("Approaching expiry", len(soon), "under %d h" % cf()["amber"]),
                      ("Open claims", sum(1 for c in mine if c["status"] in ("requested", "approved")), ""),
                      ("Completed sales", f["nsales"], ""), ("Completed donations", f["ndon"], ""),
                      ("Revenue (completed sales)", inr(f["rev"]), ""), ("At-risk stock value", inr(f["risk"]), "reference price"),
                      ("Inventory losses", inr(f["loss"]), "expired, at cost"), ("Donation value", inr(f["don"]), "not revenue")],
                 alerts=soon, ctitle="Recent transactions", claims=[c for c in mine if c["status"] == "completed"][:5],
                 charts=[bar("Inventory by category (units available)", [(c, sum(avail(l) for l in act if l["cat"] == c)) for c in CATS]),
                         bar("Listings by expiry urgency", [(n, sum(1 for l in act if urg(l)[0] == k)) for k, n in
                                                            (("red", "Critical"), ("orange", "Urgent"), ("amber", "Soon"), ("green", "Fresh"))]),
                         col("Completed-sale revenue, last 7 days", daily(u["id"], "rev"), True),
                         col("Units rescued, last 7 days", daily(u["id"], "u"))])
    elif r == "buyer":
        L = [l for l in allL if l["mode"] == "sale" and claimable(l)]; mine = claim_rows("c.uid=?", (u["id"],))
        near = [l for l in L if l["area"] == u["area"]]
        P.update(title="Buyer dashboard", actions=[("/market", "Browse marketplace")],
                 sts=[("Available discounted units", sum(avail(l) for l in L), ""),
                      ("Listings expiring soon", sum(1 for l in L if hrs(l) < cf()["amber"]), ""),
                      ("Listings in your area", len(near), u["area"] + " (sample area)"),
                      ("Potential savings", inr(sum((l["orig"] - l["price"]) * avail(l) for l in L)), "if every unit were bought"),
                      ("My claims", len(mine), ""), ("Completed orders", sum(1 for c in mine if c["status"] == "completed"), "")],
                 ctitle="My recent orders", claims=mine[:5])
    elif r == "ngo":
        L = [l for l in allL if l["mode"] == "donate" and claimable(l)]; mine = claim_rows("c.uid=?", (u["id"],))
        dn = [c for c in mine if c["status"] == "completed"]
        P.update(title="NGO dashboard", actions=[("/market", "Browse donations")],
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
        P.update(title="Admin dashboard", note="Demo-only admin. Not production access control.",
                 sts=[("Total listings", len(allL), ""), ("Available", sc.get("Available", 0), ""),
                      ("Claimed / pending", sc.get("Claimed", 0) + sc.get("Pending Pickup", 0) + sc.get("Partially Claimed", 0), ""),
                      ("Completed / donated", sc.get("Completed", 0) + sc.get("Donated", 0), ""),
                      ("Demo users", q1("SELECT COUNT(*) n FROM users")["n"], ""),
                      ("Sales / donations done", f"{f['nsales']} / {f['ndon']}", ""),
                      ("Reports", q1("SELECT COUNT(*) n FROM reports")["n"], "")],
                 charts=[bar("Listings by category", [(c, sum(1 for l in allL if l["cat"] == c)) for c in CATS]),
                         bar("Active listings by urgency", [(n, sum(1 for l in allL if claimable(l) and urg(l)[0] == k)) for k, n in
                                                            (("red", "Critical"), ("orange", "Urgent"), ("amber", "Soon"), ("green", "Fresh"))])],
                 reports=q("SELECT r.*,l.name,u.name uname FROM reports r JOIN listings l ON l.id=r.lid JOIN users u ON u.id=r.uid"))
    return render_template("page.html", **P)


@app.get("/market")
@need()
def market():
    u = me()
    f = {k: request.args.get(k, "").strip() for k in ("q", "cat", "urg", "maxp", "mind", "area")}
    f["sort"] = request.args.get("sort", "urgency")

    def num(x):
        try: return float(x)
        except ValueError: return None
    mp, md = num(f["maxp"]), num(f["mind"])
    L = [l for l in q("SELECT * FROM listings WHERE removed=0")
         if u["role"] not in ("buyer", "ngo") or (l["mode"] == "donate") == (u["role"] == "ngo")]
    L = [l for l in L if (not f["q"] or f["q"].lower() in l["name"].lower()) and (not f["cat"] or l["cat"] == f["cat"])
         and (not f["urg"] or urg(l)[0] == f["urg"]) and (mp is None or l["price"] <= mp) and (md is None or dp(l) >= md)
         and (not f["area"] or f["area"].lower() in l["area"].lower() or f["area"] == AREA[l["area"]][2])]
    key = {"price": lambda l: l["price"], "discount": lambda l: -dp(l), "qty": lambda l: -avail(l),
           "dist": lambda l: 0 if l["area"] == u["area"] else 1}.get(f["sort"], lambda l: l["exp"])
    L.sort(key=lambda l: (0 if claimable(l) else 1, key(l)))
    return render_template("market.html", items=L, f=f)


@app.get("/listing/<lid>")
@need()
def listing(lid):
    u = me(); l = q1("SELECT * FROM listings WHERE id=?", (lid,))
    if not l: abort(404)
    own = u["role"] == "seller" and l["seller"] == u["id"]
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
    flash("Request placed. It is NOT a completed purchase until the seller approves and handover is completed.", "ok")
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
        pk = f"Pickup at {l['area']} (sample location), within 2 hours of {dt(time.time())}"
        ex("UPDATE claims SET status='approved',pickup=? WHERE id=?", (pk, cid)); note(c["uid"], f"Your claim on {l['name']} is approved. " + pk)
    elif act == "reject":
        ex("UPDATE claims SET status='rejected' WHERE id=?", (cid,)); note(l["seller"] if own else c["uid"], f"Claim on {l['name']} was cancelled/rejected; quantity restored.")
    else:
        ex("UPDATE claims SET status='completed',done=? WHERE id=?", (time.time(), cid))
        note(l["seller"], f"Pickup of {l['name']} marked completed."); note(c["uid"], f"Handover of {l['name']} completed.")
    hist(l["id"], f"Claim {cid}: {act}")
    flash("Updated.", "ok")
    return back


@app.route("/add", methods=["GET", "POST"])
@need("seller")
def add():
    if request.method == "GET": return render_template("add.html")
    u = me(); f = request.form; err = None
    try:
        orig, cost, qn = float(f["orig"]), float(f["cost"]), int(f["qty"])
        minp = float(f.get("minp") or 0); exp = float(f["exp_ts"]); mode = f["mode"]
        price = 0.0 if mode == "donate" else float(f["price"])
    except (ValueError, KeyError):
        orig = cost = qn = minp = exp = price = mode = None; err = "Please fill every required number correctly (including a valid expiry)."
    cat, name, batch = f.get("cat", ""), f.get("name", "").strip(), f.get("batch", "").strip()
    if not err:
        if not name: err = "Product name is required."
        elif cat not in CATS or f.get("area") not in AREA: err = "Invalid category or area."
        elif orig <= 0 or cost < 0 or minp < 0 or price < 0: err = "Prices must be positive; cost cannot be negative."
        elif qn < 1: err = "Quantity must be a whole number of 1 or more."
        elif exp <= time.time(): err = "Expired products cannot be listed."
        elif f.get("cond") != "ok": err = "Damaged, opened or recalled products cannot be listed."
        elif not (f.get("ok1") and f.get("ok2")): err = "Confirm the expiry check and the safety statement."
        elif cat == "Pharmacy (OTC)" and not (f.get("auth") and batch): err = "Pharmacy items need authorisation confirmation and a batch number."
        elif price > orig: err = "Price cannot exceed the original price."
        elif mode == "sale" and price < minp and not f.get("ov"): err = "Price is below your minimum. Tick override to allow it."
    if err:
        flash(err, "err"); return render_template("add.html"), 400
    lid = rid("l")
    ex("INSERT INTO listings(id,seller,name,cat,orig,cost,qty,price,minp,exp,mode,area,batch,stor,ver,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
       (lid, u["id"], name, cat, orig, cost, qn, price, minp, exp, mode, f["area"], batch, f.get("stor", ""),
        "Seller-confirmed (not independently verified)", time.time()))
    hist(lid, "Listed by " + u["name"])
    flash("Listing published.", "ok")
    return redirect("/inv")


@app.get("/inv")
@need("seller", "admin")
def inv():
    u = me()
    ls = q("SELECT * FROM listings" + ("" if u["role"] == "admin" else " WHERE seller=?"), () if u["role"] == "admin" else (u["id"],))
    return render_template("inv.html", ls=ls)


def own_listing(lid):
    u = me(); l = q1("SELECT * FROM listings WHERE id=?", (lid,))
    if not l: abort(404)
    return u, l


@app.post("/listing/<lid>/remove")
@need("seller", "admin")
def remove(lid):
    u, l = own_listing(lid)
    if u["role"] == "seller" and l["seller"] != u["id"]: abort(403)
    if q1("SELECT 1 FROM claims WHERE lid=? AND status IN ('requested','approved')", (lid,)):
        flash("Resolve open claims first.", "err")
    else:
        ex("UPDATE listings SET removed=1 WHERE id=?", (lid,)); hist(lid, "Removed by " + u["name"]); flash("Listing removed.", "ok")
    return redirect(request.referrer or "/inv")


@app.post("/listing/<lid>/restore")
@need("admin")
def restore(lid):
    ex("UPDATE listings SET removed=0 WHERE id=?", (lid,)); hist(lid, "Restored by admin (demo)")
    return redirect("/inv")


@app.post("/listing/<lid>/edit")
@need("seller")
def edit(lid):
    u, l = own_listing(lid)
    if l["seller"] != u["id"]: abort(403)
    try:
        qn = int(request.form["qty"]); p = float(request.form["price"]) if l["mode"] == "sale" else 0.0
    except (ValueError, KeyError):
        flash("Invalid numbers.", "err"); return redirect("/inv")
    if qn < claimed(l) or (l["mode"] == "sale" and not (l["minp"] <= p <= l["orig"])):
        flash(f"Quantity must be at least {claimed(l)} and price between your minimum and the original price.", "err")
    else:
        hist(lid, f"Edited: qty {l['qty']} -> {qn}"); ex("UPDATE listings SET qty=?,price=? WHERE id=?", (qn, p, lid)); flash("Saved.", "ok")
    return redirect("/inv")


@app.post("/report/<lid>")
@need("buyer", "ngo")
def report(lid):
    ex("INSERT INTO reports VALUES(?,?,?,?)", (rid("r"), lid, me()["id"], time.time()))
    flash("Listing reported to admin (demo).", "ok")
    return redirect("/listing/" + lid)


@app.get("/claims")
@need()
def claims():
    u = me()
    cs = claim_rows("l.seller=?", (u["id"],)) if u["role"] == "seller" else claim_rows("c.uid=?", (u["id"],))
    return render_template("page.html", title="Requests and orders", note="", actions=[], sts=[], charts=[], alerts=None,
                           ctitle="", claims=cs, reports=None)


@app.route("/finance", methods=["GET"])
@need("seller")
def finance():
    u = me(); cat = request.args.get("cat", "")
    f = fin(u["id"], cat if cat in CATS else "")
    rows = [("Revenue (completed sales)", f["rev"]), ("Cost of goods sold", f["cogs"]), ("Gross profit / loss", f["gp"]),
            ("Operating expenses (all categories)", f["exp"]), ("Net profit / loss", f["net"]), ("Discounts given", f["disc"]),
            ("Inventory losses (expired, at cost)", f["loss"]), ("Net after write-offs", f["net"] - f["loss"]),
            ("Donation value (separate, not revenue)", f["don"]), ("Stock at risk (reference price)", f["risk"]),
            ("Potential revenue (NOT realised)", f["pot"]), ("Potential profit (NOT realised)", f["potp"])]
    csv = ["date,item,category,type,qty,unit_price_inr,amount_inr,cost_inr"]
    for c in claim_rows("l.seller=? AND c.status='completed'", (u["id"],)):
        l = q1("SELECT * FROM listings WHERE id=?", (c["lid"],))
        csv.append(",".join(map(str, [time.strftime("%d-%m-%Y", time.localtime(c["done"])), '"' + l["name"] + '"', l["cat"],
                                      c["type"], c["qty"], c["price"], c["price"] * c["qty"], l["cost"] * c["qty"]])))
    ch = [bar("Revenue by category", [(c, fin(u["id"], c)["rev"]) for c in CATS], True),
          bar("Gross profit by category", [(c, fin(u["id"], c)["gp"]) for c in CATS], True),
          col("Completed-sale revenue, last 7 days", daily(u["id"], "rev"), True)]
    return render_template("finance.html", rows=rows, csv="\n".join(csv), charts=ch, cat=cat,
                           exps=q("SELECT * FROM expenses WHERE seller=?", (u["id"],)))


@app.post("/expense")
@need("seller")
def expense():
    try:
        a = float(request.form["amt"]); d = request.form["descr"].strip()
        assert a > 0 and d
    except Exception:
        flash("Enter a description and a positive amount.", "err"); return redirect("/finance")
    ex("INSERT INTO expenses VALUES(?,?,?,?,?)", (rid("e"), me()["id"], d, a, time.time()))
    return redirect("/finance")


@app.get("/impact")
@need("seller", "ngo", "admin")
def impact():
    u = me(); sid = u["id"] if u["role"] == "seller" else None
    f = fin(sid); un = f["sold"] + f["donu"]
    rate = round(un / (un + f["lossu"]) * 100) if un + f["lossu"] else 0
    return render_template("page.html", title="Impact dashboard", actions=[], alerts=None, ctitle="", claims=None, reports=None,
        note="Demo data only: figures come from sample records in this database, not real-world impact. Pending, approved or unclaimed items and expired stock are never counted as rescued. Donations are never counted as revenue. No kg or carbon figures are shown because there is no weight data or documented method.",
        sts=[("Units rescued", un, "completed sales + donations"), ("Completed sales", f["nsales"], ""), ("Completed donations", f["ndon"], ""),
             ("Value recovered", inr(f["rev"]), "actual completed sales"), ("Value donated (estimate)", inr(f["don"]), "reference price"),
             ("Waste value prevented (estimate)", inr(f["don"] + f["rev"] + f["disc"]), "reference price of rescued units"),
             ("Listings redistributed", len(f["red"]), ""), ("Rescue rate", f"{rate}%", "rescued / (rescued + expired unclaimed)")],
        charts=[col("Units rescued, last 7 days", daily(sid, "u")), col("Value recovered, last 7 days", daily(sid, "rev"), True)])


@app.get("/notifs")
@need()
def notifs():
    u = me()
    return render_template("notifs.html", ns=q("SELECT * FROM notifs WHERE uid=? ORDER BY ts DESC", (u["id"],)))


@app.post("/notifs/read")
@need()
def notifs_read():
    ex("UPDATE notifs SET rd=1 WHERE uid=?", (me()["id"],))
    return redirect("/notifs")


@app.route("/settings", methods=["GET", "POST"])
@need("admin")
def settings():
    if request.method == "POST":
        for k, v in request.form.items():
            try:
                v = float(v)
                if v >= 0 and q1("SELECT 1 FROM cfg WHERE k=?", (k,)): ex("UPDATE cfg SET v=? WHERE k=?", (v, k))
            except ValueError:
                pass
        flash("Settings saved.", "ok")
        return redirect("/settings")
    return render_template("settings.html", c=cf())


init_db()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
'''

FILES["static/style.css"] = r''':root{--g:#047857;--f:#064e3b;--bg:#f2f7f4;--t:#0f172a;--m:#64748b;--l:#e2e8f0}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--t)}
button,input,select,textarea{font:inherit}
a{color:var(--g)}
.btn{display:inline-block;background:var(--g);color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;font-weight:600;text-decoration:none}
.btn:hover{background:var(--f)}.btn.o{background:#fff;color:var(--g);border:1px solid var(--g)}
.btn.r{background:#b91c1c}.btn.s{padding:4px 9px;font-size:13px}.btn.x{background:#cbd5e1;color:#475569}
input,select,textarea{border:1px solid #cbd5e1;border-radius:8px;padding:8px;width:100%;background:#fff}
input[type=checkbox]{width:auto}
label{font-size:13px;color:var(--m);display:block}
.layout{display:flex;min-height:100vh}
.side{width:230px;background:var(--f);color:#fff;padding:16px;flex-shrink:0}
.side a{display:block;padding:9px 12px;border-radius:8px;color:#d1fae5;text-decoration:none;margin:2px 0}
.side a.on,.side a:hover{background:#065f46;color:#fff}
.main{flex:1;padding:20px;min-width:0}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(210px,1fr))}
.g2{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));margin:14px 0}
.card{background:#fff;border-radius:12px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.k{font-size:22px;font-weight:700}.sub{font-size:12px;color:var(--m)}
.b{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:700;color:#fff;display:inline-block}
.green{background:#047857}.amber{background:#b45309}.orange{background:#c2410c}.red{background:#b91c1c}.grey{background:#64748b}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px;border-bottom:1px solid var(--l);vertical-align:top}
.tw{overflow-x:auto}
.bar{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:13px}
.bar span{width:110px;flex-shrink:0}.bar i{display:block;height:14px;background:var(--g);border-radius:4px;min-width:2px}
.cols{display:flex;align-items:flex-end;gap:8px;height:150px;margin-top:8px}
.cols div{flex:1;text-align:center;font-size:11px}.cols i{display:block;background:var(--g);border-radius:4px 4px 0 0;min-height:2px}
.warn{background:#fef3c7;border-radius:8px;padding:8px;font-size:13px;margin-bottom:12px}
.msg{padding:8px 12px;border-radius:8px;margin-bottom:10px;color:#fff}.msg.ok{background:#047857}.msg.err{background:#b91c1c}
.hero{background:#ecfdf5;padding:50px 20px;text-align:center}
.wrap{max-width:1000px;margin:auto;padding:20px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.row>*{flex:1;min-width:130px}
.f2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.ico{font-size:34px}h1,h2,h3{color:var(--f)}
@media(max-width:800px){.layout{display:block}.side{width:auto;display:flex;overflow-x:auto;gap:4px;padding:8px}
.side a{white-space:nowrap}.side h2,.side .u{display:none}}
'''

FILES["static/app.js"] = r'''function leftText(t) {
  var ms = t * 1000 - Date.now();
  if (ms <= 0) return "Expired";
  var m = Math.floor(ms / 60000), d = Math.floor(m / 1440), h = Math.floor(m % 1440 / 60);
  if (d >= 1) return d + "d " + h + "h remaining";
  if (h >= 1) return h + "h " + (m % 60) + "m remaining";
  return m + "m " + Math.floor(ms / 1000 % 60) + "s remaining";
}
setInterval(function () {
  document.querySelectorAll("[data-exp]").forEach(function (e) { e.textContent = leftText(+e.dataset.exp); });
}, 1000);

var inrFmt = new Intl.NumberFormat("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 2});
var af = document.getElementById("addform");
if (af) {
  var calcBox = document.getElementById("calc"), priceBox = document.getElementById("f_price");
  var timer = null, rec = null;
  function val(n) { return af.elements[n] ? af.elements[n].value : ""; }
  function refresh() {
    var exp = new Date(val("exp")).getTime() / 1000;
    af.elements["exp_ts"].value = isNaN(exp) ? "" : exp;
    clearTimeout(timer);
    timer = setTimeout(function () {
      fetch("/calc", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cat: val("cat"), orig: val("orig"), cost: val("cost"), qty: val("qty"),
                              minp: val("minp"), exp: exp, strat: val("strat")})})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.error) { calcBox.textContent = d.error; rec = null; return; }
          rec = d;
          calcBox.innerHTML = "<table>" +
            "<tr><td>Original price</td><td>" + inrFmt.format(val("orig")) + "</td></tr>" +
            "<tr><td>Recommended discount</td><td>" + d.pct + "%" + (d.floored ? " (held at your minimum price)" : "") + "</td></tr>" +
            "<tr><td>Discount amount</td><td>" + inrFmt.format(d.disc) + " per unit</td></tr>" +
            "<tr><td><b>Recommended price</b></td><td><b>" + inrFmt.format(d.price) + "</b></td></tr>" +
            "<tr><td>Your purchase cost</td><td>" + inrFmt.format(val("cost") || 0) + "</td></tr>" +
            "<tr><td>Potential proceeds (if all sell)</td><td>" + inrFmt.format(d.proceeds) + "</td></tr>" +
            "<tr><td>Potential " + (d.profit < 0 ? "loss" : "profit") + " (not realised)</td><td>" + inrFmt.format(d.profit) + "</td></tr>" +
            "<tr><td>Quantity</td><td>" + val("qty") + "</td></tr>" +
            "<tr><td>Time remaining</td><td>" + leftText(exp) + "</td></tr></table>" +
            (d.critical ? "<div class='warn'>Critical: act now, but only list if the product is still safe and eligible.</div>" : "") +
            "<p class='sub'>Rule-based estimate. It does not guarantee a sale.</p>";
        })
        .catch(function () { calcBox.textContent = "Could not reach the server."; });
    }, 250);
  }
  af.addEventListener("input", refresh);
  af.addEventListener("change", refresh);
  var useBtn = document.getElementById("userec");
  if (useBtn) useBtn.addEventListener("click", function () { if (rec) priceBox.value = rec.price; });
  var file = document.getElementById("scanfile");
  if (file) file.addEventListener("change", function () {
    var f = file.files[0];
    if (!f) return;
    document.getElementById("pv").innerHTML = "<img src='" + URL.createObjectURL(f) +
      "' style='max-width:100%;max-height:200px;margin-top:8px;border-radius:8px'>" +
      "<div class='sub'>Preview only. No fields were extracted.</div>";
  });
}
'''

FILES["templates/base.html"] = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SmartRescue</title><link rel="stylesheet" href="/static/style.css"></head><body>
{% if me %}
<div class="layout"><nav class="side"><h2>SmartRescue</h2><div class="u sub" style="color:#a7f3d0;margin-bottom:8px">{{ me.name }}</div>
{% for u,t in nav %}<a href="{{u}}" class="{{ 'on' if request.path==u }}">{{t}}{% if u=='/notifs' and unread %} ({{unread}}){% endif %}</a>{% endfor %}
<a href="/logout">Switch role</a></nav>
<main class="main"><div class="warn">DEMO MODE: fictional data stored in a local SQLite file. Demo logins are not real accounts or verified organisations. No real payments, GPS, SMS or email.</div>
{% for c,m in get_flashed_messages(with_categories=true) %}<div class="msg {{c}}">{{m}}</div>{% endfor %}
{% block body %}{% endblock %}</main></div>
{% else %}{% block public %}{% endblock %}{% endif %}
<script src="/static/app.js"></script></body></html>
'''

FILES["templates/macros.html"] = r'''{% macro badge(l) %}{% set u=urg(l) %}<span class="b {{u[0]}}">{{u[1]}}</span>{% endmacro %}
{% macro cd(l) %}<span data-exp="{{l.exp}}">{{ left(l.exp) }}</span>{% endmacro %}
{% macro stats(items) %}<div class="grid">{% for a,b,c in items %}<div class="card"><div class="sub">{{a}}</div><div class="k">{{b}}</div><div class="sub">{{c}}</div></div>{% endfor %}</div>{% endmacro %}
{% macro chart(c) %}<div class="card"><b>{{c.title}}</b>
{% set mx=([1]+(c.data|map(attribute=1)|map('abs')|list))|max %}
{% if c.kind=='bar' %}{% for l,v in c.data %}<div class="bar"><span>{{l}}</span><i style="width:{{ ((v|abs)/mx*55)|round|int }}%"></i><b>{{ inr(v) if c.money else v }}</b></div>{% endfor %}
{% else %}<div class="cols">{% for l,v in c.data %}<div><span class="sub">{{ inr(v) if c.money else v }}</span><i style="height:{{ ((v|abs)/mx*90)|round|int }}px"></i>{{l}}</div>{% endfor %}</div>{% endif %}</div>{% endmacro %}
{% macro btn(id,act,label,cls='') %}<form method="post" action="/claim-action/{{id}}/{{act}}" style="display:inline"><button class="btn s {{cls}}">{{label}}</button></form> {% endmacro %}
{% macro claims_table(cs) %}{% if not cs %}<div class="card sub">No records yet.</div>{% else %}
<div class="card tw"><table><tr><th>Item</th><th>Qty</th><th>Type</th><th>Amount</th><th>Status</th><th>Pickup</th><th>Action</th></tr>
{% for c in cs %}{% set s = (me.role=='seller' and c.seller==me.id) %}
<tr><td>{{c.name}}<div class="sub">{{c.uname}}</div></td><td>{{c.qty}}</td><td>{{c.type}}</td>
<td>{% if c.type=='sale' %}{{ inr(c.price*c.qty) }}{% else %}Donation, est. {{ inr(c.orig*c.qty) }}{% endif %}</td>
<td>{{c.status}}</td><td class="sub">{{ c.pickup or '-' }}</td><td>
{% if c.status=='requested' %}{% if s %}{{ btn(c.id,'approve','Approve') }}{{ btn(c.id,'reject','Reject','r') }}{% endif %}{% if c.uid==me.id %}{{ btn(c.id,'reject','Cancel','o') }}{% endif %}{% endif %}
{% if c.status=='approved' %}{% if c.type=='sale' and s %}{{ btn(c.id,'complete','Mark sale completed') }}{% endif %}{% if c.type=='donation' and (c.uid==me.id or s) %}{{ btn(c.id,'complete','Confirm collection') }}{% endif %}{% endif %}
</td></tr>{% endfor %}</table></div>{% endif %}{% endmacro %}
'''

FILES["templates/landing.html"] = r'''{% extends "base.html" %}
{% block public %}
<div class="hero"><h1 style="font-size:40px;margin:0">SmartRescue</h1>
<p style="font-size:18px"><b>Save Stock. Recover Value. Reduce Waste.</b></p>
<p style="max-width:640px;margin:10px auto">Small grocers, pharmacies and distributors throw away short-shelf-life stock because selling it fast is hard. SmartRescue lists it, suggests a discount from the time left, and connects it with nearby buyers and NGOs, least time remaining first.</p>
<a class="btn" href="/login/b1?next=/market">Explore Marketplace</a> <a class="btn o" href="#roles">Get Started</a></div>
<div class="wrap">
<div class="grid"><div class="card"><div class="sub">Demo statistic</div><div class="k">{{ f.sold+f.donu }} units</div><div class="sub">rescued in sample data</div></div>
<div class="card"><div class="sub">Demo statistic</div><div class="k">{{ inr(f.rev) }}</div><div class="sub">recovered (sample sales)</div></div>
<div class="card"><div class="sub">Demo statistic</div><div class="k">{{ inr(f.don) }}</div><div class="sub">donated, est. (sample)</div></div></div>
<h2>How it works</h2><div class="grid"><div class="card"><b>1. List</b><br>Add or scan a product and confirm its expiry.</div><div class="card"><b>2. Price</b><br>Get a discount recommendation from time left and cost.</div><div class="card"><b>3. Match</b><br>Buyers and NGOs see the most urgent items first.</div><div class="card"><b>4. Complete</b><br>Approve, hand over, and see profit and impact update.</div></div>
<h2>Features</h2><div class="grid"><div class="card">Live expiry countdowns with configurable urgency</div><div class="card">Smart discount calculator in INR</div><div class="card">Buyer and NGO match scores with reasons</div><div class="card">Profit and loss and impact dashboards</div><div class="card">Label scanner with an honest manual fallback</div><div class="card">Server-side atomic claims and expiry checks</div></div>
<h2 id="roles">Choose a demo role</h2>
<div class="grid">{% for id,n,d in roles %}<div class="card"><b>{{n}}</b><p class="sub">{{d}}</p><a class="btn s" href="/login/{{id}}">Enter</a></div>{% endfor %}</div>
<p class="sub" style="margin-top:30px">DEMO MODE: all accounts, places, products and numbers are fictional. No real payments, GPS, SMS or email.</p>
<form method="post" action="/reset"><button class="btn o s">Reset demo data</button></form></div>
{% endblock %}
'''

FILES["templates/page.html"] = r'''{% extends "base.html" %}
{% from "macros.html" import badge,cd,stats,chart,claims_table with context %}
{% block body %}<h1>{{title}}</h1>
{% if actions %}<p>{% for u,t in actions %}<a class="btn o" href="{{u}}">{{t}}</a> {% endfor %}</p>{% endif %}
{% if note %}<div class="warn">{{note}}</div>{% endif %}
{% if sts %}{{ stats(sts) }}{% endif %}
{% if alerts is not none %}<h3>Urgent expiry alerts</h3>{% if alerts %}<div class="card">{% for l in alerts %}<div>{{badge(l)}} <a href="/listing/{{l.id}}">{{l.name}}</a> - {{cd(l)}}</div>{% endfor %}</div>{% else %}<div class="card sub">No urgent listings.</div>{% endif %}{% endif %}
{% if charts %}<div class="g2">{% for c in charts %}{{ chart(c) }}{% endfor %}</div>{% endif %}
{% if claims is not none %}{% if ctitle %}<h3>{{ctitle}}</h3>{% endif %}{{ claims_table(claims) }}{% endif %}
{% if reports is not none %}<h3>Reported listings</h3>{% if reports %}<div class="card tw"><table>{% for r in reports %}<tr><td>{{r.name}}</td><td>{{r.uname}}</td><td>{{ dt(r.ts) }}</td><td><a class="btn s" href="/listing/{{r.lid}}">Review</a>
<form method="post" action="/listing/{{r.lid}}/remove" style="display:inline" onsubmit="return confirm('Remove this listing?')"><button class="btn r s">Remove</button></form></td></tr>{% endfor %}</table></div>{% else %}<div class="card sub">No reports.</div>{% endif %}{% endif %}
{% endblock %}
'''

FILES["templates/market.html"] = r'''{% extends "base.html" %}
{% from "macros.html" import badge,cd with context %}
{% block body %}<h1>{{ 'Donation listings' if me.role=='ngo' else 'Marketplace' }}</h1>
<form class="card row" method="get" style="margin-bottom:12px">
<div><label>Search</label><input name="q" value="{{f.q}}"></div>
<div><label>Category</label><select name="cat"><option value="">All</option>{% for c in CATS %}<option {{ 'selected' if f.cat==c }}>{{c}}</option>{% endfor %}</select></div>
<div><label>Urgency</label><select name="urg">{% for v,t in [('','All'),('red','Critical'),('orange','Urgent'),('amber','Soon'),('green','Fresh')] %}<option value="{{v}}" {{ 'selected' if f.urg==v }}>{{t}}</option>{% endfor %}</select></div>
<div><label>Max price (INR)</label><input name="maxp" type="number" value="{{f.maxp}}"></div>
<div><label>Min discount %</label><input name="mind" type="number" value="{{f.mind}}"></div>
<div><label>Area or PIN</label><input name="area" value="{{f.area}}"></div>
<div><label>Sort</label><select name="sort">{% for v,t in [('urgency','Urgency (least time first)'),('price','Lowest price'),('discount','Highest discount'),('qty','Quantity'),('dist','Nearest area first')] %}<option value="{{v}}" {{ 'selected' if f.sort==v }}>{{t}}</option>{% endfor %}</select></div>
<button class="btn">Apply</button></form>
<div class="grid">{% for l in items %}<div class="card"><div class="ico">{{ ICON[l.cat]|safe }}</div><b>{{l.name}}</b>
<div class="sub">{{l.cat}} | Pickup: {{l.area}} (sample)</div><div style="margin:6px 0">{{badge(l)}} {{cd(l)}}</div>
<div>{% if l.mode=='donate' %}<b>Free (donation)</b> <s class="sub">{{ inr(l.orig) }}</s>{% else %}<b>{{ inr(l.price) }}</b> <s class="sub">{{ inr(l.orig) }}</s> <span class="sub">{{ dp(l) }}% off</span>{% endif %}</div>
<div class="sub">{{ avail(l) }} units available | {{ status(l) }}</div>
<a class="btn s {{ '' if hrs(l)>0 and avail(l)>0 else 'x' }}" style="margin-top:8px" href="/listing/{{l.id}}">{{ ('Request' if l.mode=='donate' else 'Claim') if hrs(l)>0 and avail(l)>0 else 'Unavailable' }}</a></div>
{% else %}<div class="card">No listings match your filters.</div>{% endfor %}</div>{% endblock %}
'''

FILES["templates/listing.html"] = r'''{% extends "base.html" %}
{% from "macros.html" import badge,cd with context %}
{% block body %}<a href="/market">&larr; Back</a>
<div class="card" style="margin-top:8px"><div class="ico">{{ ICON[l.cat]|safe }}</div><h2 style="margin:0">{{l.name}}</h2>
<p>{{badge(l)}} <b>{{cd(l)}}</b> <span class="sub">(expires {{ dt(l.exp) }}, server local time)</span></p>
<div class="tw"><table>
<tr><td>Category</td><td>{{l.cat}}</td><td>Status</td><td>{{ status(l) }}</td></tr>
<tr><td>Price</td><td>{% if l.mode=='donate' %}Free (donation), ref. {{ inr(l.orig) }}{% else %}{{ inr(l.price) }} (MRP {{ inr(l.orig) }}, {{ dp(l) }}% off){% endif %}</td><td>Available</td><td>{{ avail(l) }} of {{ l.qty }}</td></tr>
<tr><td>Batch</td><td>{{ l.batch or '-' }}</td><td>Verification</td><td>{{ l.ver }}</td></tr>
<tr><td>Pickup area</td><td>{{ l.area }} (sample)</td><td>Storage</td><td>{{ l.stor or 'Not specified' }}</td></tr>
<tr><td>Seller</td><td colspan="3">{{ seller.name }}</td></tr></table></div>
<p class="sub">Not a safety guarantee. Check the physical product and label before use.</p>
{% if me.role in ('buyer','ngo') %}
{% if (me.role=='ngo') == (l.mode=='donate') %}
{% if ok %}<form method="post" action="/claim/{{l.id}}" class="row"><div><label>Quantity (max {{ avail(l) }})</label><input name="qty" type="number" min="1" max="{{ avail(l) }}" value="1"></div>
<button class="btn">{{ 'Request donation' if l.mode=='donate' else 'Claim' }}</button></form>
<p class="sub">Expiry and quantity are re-checked on the server when you submit. This is a request: nothing is purchased or received until the seller approves and handover is marked completed. No payment is processed here.</p>
{% else %}<div class="warn">Cannot be claimed (status: {{ status(l) }}).</div>{% endif %}
{% else %}<div class="warn">This listing is for {{ 'NGOs' if l.mode=='donate' else 'buyers' }}.</div>{% endif %}
<form method="post" action="/report/{{l.id}}"><button class="btn o s">Report listing</button></form>{% endif %}
{% if matches %}<h3>Suggested buyers and NGOs</h3><div class="tw"><table><tr><th>Who</th><th>Score</th><th>Why</th></tr>
{% for m in matches %}<tr><td>{{ m.u.name }}</td><td><b>{{ m.s }}</b><div class="sub">{{ m.tag }}</div></td><td class="sub">{{ m.w }}</td></tr>{% endfor %}</table></div>
<p class="sub">Sample locations; distances are rough estimates from area centres. Nobody is contacted automatically.</p>{% endif %}
<h3>History</h3><div class="sub">{% for x in h %}{{ dt(x.ts) }} - {{ x.msg }}<br>{% endfor %}</div></div>{% endblock %}
'''

FILES["templates/add.html"] = r'''{% extends "base.html" %}
{% block body %}<h1>Add / scan product</h1>
<div class="card"><h3>1. Scan label (optional)</h3><input type="file" id="scanfile" accept="image/*"><div id="pv"></div>
<div class="warn" style="margin-top:8px">AI scanning is NOT connected in this build: no vision API is configured, so nothing is extracted and no OCR result is invented. Read the label and type the details below. A vision model (e.g. Gemini) should be called from the server so the key never reaches the browser, and its output would still need your confirmation.</div></div>
<form id="addform" method="post" class="g2">
<div class="card"><h3>2. Product details</h3><div class="f2">
<div><label>Product name</label><input name="name" required placeholder="Could not confidently identify - enter manually"></div>
<div><label>Category</label><select name="cat">{% for c in CATS %}<option>{{c}}</option>{% endfor %}</select></div>
<div><label>Original price per unit (INR)</label><input name="orig" type="number" min="0" step="0.01" required></div>
<div><label>Purchase cost per unit (INR)</label><input name="cost" type="number" min="0" step="0.01" required></div>
<div><label>Quantity</label><input name="qty" type="number" min="1" step="1" required></div>
<div><label>Minimum acceptable price (INR)</label><input name="minp" type="number" min="0" step="0.01" value="0"></div>
<div><label>Expiry date and time (your local time)</label><input name="exp" type="datetime-local" required><input type="hidden" name="exp_ts"></div>
<div><label>Batch / lot number</label><input name="batch" placeholder="Enter manually"></div>
<div><label>Strategy</label><select name="strat"><option value="bal">Balanced</option><option value="fast">Sell fast</option><option value="value">Maximise value</option></select></div>
<div><label>Listing type</label><select name="mode"><option value="sale">Sell at discount</option><option value="donate">Donate to NGO</option></select></div>
<div><label>Pickup area (sample)</label><select name="area">{% for a in AREAS %}<option>{{a}}</option>{% endfor %}</select></div>
<div><label>Storage</label><input name="stor" placeholder="e.g. Keep chilled 2-8 C"></div>
<div><label>Condition</label><select name="cond"><option value="ok">Sealed and undamaged</option><option value="bad">Damaged, opened or recalled</option></select></div></div></div>
<div><div class="card"><h3>3. Discount calculator</h3><div id="calc" class="sub">Enter price, quantity and a future expiry.</div></div>
<div class="card" style="margin-top:14px"><h3>4. Confirm and publish</h3>
<label>Final price per unit (INR; ignored for donations)</label><input id="f_price" name="price" type="number" min="0" step="0.01">
<p><button type="button" id="userec" class="btn o s">Use recommended price</button></p>
<label><input type="checkbox" name="ov"> Override: allow price below my minimum</label>
<label><input type="checkbox" name="ok1"> I checked the expiry date on the physical product</label>
<label><input type="checkbox" name="ok2"> This product is safe, undamaged, not recalled and legal to sell or donate</label>
<label><input type="checkbox" name="auth"> Pharmacy (OTC) only: I hold the required licence and keep batch records</label>
<div class="warn" style="margin-top:8px">Prescription or restricted medicines are not allowed here. Being unexpired does not mean a product is safe.</div>
<button class="btn">Publish listing</button></div></div></form>{% endblock %}
'''

FILES["templates/inv.html"] = r'''{% extends "base.html" %}
{% from "macros.html" import badge,cd with context %}
{% block body %}<h1>{{ 'All listings' if me.role=='admin' else 'Inventory' }}</h1>
{% if ls %}<div class="card tw"><table><tr><th>Item</th><th>Status</th><th>Left / total</th><th>Price</th><th>Expiry</th><th>Actions</th></tr>
{% for l in ls %}<tr><td><a href="/listing/{{l.id}}">{{l.name}}</a><div class="sub">{{l.cat}} | {{l.id}} | {{l.mode}}</div></td><td>{{ status(l) }}</td>
<td>{{ avail(l) }} / {{ l.qty }}</td><td>{{ 'Free' if l.mode=='donate' else inr(l.price) }}</td><td>{{badge(l)}}<div class="sub">{{cd(l)}}</div></td><td>
{% if me.role=='seller' and l.seller==me.id and not l.removed %}<form method="post" action="/listing/{{l.id}}/edit" class="row" style="margin-bottom:4px"><input name="qty" type="number" value="{{l.qty}}" style="min-width:60px"><input name="price" type="number" step="0.01" value="{{l.price}}" style="min-width:70px"><button class="btn o s">Save</button></form>{% endif %}
{% if l.removed %}{% if me.role=='admin' %}<form method="post" action="/listing/{{l.id}}/restore"><button class="btn s">Restore</button></form>{% endif %}
{% else %}<form method="post" action="/listing/{{l.id}}/remove" onsubmit="return confirm('Remove this listing?')"><button class="btn r s">Remove</button></form>{% endif %}
</td></tr>{% endfor %}</table></div>{% else %}<div class="card">No listings yet.</div>{% endif %}{% endblock %}
'''

FILES["templates/finance.html"] = r'''{% extends "base.html" %}
{% from "macros.html" import chart with context %}
{% block body %}<h1>Profit and loss</h1>
<form method="get" class="row"><div><label>Category</label><select name="cat" onchange="this.form.submit()"><option value="">All</option>{% for c in CATS %}<option {{ 'selected' if cat==c }}>{{c}}</option>{% endfor %}</select></div></form>
<div class="g2"><div class="card tw"><table>{% for a,b in rows %}<tr><td>{{a}}</td><td><b>{{ inr(b) }}</b></td></tr>{% endfor %}</table></div>
<div class="card"><b>How it is calculated</b><p class="sub">Revenue = actual price x units for completed sales only. COGS = purchase cost x units sold. Gross = revenue - COGS. Net = gross - recorded expenses. Loss = cost of units left on expired listings. Discount = (original - actual price) x units sold. Donation value = original price x units in completed donations, kept separate. Potential figures are estimates from available stock and are never included in revenue or realised profit.</p>
<label>Add expense</label><form method="post" action="/expense" class="row"><input name="descr" placeholder="Description"><input name="amt" type="number" step="0.01" placeholder="Amount INR"><button class="btn s">Add</button></form>
{% for e in exps %}<div class="sub">{{ dt(e.ts) }} - {{ e.descr }}: {{ inr(e.amt) }}</div>{% endfor %}</div></div>
<div class="g2">{% for c in charts %}{{ chart(c) }}{% endfor %}</div>
<div class="card"><b>CSV (select all and copy into a sheet)</b><textarea rows="6" readonly onclick="this.select()">{{csv}}</textarea></div>{% endblock %}
'''

FILES["templates/notifs.html"] = r'''{% extends "base.html" %}
{% block body %}<h1>Notifications</h1>
<p class="sub">In-app only (simulated). No email, SMS or WhatsApp is sent.</p>
<form method="post" action="/notifs/read"><button class="btn o s">Mark all read</button></form><br>
{% for n in ns %}<div class="card" style="margin-bottom:8px;{{ 'opacity:.65' if n.rd else 'border-left:4px solid var(--g)' }}">{{ n.msg }}<div class="sub">{{ dt(n.ts) }}</div></div>
{% else %}<div class="card sub">No notifications.</div>{% endfor %}{% endblock %}
'''

FILES["templates/settings.html"] = r'''{% extends "base.html" %}
{% block body %}<h1>Settings (demo admin)</h1>
<form method="post" class="card"><h3>Urgency thresholds (hours)</h3>
<div class="row"><div><label>Red below</label><input name="red" type="number" value="{{ c.red|int }}"></div>
<div><label>Orange below</label><input name="orange" type="number" value="{{ c.orange|int }}"></div>
<div><label>Amber up to</label><input name="amber" type="number" value="{{ c.amber|int }}"></div></div>
<h3>Category discount multipliers</h3><div class="row">{% for k in CATS %}<div><label>{{k}}</label><input name="m_{{k}}" type="number" step="0.05" value="{{ c['m_'+k] }}"></div>{% endfor %}</div>
<p class="sub">Base discount: over 72h 10%, 24-72h 25%, 6-24h 40%, under 6h 55%; times the multiplier; +5 if over 50 units; capped at 70%. These are starting rules, not food-safety standards.</p>
<button class="btn">Save</button></form>
<form method="post" action="/reset" style="margin-top:12px" onsubmit="return confirm('Reset all demo data?')"><button class="btn r">Reset demo data</button></form>{% endblock %}
'''

root = "smartrescue"
for path, text in FILES.items():
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full) or root, exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
print("Created folder:", os.path.abspath(root))
print("Next: cd smartrescue ; pip install -r requirements.txt ; python app.py")
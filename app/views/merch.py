"""Merchandise: products sold in the clinic (oral care, orthodontic care, medicines, denture care...).

A sale (MS-000001) has its own receipt and payments, apart from patient bills, for a clinic patient or anyone buying.
Stock is kept per branch: stock in (with cost and expiry), sales take it out, a count fixes it; every change is logged in
merch_moves. A voided sale puts its stock back. Medicines marked "Rx" show a reminder that a prescription is needed.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..billing import pay_options, parse_pay
from ..db import get_db
from ..permissions import can_see_patient
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import date_range_args
from .xray import _marks, pay_label

bp = Blueprint("merch", __name__, url_prefix="/staff/merch")

CATEGORIES = ["Oral care", "Orthodontic care", "Medicines", "Denture care", "Whitening & others", "Others"]
UNITS = ["pc", "pack", "box", "tube", "bottle", "tablet", "capsule", "kit", "sachet"]
MAX_LINES = 12
EXPIRY_WARN_DAYS = 60


def _scope():
    return list(g.user.scope_branch_ids)


def _branches(conn, ids):
    return conn.all(f"SELECT id, name FROM branches WHERE active = 1 AND id IN ({_marks(ids)}) ORDER BY sort_order", list(ids)) if ids else []


def products(conn, active_only=True):
    return conn.all("SELECT * FROM merch_products" + (" WHERE active = 1" if active_only else "") + " ORDER BY category, sort_order, name")


def stock_of(conn, branch_id) -> dict[int, dict]:
    return {r["product_id"]: dict(r) for r in conn.all("SELECT * FROM merch_stock WHERE branch_id = ?", (branch_id,))}


def move(conn, product_id, branch_id, kind, qty, sale_id=None, unit_cost=None, expiry=None, notes=""):
    """Change the stock of a product at a branch and log it. qty is signed (+ in, − out)."""
    row = conn.one("SELECT qty, expiry_date FROM merch_stock WHERE product_id = ? AND branch_id = ?", (product_id, branch_id))
    if row:
        new_exp = row["expiry_date"]
        if expiry and qty > 0:
            new_exp = expiry if (not new_exp or row["qty"] <= 0 or expiry < new_exp) else new_exp
        conn.execute("UPDATE merch_stock SET qty = qty + ?, expiry_date = ? WHERE product_id = ? AND branch_id = ?",
                     (qty, new_exp, product_id, branch_id))
    else:
        conn.execute("INSERT INTO merch_stock (product_id, branch_id, qty, expiry_date) VALUES (?, ?, ?, ?)",
                     (product_id, branch_id, qty, expiry if qty > 0 else None))
    conn.insert("merch_moves", {"product_id": product_id, "branch_id": branch_id, "kind": kind, "qty": qty, "unit_cost_cents": unit_cost,
                                "expiry_date": expiry, "sale_id": sale_id, "notes": notes, "created_by": g.user.id, "created_at": now_str()})


def _load(sale_id):
    s = get_db().one("SELECT s.*, b.name AS branch, b.address AS branch_address, b.phone AS branch_phone, p.first_name, p.last_name, "
                     "p.chart_no, u.name AS created_name FROM merch_sales s JOIN branches b ON b.id = s.branch_id "
                     "LEFT JOIN patients p ON p.id = s.patient_id LEFT JOIN users u ON u.id = s.created_by WHERE s.id = ?", (sale_id,))
    if not s or not g.user.in_branch(s["branch_id"]):
        abort(404)
    return s


def buyer(s) -> str:
    if s["patient_id"]:
        return f"{s['last_name']}, {s['first_name']}"
    return s["buyer_name"] or "Walk-in"


def paid_of(conn, ids) -> dict[int, int]:
    ids = list(ids)
    if not ids:
        return {}
    return {r["sale_id"]: r["amt"] for r in conn.all(
        f"SELECT sale_id, SUM(amount_cents) AS amt FROM merch_payments WHERE status = 'valid' AND sale_id IN ({_marks(ids)}) GROUP BY sale_id", ids)}


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------

@bp.route("/")
@require("merch.view")
def index():
    conn = get_db()
    start, end = date_range_args(31)
    scope = _scope()
    q = clean(request.args.get("q"), 80)
    show = request.args.get("show", "")
    where = [f"s.branch_id IN ({_marks(scope)})", "s.sold_on BETWEEN ? AND ?"]
    args = [*scope, start.isoformat(), end.isoformat()]
    if q:
        like = f"%{q}%"
        where.append("(s.number LIKE ? OR s.buyer_name LIKE ? OR p.first_name || ' ' || p.last_name LIKE ? OR p.chart_no LIKE ? "
                     "OR s.id IN (SELECT sale_id FROM merch_sale_items WHERE description LIKE ?))")
        args += [like] * 5
    if show != "void":
        where.append("s.status = 'ok'")
    rows = conn.all("SELECT s.*, b.name AS branch, p.first_name, p.last_name, p.chart_no, "
                    "(SELECT group_concat(description || ' ×' || qty, ', ') FROM merch_sale_items WHERE sale_id = s.id) AS what "
                    "FROM merch_sales s JOIN branches b ON b.id = s.branch_id LEFT JOIN patients p ON p.id = s.patient_id "
                    f"WHERE {' AND '.join(where)} ORDER BY s.sold_on DESC, s.id DESC LIMIT 500", args)
    paid = paid_of(conn, [r["id"] for r in rows])
    items = [{**dict(r), "who": buyer(r), "paid": paid.get(r["id"], 0),
              "balance": r["total_cents"] - paid.get(r["id"], 0) if r["status"] == "ok" else 0} for r in rows]
    if show == "balance":
        items = [i for i in items if i["balance"] > 0]
    ok = [i for i in items if i["status"] == "ok"]
    totals = {"n": len(ok), "total": sum(i["total_cents"] for i in ok), "paid": sum(i["paid"] for i in ok),
              "balance": sum(i["balance"] for i in ok)}
    low = _low_stock(conn, scope)
    return render_template("staff/merch/index.html", items=items, totals=totals, start=start, end=end, q=q, show=show, low=low)


def _low_stock(conn, scope):
    if not scope:
        return {"low": 0, "expiring": 0}
    soon = (today() + timedelta(days=EXPIRY_WARN_DAYS)).isoformat()
    low = conn.scalar(f"SELECT COUNT(*) FROM merch_products p JOIN branches b ON b.id IN ({_marks(scope)}) "
                      "LEFT JOIN merch_stock s ON s.product_id = p.id AND s.branch_id = b.id "
                      "WHERE p.active = 1 AND p.reorder_level > 0 AND COALESCE(s.qty, 0) <= p.reorder_level", scope) or 0
    exp = conn.scalar(f"SELECT COUNT(*) FROM merch_stock WHERE branch_id IN ({_marks(scope)}) AND qty > 0 AND expiry_date IS NOT NULL "
                      "AND expiry_date <= ?", [*scope, soon]) or 0
    return {"low": low, "expiring": exp}


@bp.route("/new", methods=["GET", "POST"])
@require("merch.sell")
def new():
    conn = get_db()
    mine = list(g.user.branch_ids)
    branch_id = to_int(request.values.get("branch_id")) or g.user.active_branch_id or (mine[0] if mine else None)
    if branch_id not in mine:
        branch_id = mine[0] if mine else None
    patient = None
    pid = to_int(request.values.get("patient_id"))
    if pid:
        if not can_see_patient(conn, g.user, pid):
            abort(403)
        patient = conn.one("SELECT id, first_name, last_name, chart_no FROM patients WHERE id = ?", (pid,))
    prods = products(conn)
    stock = stock_of(conn, branch_id) if branch_id else {}
    v = {"chart_no": patient["chart_no"] if patient else "", "buyer_name": "", "discount": "", "notes": "",
         "lines": [{"product_id": None, "qty": "1", "price": ""}]}
    errors = []
    if request.method == "POST":
        f = request.form
        v = {"chart_no": clean(f.get("chart_no"), 40), "buyer_name": clean(f.get("buyer_name"), 120), "discount": f.get("discount") or "",
             "notes": clean(f.get("notes"), 500), "lines": []}
        pmap = {p["id"]: p for p in products(conn, active_only=False)}
        patient_id = pid
        if not patient_id and v["chart_no"]:
            p = conn.one("SELECT id FROM patients WHERE lower(chart_no) = lower(?) AND deleted_at IS NULL", (v["chart_no"],))
            if not p:
                errors.append(f"No patient with chart no. {v['chart_no']}. Leave it empty for a walk-in.")
            elif not can_see_patient(conn, g.user, p["id"]):
                abort(403)
            patient_id = p["id"] if p else None
        lines = []
        want: dict[int, int] = {}
        for i in range(MAX_LINES):
            prod_id = to_int(f.get(f"product_{i}"))
            raw_q, raw_p = (f.get(f"qty_{i}") or "").strip(), (f.get(f"price_{i}") or "").strip()
            if not prod_id:
                continue
            v["lines"].append({"product_id": prod_id, "qty": raw_q, "price": raw_p})
            pr = pmap.get(prod_id)
            qty = to_int(raw_q)
            if not pr:
                errors.append(f"Line {i + 1}: choose a product.")
                continue
            if not qty or qty < 1 or qty > 999:
                errors.append(f"{pr['name']}: enter the quantity.")
                continue
            price = parse_money(raw_p) if raw_p else pr["price_cents"]
            if price is None or price < 0:
                errors.append(f"{pr['name']}: enter the price (no price is set for this product yet).")
                continue
            want[prod_id] = want.get(prod_id, 0) + qty
            lines.append({"product_id": prod_id, "description": pr["name"], "qty": qty, "unit_price_cents": price,
                          "unit_cost_cents": pr["cost_cents"], "amount_cents": qty * price})
        if not v["lines"]:
            v["lines"] = [{"product_id": None, "qty": "1", "price": ""}]
            errors.append("Add at least one product.")
        stock = stock_of(conn, branch_id)
        for prod_id, n in want.items():
            have = (stock.get(prod_id) or {}).get("qty", 0)
            if n > have:
                errors.append(f"{pmap[prod_id]['name']}: only {have} in stock at this branch. Stock in first (Merchandise → Stock).")
        subtotal = sum(l["amount_cents"] for l in lines)
        discount = parse_money(v["discount"]) if v["discount"].strip() else 0
        if discount is None or discount < 0 or discount > subtotal:
            errors.append("The discount must be between 0 and the total.")
            discount = 0
        total = subtotal - discount
        raw_pay = (f.get("pay_amount") or "").strip()
        pay_amt = parse_money(raw_pay) if raw_pay else total
        pay = parse_pay(f.get("pay_method"), conn)
        if pay_amt is None or pay_amt < 0 or pay_amt > total:
            errors.append("The payment can't be more than the total.")
        elif pay_amt and not pay:
            errors.append("Choose how the payment was made.")
        if branch_id not in mine:
            errors.append("Choose the branch.")
        if not errors:
            with conn.transaction(immediate=True):
                nxt = (conn.scalar("SELECT MAX(id) FROM merch_sales") or 0) + 1
                number = f"MS-{nxt:06d}"
                sid = conn.insert("merch_sales", {"number": number, "branch_id": branch_id, "patient_id": patient_id,
                                                  "buyer_name": "" if patient_id else v["buyer_name"], "sold_on": today().isoformat(),
                                                  "subtotal_cents": subtotal, "discount_cents": discount, "total_cents": total,
                                                  "notes": v["notes"], "status": "ok", "created_by": g.user.id, "created_at": now_str()})
                for ln in lines:
                    conn.insert("merch_sale_items", {"sale_id": sid, **ln})
                    move(conn, ln["product_id"], branch_id, "sale", -ln["qty"], sale_id=sid)
                if pay_amt:
                    conn.insert("merch_payments", {"sale_id": sid, "branch_id": branch_id, "amount_cents": pay_amt, "method": pay[0],
                                                   "account": pay[1], "reference": clean(f.get("reference"), 80), "received_at": now_str(),
                                                   "received_by": g.user.id, "created_at": now_str()})
            audit.record("merch_sale", "merch_sale", sid, f"Merchandise sale {number}", {"items": len(lines), "total": total}, branch_id)
            flash(f"Sale {number} saved." + (" Payment recorded." if pay_amt else ""), "success")
            return redirect(url_for("merch.detail", sale_id=sid))
    return render_template("staff/merch/form.html", v=v, errors=errors, patient=patient, prods=prods, stock=stock,
                           branches=_branches(conn, mine), branch_id=branch_id, pay_opts=pay_options(conn), max_lines=MAX_LINES)


@bp.route("/<int:sale_id>")
@require("merch.view")
def detail(sale_id):
    conn = get_db()
    s = _load(sale_id)
    items = conn.all("SELECT i.*, p.rx_required, p.unit FROM merch_sale_items i JOIN merch_products p ON p.id = i.product_id "
                     "WHERE i.sale_id = ? ORDER BY i.id", (sale_id,))
    pays = conn.all("SELECT p.*, u.name AS received_name FROM merch_payments p LEFT JOIN users u ON u.id = p.received_by "
                    "WHERE p.sale_id = ? ORDER BY p.received_at, p.id", (sale_id,))
    paid = sum(p["amount_cents"] for p in pays if p["status"] == "valid")
    return render_template("staff/merch/detail.html", s=s, who=buyer(s), items=items, pays=pays, paid=paid,
                           balance=s["total_cents"] - paid if s["status"] == "ok" else 0, pay_opts=pay_options(conn), pay_label=pay_label)


@bp.route("/<int:sale_id>/pay", methods=["POST"])
@require("merch.sell")
def pay(sale_id):
    conn = get_db()
    s = _load(sale_id)
    paid = paid_of(conn, [sale_id]).get(sale_id, 0)
    amt = parse_money(request.form.get("amount"))
    method = parse_pay(request.form.get("method"), conn)
    if s["status"] != "ok":
        flash("This sale is voided.", "error")
    elif not amt or amt <= 0 or amt > s["total_cents"] - paid:
        flash(f"Enter an amount up to the balance ({(s['total_cents'] - paid) / 100:,.2f}).", "error")
    elif not method:
        flash("Choose how the payment was made.", "error")
    else:
        conn.insert("merch_payments", {"sale_id": sale_id, "branch_id": s["branch_id"], "amount_cents": amt, "method": method[0],
                                       "account": method[1], "reference": clean(request.form.get("reference"), 80), "received_at": now_str(),
                                       "received_by": g.user.id, "created_at": now_str()})
        audit.record("merch_payment", "merch_sale", sale_id, f"Payment on {s['number']}", {"amount": amt}, s["branch_id"])
        flash("Payment recorded.", "success")
    return redirect(url_for("merch.detail", sale_id=sale_id))


@bp.route("/<int:sale_id>/payments/<int:pay_id>/void", methods=["POST"])
@require("merch.void")
def pay_void(sale_id, pay_id):
    conn = get_db()
    s = _load(sale_id)
    reason = clean(request.form.get("reason"), 300)
    if not conn.one("SELECT id FROM merch_payments WHERE id = ? AND sale_id = ? AND status = 'valid'", (pay_id, sale_id)):
        abort(404)
    if len(reason) < 3:
        flash("Write why the payment is voided.", "error")
    else:
        conn.execute("UPDATE merch_payments SET status = 'void', void_reason = ? WHERE id = ?", (reason, pay_id))
        audit.record("merch_payment_voided", "merch_sale", sale_id, f"Voided a payment on {s['number']}", {"payment": pay_id, "reason": reason})
        flash("Payment voided.", "success")
    return redirect(url_for("merch.detail", sale_id=sale_id))


@bp.route("/<int:sale_id>/void", methods=["POST"])
@require("merch.void")
def void(sale_id):
    conn = get_db()
    s = _load(sale_id)
    reason = clean(request.form.get("reason"), 300)
    if s["status"] != "ok":
        abort(404)
    if paid_of(conn, [sale_id]).get(sale_id, 0):
        flash("Void its payments first (or refund the buyer).", "error")
    elif len(reason) < 3:
        flash("Write why this sale is voided.", "error")
    else:
        with conn.transaction(immediate=True):
            conn.execute("UPDATE merch_sales SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                         (reason, g.user.id, now_str(), sale_id))
            if request.form.get("restock", "1") == "1":
                for it in conn.all("SELECT product_id, qty FROM merch_sale_items WHERE sale_id = ?", (sale_id,)):
                    move(conn, it["product_id"], s["branch_id"], "void", it["qty"], sale_id=sale_id, notes="Sale voided")
        audit.record("merch_sale_voided", "merch_sale", sale_id, f"Voided {s['number']}", {"reason": reason}, s["branch_id"])
        flash("Sale voided. Its stock was put back.", "success")
    return redirect(url_for("merch.detail", sale_id=sale_id))


@bp.route("/<int:sale_id>/receipt")
@require("merch.view")
def receipt(sale_id):
    conn = get_db()
    s = _load(sale_id)
    items = conn.all("SELECT * FROM merch_sale_items WHERE sale_id = ? ORDER BY id", (sale_id,))
    pays = conn.all("SELECT * FROM merch_payments WHERE sale_id = ? AND status = 'valid' ORDER BY received_at, id", (sale_id,))
    return render_template("staff/merch/receipt.html", s=s, who=buyer(s), items=items, pays=pays, paid=sum(p["amount_cents"] for p in pays),
                           pay_label=pay_label)


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

@bp.route("/stock", methods=["GET", "POST"])
@require("merch.view")
def stock():
    conn = get_db()
    mine = list(g.user.branch_ids)
    branch_id = to_int(request.values.get("branch_id")) or g.user.active_branch_id or (mine[0] if mine else None)
    if branch_id not in mine:
        abort(403)
    if request.method == "POST":
        if not g.user.can("merch.stock"):
            abort(403)
        f = request.form
        pr = conn.one("SELECT * FROM merch_products WHERE id = ?", (to_int(f.get("product_id")),))
        action = f.get("action")
        if not pr:
            flash("Choose the product.", "error")
        elif action == "in":
            qty = to_int(f.get("qty"))
            cost = parse_money(f.get("unit_cost")) if (f.get("unit_cost") or "").strip() else None
            exp = parse_date(f.get("expiry_date")) if (f.get("expiry_date") or "").strip() else None
            if not qty or qty < 1 or qty > 100000:
                flash("Enter how many came in.", "error")
            elif (f.get("expiry_date") or "").strip() and not exp:
                flash("Check the expiry date.", "error")
            else:
                with conn.transaction(immediate=True):
                    move(conn, pr["id"], branch_id, "in", qty, unit_cost=cost, expiry=exp.isoformat() if exp else None,
                         notes=clean(f.get("notes"), 200))
                    if cost is not None:
                        conn.execute("UPDATE merch_products SET cost_cents = ? WHERE id = ?", (cost, pr["id"]))
                audit.record("merch_stock_in", "merch_product", pr["id"], f"Stock in: {qty} {pr['unit']} {pr['name']}", branch_id=branch_id)
                flash(f"Added {qty} to {pr['name']}.", "success")
        elif action == "count":
            counted = to_int(f.get("counted"))
            reason = clean(f.get("notes"), 200)
            have = (conn.scalar("SELECT qty FROM merch_stock WHERE product_id = ? AND branch_id = ?", (pr["id"], branch_id)) or 0)
            if counted is None or counted < 0:
                flash("Enter the number counted.", "error")
            elif len(reason) < 3:
                flash("Write the reason (e.g. monthly count, damaged, expired).", "error")
            elif counted != have:
                with conn.transaction(immediate=True):
                    move(conn, pr["id"], branch_id, "adjust", counted - have, notes=reason)
                    if counted == 0:
                        conn.execute("UPDATE merch_stock SET expiry_date = NULL WHERE product_id = ? AND branch_id = ?", (pr["id"], branch_id))
                audit.record("merch_stock_count", "merch_product", pr["id"], f"Stock count {pr['name']}: {have} → {counted}",
                             {"reason": reason}, branch_id)
                flash(f"{pr['name']}: stock set to {counted}.", "success")
            else:
                flash("The count is the same as the stock. Nothing changed.", "info")
        elif action == "expiry":
            exp = parse_date(f.get("expiry_date")) if (f.get("expiry_date") or "").strip() else None
            conn.execute("UPDATE merch_stock SET expiry_date = ? WHERE product_id = ? AND branch_id = ?",
                         (exp.isoformat() if exp else None, pr["id"], branch_id))
            flash("Expiry date saved.", "success")
        return redirect(url_for("merch.stock", branch_id=branch_id))
    st = stock_of(conn, branch_id)
    soon = (today() + timedelta(days=EXPIRY_WARN_DAYS)).isoformat()
    rows = []
    for p in products(conn, active_only=False):
        s = st.get(p["id"]) or {}
        if not p["active"] and not s.get("qty"):
            continue
        qty = s.get("qty", 0)
        rows.append({**dict(p), "qty": qty, "expiry": s.get("expiry_date"), "low": p["reorder_level"] > 0 and qty <= p["reorder_level"],
                     "expiring": bool(qty > 0 and s.get("expiry_date") and s["expiry_date"] <= soon),
                     "expired": bool(qty > 0 and s.get("expiry_date") and s["expiry_date"] < today().isoformat())})
    value = sum(r["qty"] * (r["cost_cents"] or 0) for r in rows if r["qty"] > 0)
    moves = conn.all("SELECT m.*, p.name, u.name AS by_name FROM merch_moves m JOIN merch_products p ON p.id = m.product_id "
                     "LEFT JOIN users u ON u.id = m.created_by WHERE m.branch_id = ? AND m.kind != 'sale' ORDER BY m.id DESC LIMIT 30", (branch_id,))
    return render_template("staff/merch/stock.html", rows=rows, branches=_branches(conn, mine), branch_id=branch_id, value=value,
                           moves=moves, categories=CATEGORIES, warn_days=EXPIRY_WARN_DAYS)


# ---------------------------------------------------------------------------
# Products & prices
# ---------------------------------------------------------------------------

@bp.route("/products", methods=["GET", "POST"])
@require("merch.stock")
def product_list():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        pid = to_int(f.get("product_id"))
        name = clean(f.get("name"), 120)
        cat = f.get("category") if f.get("category") in CATEGORIES else "Others"
        unit = f.get("unit") if f.get("unit") in UNITS else "pc"
        price = parse_money(f.get("price")) if (f.get("price") or "").strip() else None
        cost = parse_money(f.get("cost")) if (f.get("cost") or "").strip() else None
        reorder = to_int(f.get("reorder_level")) or 0
        if not name:
            flash("Enter the product name.", "error")
        elif (f.get("price") or "").strip() and (price is None or price < 0) or (f.get("cost") or "").strip() and (cost is None or cost < 0):
            flash("Check the price and cost.", "error")
        elif conn.one("SELECT id FROM merch_products WHERE lower(name) = lower(?) AND id != ?", (name, pid or 0)):
            flash(f"{name} is already on the list.", "error")
        else:
            vals = {"name": name, "category": cat, "unit": unit, "price_cents": price, "cost_cents": cost, "reorder_level": max(0, reorder),
                    "rx_required": 1 if f.get("rx_required") else 0, "active": 1 if f.get("active") else 0}
            if pid:
                old = conn.one("SELECT * FROM merch_products WHERE id = ?", (pid,))
                if not old:
                    abort(404)
                conn.update("merch_products", pid, vals)
                audit.record("merch_product_edited", "merch_product", pid, f"Edited product {name}", audit.diff(dict(old), vals, vals.keys()))
                flash(f"{name} saved.", "success")
            else:
                pid = conn.insert("merch_products", {**vals, "sort_order": (conn.scalar("SELECT MAX(sort_order) FROM merch_products") or 0) + 1,
                                                     "created_at": now_str()})
                audit.record("merch_product_added", "merch_product", pid, f"Added product {name}")
                flash(f"{name} added.", "success")
        return redirect(url_for("merch.product_list", edit=None) + (f"#p{pid}" if pid else ""))
    edit = to_int(request.args.get("edit"))
    return render_template("staff/merch/products.html", prods=products(conn, active_only=False), categories=CATEGORIES, units=UNITS,
                           edit=edit)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@bp.route("/report")
@require("merch.view")
def report():
    conn = get_db()
    start, end = date_range_args(31)
    scope = _scope()
    args = [*scope, start.isoformat(), end.isoformat()]
    base = f"s.status = 'ok' AND s.branch_id IN ({_marks(scope)}) AND s.sold_on BETWEEN ? AND ?"
    sums = conn.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(subtotal_cents), 0) AS gross, COALESCE(SUM(discount_cents), 0) AS discount, "
                    f"COALESCE(SUM(total_cents), 0) AS net FROM merch_sales s WHERE {base}", args)
    by_product = conn.all(f"SELECT i.description AS name, p.category, SUM(i.qty) AS qty, SUM(i.amount_cents) AS amt, "
                          f"SUM(CASE WHEN i.unit_cost_cents IS NOT NULL THEN i.qty * i.unit_cost_cents END) AS cost, "
                          f"SUM(CASE WHEN i.unit_cost_cents IS NULL THEN 1 ELSE 0 END) AS no_cost "
                          f"FROM merch_sale_items i JOIN merch_sales s ON s.id = i.sale_id JOIN merch_products p ON p.id = i.product_id "
                          f"WHERE {base} GROUP BY i.product_id ORDER BY amt DESC", args)
    by_cat: dict[str, int] = {}
    for r in by_product:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + (r["amt"] or 0)
    by_branch = conn.all(f"SELECT b.name, COUNT(*) AS n, SUM(s.total_cents) AS net FROM merch_sales s JOIN branches b ON b.id = s.branch_id "
                         f"WHERE {base} GROUP BY b.name ORDER BY b.name", args)
    pays = conn.all(f"SELECT method, account, SUM(amount_cents) AS amt, COUNT(*) AS n FROM merch_payments WHERE status = 'valid' "
                    f"AND branch_id IN ({_marks(scope)}) AND substr(received_at, 1, 10) BETWEEN ? AND ? GROUP BY method, account ORDER BY amt DESC", args)
    cost = sum(r["cost"] or 0 for r in by_product)
    return render_template("staff/merch/report.html", start=start, end=end, sums=sums, by_product=by_product,
                           by_cat=sorted(by_cat.items(), key=lambda x: -x[1]), by_branch=by_branch,
                           pays=[{**dict(p), "label": pay_label(p["method"], p["account"])} for p in pays], collected=sum(p["amt"] for p in pays),
                           cost=cost, missing_cost=sum(1 for r in by_product if r["no_cost"]))

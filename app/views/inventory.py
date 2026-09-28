"""Consumables inventory: stock per location (each branch and the in-house Digital Solutions Dental Laboratory).

- inventory.view   : see stock, expiry and history for the locations you belong to.
- inventory.manage : update stock (count, receive, use/remove), and add or edit items and prices.
                     No role has it by default; only super admins until one grants it in Role access.

A location is visible to a user when they belong to its branch (user_branches) or its lab (user_labs).
Super admins see every location. Every quantity change is written to inventory_moves with who and when.
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..inventory_content import CATEGORIES, GROUP_OF, GROUPS
from ..util import clean, now_str, parse_date, parse_money, to_int, today

bp = Blueprint("inventory", __name__, url_prefix="/staff/inventory")

EXPIRY_WARN_DAYS = 90
STATUS = {  # key: (label, badge class, sort weight: most urgent first)
    "expired": ("Expired", "badge-red", 0),
    "out": ("Out of stock", "badge-red", 1),
    "expiring": ("Expiring soon", "badge-amber", 2),
    "reorder": ("Reorder", "badge-amber", 3),
    "ok": ("OK", "badge-green", 4),
    "none": ("Not counted", "", 5),
}
ATTENTION = ("expired", "out", "expiring", "reorder")
REMOVE_REASONS = {"used": "Used in clinic", "expired": "Expired / discarded", "damaged": "Damaged / defective",
                  "transfer_out": "Transferred to another location"}
MOVE_LABELS = {"count": "Stock count", "received": "Received", "adjust": "Count corrected", **REMOVE_REASONS}
MAX_QTY = 1_000_000


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def user_locations(conn=None):
    conn = conn or get_db()
    rows = conn.all("SELECT l.*, lab.name AS lab_name FROM inventory_locations l LEFT JOIN laboratories lab ON lab.id = l.laboratory_id "
                    "LEFT JOIN branches b ON b.id = l.branch_id WHERE l.active = 1 AND (l.branch_id IS NULL OR b.active = 1) "
                    "ORDER BY l.sort_order, l.id")
    if g.user.is_super_admin:
        return rows
    labs = {r["lab_id"] for r in conn.all("SELECT lab_id FROM user_labs WHERE user_id = ?", (g.user.id,))}
    return [r for r in rows if (r["branch_id"] and r["branch_id"] in g.user.branch_ids) or (r["laboratory_id"] and r["laboratory_id"] in labs)]


def _location(location_id):
    loc = next((x for x in user_locations() if x["id"] == location_id), None)
    if not loc:
        abort(404)
    return loc


def _item(conn, item_id):
    it = conn.one("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
    if not it:
        abort(404)
    return it


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_qty(value):
    """'12', '2.5', '1,000' -> float; blank -> None; invalid or negative -> raises ValueError."""
    value = (value or "").strip().replace(",", "")
    if value == "":
        return None
    q = float(value)
    if q < 0 or q > MAX_QTY or q != q:
        raise ValueError
    return round(q, 2)


def fmt_qty(q):
    if q is None:
        return ""
    return f"{q:,.2f}".rstrip("0").rstrip(".")


def status_of(row, on=None):
    on = on or today()
    if row["qty"] is None:
        return "none"
    exp = parse_date(row["expiry_date"]) if row["expiry_date"] else None
    if exp and exp < on and row["qty"] > 0:
        return "expired"
    if row["qty"] <= 0:
        return "out"
    if exp and exp <= on + timedelta(days=EXPIRY_WARN_DAYS):
        return "expiring"
    if row["reorder_level"] is not None and row["qty"] <= row["reorder_level"]:
        return "reorder"
    return "ok"


def stock_rows(conn, location_id):
    rows = conn.all("SELECT i.*, s.qty, s.reorder_level, s.expiry_date, s.last_counted_at, s.updated_at AS stock_updated_at "
                    "FROM inventory_items i LEFT JOIN inventory_stock s ON s.item_id = i.id AND s.location_id = ? "
                    "WHERE i.active = 1", (location_id,))
    out = []
    on = today()
    for r in rows:
        r = dict(r)
        r["status"] = status_of(r, on)
        r["value_cents"] = round(r["qty"] * r["unit_price_cents"]) if r["qty"] and r["unit_price_cents"] is not None else None
        r["group"] = GROUP_OF.get(r["category"], "Other Supplies")
        out.append(r)
    cat_index = {c: i for i, c in enumerate(CATEGORIES)}
    out.sort(key=lambda r: (cat_index.get(r["category"], 999), r["name"].lower()))
    return out


def summarize(rows):
    s = {"in_stock": 0, "value_cents": 0, "counted": 0, **{k: 0 for k in STATUS}}
    for r in rows:
        s[r["status"]] += 1
        if r["qty"] is not None:
            s["counted"] += 1
        if r["qty"] and r["qty"] > 0:
            s["in_stock"] += 1
        s["value_cents"] += r["value_cents"] or 0
    s["attention"] = sum(s[k] for k in ATTENTION)
    return s


def _apply(conn, loc, item, *, qty=None, change=None, kind, reorder=..., expiry=..., note="", counted=False):
    """Set (qty) or change (change) the stock of one item at one location and log it. Call inside a transaction."""
    cur = conn.one("SELECT * FROM inventory_stock WHERE location_id = ? AND item_id = ?", (loc["id"], item["id"]))
    before = cur["qty"] if cur else 0.0
    after = before if qty is None and change is None else (qty if qty is not None else round(before + change, 2))
    if after < 0:
        raise ValueError("negative")
    vals = {"qty": after, "updated_by": g.user.id, "updated_at": now_str()}
    if reorder is not ...:
        vals["reorder_level"] = reorder
    if expiry is not ...:
        vals["expiry_date"] = expiry
    if counted:
        vals["last_counted_at"] = now_str()
    if cur:
        sets = ", ".join(f"{k} = ?" for k in vals)
        conn.execute(f"UPDATE inventory_stock SET {sets} WHERE location_id = ? AND item_id = ?", [*vals.values(), loc["id"], item["id"]])
    else:
        row = {"location_id": loc["id"], "item_id": item["id"], "reorder_level": None, "expiry_date": None, **vals}
        conn.execute(f"INSERT INTO inventory_stock ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    if after != before or (cur is None and qty is not None):
        conn.insert("inventory_moves", {"location_id": loc["id"], "item_id": item["id"], "kind": kind, "qty_change": round(after - before, 2),
                                        "qty_after": after, "expiry_date": vals.get("expiry_date") if expiry is not ... else None,
                                        "note": note, "user_id": g.user.id, "at": now_str()})
    return before, after


def _csv_cell(v):
    v = "" if v is None else v
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("")
@require("inventory.view")
def index():
    conn = get_db()
    locs = user_locations(conn)
    if not locs:
        return render_template("staff/inventory/none.html")
    if len(locs) == 1:
        return redirect(url_for("inventory.location", location_id=locs[0]["id"]))
    cards = []
    attention = []
    for loc in locs:
        rows = stock_rows(conn, loc["id"])
        cards.append((loc, summarize(rows)))
        for r in rows:
            if r["status"] in ATTENTION:
                attention.append((loc, r))
    attention.sort(key=lambda x: (STATUS[x[1]["status"]][2], x[1]["expiry_date"] or "9999", x[1]["name"].lower()))
    return render_template("staff/inventory/overview.html", cards=cards, attention=attention[:300], more=max(0, len(attention) - 300),
                           statuses=STATUS, fmt_qty=fmt_qty, warn_days=EXPIRY_WARN_DAYS)


@bp.route("/<int:location_id>", methods=["GET", "POST"])
@require("inventory.view")
def location(location_id):
    conn = get_db()
    loc = _location(location_id)
    can_edit = g.user.can("inventory.manage")
    category = request.values.get("category", "")
    category = category if category in CATEGORIES else ""
    status = request.values.get("status", "")
    q = clean(request.values.get("q"), 80).lower()
    editing = can_edit and request.values.get("edit") == "1" and bool(category)

    if request.method == "POST":
        if not can_edit:
            abort(403)
        if not category:
            abort(400)
        rows = [r for r in stock_rows(conn, loc["id"]) if r["category"] == category]
        errors, changed = {}, []
        for r in rows:
            f = request.form
            key = str(r["id"])
            if f"qty_{key}" not in f:
                continue
            try:
                new_qty = parse_qty(f.get(f"qty_{key}"))
                new_reorder = parse_qty(f.get(f"reorder_{key}"))
            except ValueError:
                errors[r["id"]] = "Enter a number of 0 or more."
                continue
            exp_raw = clean(f.get(f"expiry_{key}"), 10)
            new_exp = parse_date(exp_raw) if exp_raw else None
            if exp_raw and not new_exp:
                errors[r["id"]] = "Enter the expiry date as YYYY-MM-DD."
                continue
            new_exp = new_exp.isoformat() if new_exp else None
            if r["qty"] is None and new_qty is None and (new_reorder is not None or new_exp):
                errors[r["id"]] = "Enter the quantity on hand too."
                continue
            qty_changed = new_qty is not None and new_qty != r["qty"]
            other_changed = (r["qty"] is not None or new_reorder is not None or new_exp is not None) and \
                (new_reorder != r["reorder_level"] or new_exp != r["expiry_date"])
            if qty_changed or other_changed:
                changed.append((r, new_qty, new_reorder, new_exp, qty_changed))
        if errors:
            flash(f"Nothing was saved: {len(errors)} row(s) need fixing (highlighted).", "error")
            return render_template("staff/inventory/location.html", **_location_ctx(conn, loc, category, status, q, True, errors, request.form))
        with conn.transaction():
            for r, new_qty, new_reorder, new_exp, qty_changed in changed:
                _apply(conn, loc, r, qty=new_qty if qty_changed else None, kind="count", reorder=new_reorder, expiry=new_exp,
                       counted=qty_changed)
            if changed:
                audit.record("inventory_counted", "inventory_location", loc["id"],
                             f"Updated {len(changed)} item(s) in {category} at {loc['name']}", branch_id=loc["branch_id"])
        flash(f"Saved {len(changed)} change(s)." if changed else "No changes to save.", "success")
        return redirect(url_for("inventory.location", location_id=loc["id"], category=category, status=status, q=q))

    return render_template("staff/inventory/location.html", **_location_ctx(conn, loc, category, status, q, editing, {}, None))


def _location_ctx(conn, loc, category, status, q, editing, errors, form):
    rows = stock_rows(conn, loc["id"])
    summary = summarize(rows)
    shown = rows
    if category:
        shown = [r for r in shown if r["category"] == category]
    if q:
        shown = [r for r in shown if q in r["name"].lower() or q in r["code"].lower() or q in (r["supplier"] or "").lower()]
    if status == "attention":
        shown = [r for r in shown if r["status"] in ATTENTION]
    elif status in STATUS:
        shown = [r for r in shown if r["status"] == status]
    counts = {c: 0 for c in CATEGORIES}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return dict(loc=loc, locs=user_locations(conn), rows=shown, summary=summary, category=category, status=status, q=q,
                editing=editing, errors=errors, form=form, groups=GROUPS, counts=counts, statuses=STATUS, fmt_qty=fmt_qty,
                can_edit=g.user.can("inventory.manage"), warn_days=EXPIRY_WARN_DAYS)


@bp.route("/<int:location_id>/item/<int:item_id>", methods=["GET", "POST"])
@require("inventory.view")
def item(location_id, item_id):
    conn = get_db()
    loc = _location(location_id)
    it = _item(conn, item_id)
    errors = {}
    if request.method == "POST":
        if not g.user.can("inventory.manage"):
            abort(403)
        action = request.form.get("action")
        note = clean(request.form.get("note"), 300)
        try:
            qty = parse_qty(request.form.get("qty"))
        except ValueError:
            qty = -1
        cur = conn.one("SELECT * FROM inventory_stock WHERE location_id = ? AND item_id = ?", (loc["id"], it["id"]))
        have = cur["qty"] if cur else 0.0
        if action == "receive":
            exp_raw = clean(request.form.get("expiry"), 10)
            exp = parse_date(exp_raw) if exp_raw else None
            if qty is None or qty <= 0:
                errors["receive"] = "Enter how many you received (more than 0)."
            elif exp_raw and not exp:
                errors["receive"] = "Enter the expiry date as YYYY-MM-DD."
            else:
                # Keep the earliest expiry on hand: a new batch only sets it when there was no dated stock left.
                new_exp = cur["expiry_date"] if cur else None
                if exp and (have <= 0 or not new_exp or exp.isoformat() < new_exp):
                    new_exp = exp.isoformat()
                with conn.transaction():
                    _apply(conn, loc, it, change=qty, kind="received", expiry=new_exp, note=note)
                    audit.record("inventory_received", "inventory_item", it["id"], f"Received {fmt_qty(qty)} {it['unit']} of {it['name']} at {loc['name']}",
                                 branch_id=loc["branch_id"])
                flash(f"Added {fmt_qty(qty)} {it['unit']}.", "success")
                return redirect(url_for("inventory.item", location_id=loc["id"], item_id=it["id"]))
        elif action == "remove":
            reason = request.form.get("reason")
            if reason not in REMOVE_REASONS:
                errors["remove"] = "Choose a reason."
            elif qty is None or qty <= 0:
                errors["remove"] = "Enter how many to remove (more than 0)."
            elif qty > have:
                errors["remove"] = f"Only {fmt_qty(have)} {it['unit']} on hand. Correct the count first if that's wrong."
            else:
                with conn.transaction():
                    _apply(conn, loc, it, change=-qty, kind=reason, note=note)
                    audit.record("inventory_removed", "inventory_item", it["id"],
                                 f"{REMOVE_REASONS[reason]}: {fmt_qty(qty)} {it['unit']} of {it['name']} at {loc['name']}", branch_id=loc["branch_id"])
                flash(f"Removed {fmt_qty(qty)} {it['unit']}.", "success")
                return redirect(url_for("inventory.item", location_id=loc["id"], item_id=it["id"]))
        elif action == "settings":
            try:
                reorder = parse_qty(request.form.get("reorder"))
            except ValueError:
                reorder = -1
            exp_raw = clean(request.form.get("expiry"), 10)
            exp = parse_date(exp_raw) if exp_raw else None
            if reorder == -1:
                errors["settings"] = "Enter a reorder level of 0 or more, or leave it blank."
            elif exp_raw and not exp:
                errors["settings"] = "Enter the expiry date as YYYY-MM-DD."
            elif qty == -1:
                errors["settings"] = "Enter the quantity on hand as a number of 0 or more."
            elif qty is None and not cur:
                errors["settings"] = "Enter the quantity on hand."
            else:
                with conn.transaction():
                    _apply(conn, loc, it, qty=qty, kind="adjust" if cur else "count", reorder=reorder,
                           expiry=exp.isoformat() if exp else None, note=note, counted=qty is not None and qty != have)
                    audit.record("inventory_adjusted", "inventory_item", it["id"], f"Updated stock details of {it['name']} at {loc['name']}",
                                 branch_id=loc["branch_id"])
                flash("Saved.", "success")
                return redirect(url_for("inventory.item", location_id=loc["id"], item_id=it["id"]))
        else:
            abort(400)
    stock = conn.one("SELECT * FROM inventory_stock WHERE location_id = ? AND item_id = ?", (loc["id"], it["id"]))
    row = dict(it, qty=stock["qty"] if stock else None, reorder_level=stock["reorder_level"] if stock else None,
               expiry_date=stock["expiry_date"] if stock else None)
    moves = conn.all("SELECT m.*, u.name AS user_name FROM inventory_moves m LEFT JOIN users u ON u.id = m.user_id "
                     "WHERE m.location_id = ? AND m.item_id = ? ORDER BY m.id DESC LIMIT 200", (loc["id"], it["id"]))
    others = []
    for other in user_locations(conn):
        if other["id"] != loc["id"]:
            s = conn.one("SELECT qty, expiry_date, reorder_level FROM inventory_stock WHERE location_id = ? AND item_id = ?", (other["id"], it["id"]))
            others.append((other, s))
    return render_template("staff/inventory/item.html", loc=loc, it=it, stock=stock, status=status_of(row), statuses=STATUS, moves=moves,
                           others=others, fmt_qty=fmt_qty, errors=errors, form=request.form, reasons=REMOVE_REASONS, move_labels=MOVE_LABELS,
                           can_edit=g.user.can("inventory.manage"), group=GROUP_OF.get(it["category"], ""))


@bp.route("/<int:location_id>/export.csv")
@require("inventory.view")
def export(location_id):
    conn = get_db()
    loc = _location(location_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Code", "Group", "Category", "Item", "Unit", "Qty on hand", "Reorder level", "Expiry date", "Unit price (PHP)",
                "Stock value (PHP)", "Status", "Supplier", "Last counted"])
    for r in stock_rows(conn, loc["id"]):
        w.writerow([_csv_cell(x) for x in (r["code"], r["group"], r["category"], r["name"], r["unit"], fmt_qty(r["qty"]),
                                            fmt_qty(r["reorder_level"]), r["expiry_date"] or "",
                                            "" if r["unit_price_cents"] is None else r["unit_price_cents"] / 100,
                                            "" if r["value_cents"] is None else r["value_cents"] / 100, STATUS[r["status"]][0],
                                            r["supplier"], (r["last_counted_at"] or "")[:10])])
    audit.record("inventory_exported", "inventory_location", loc["id"], f"Exported inventory of {loc['name']}", branch_id=loc["branch_id"])
    name = "".join(ch if ch.isalnum() else "-" for ch in loc["name"].lower()).strip("-")
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="inventory-{name}-{today().isoformat()}.csv"', "Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Item list (catalog): shared by every location
# ---------------------------------------------------------------------------

@bp.route("/items", methods=["GET", "POST"])
@require("inventory.manage")
def items():
    conn = get_db()
    category = request.values.get("category", "")
    category = category if category in CATEGORIES else ""
    q = clean(request.values.get("q"), 80).lower()
    show = request.values.get("show", "active")
    v = {"name": "", "unit": "", "category": category or CATEGORIES[0], "price": "", "supplier": ""}
    errors = {}
    if request.method == "POST":
        v = {"name": clean(request.form.get("name"), 120), "unit": clean(request.form.get("unit"), 30),
             "category": request.form.get("category", ""), "price": clean(request.form.get("price"), 20),
             "supplier": clean(request.form.get("supplier"), 120)}
        errors = _validate_item(conn, v)
        if not errors:
            with conn.transaction():
                n = (conn.scalar("SELECT MAX(CAST(SUBSTR(code, 4) AS INTEGER)) FROM inventory_items WHERE code LIKE 'DH-%'") or 0) + 1
                iid = conn.insert("inventory_items", {"code": f"DH-{n:04d}", "name": v["name"], "unit": v["unit"], "category": v["category"],
                                                      "unit_price_cents": parse_money(v["price"]) if v["price"] else None, "supplier": v["supplier"],
                                                      "sort_order": CATEGORIES.index(v["category"]) * 1000 + 999, "active": 1,
                                                      "created_at": now_str(), "updated_at": now_str()})
                audit.record("inventory_item_added", "inventory_item", iid, f"Added inventory item: {v['name']}")
            flash(f"Added {v['name']}.", "success")
            return redirect(url_for("inventory.items", category=v["category"]))
    where, args = ["1 = 1"], []
    if show != "all":
        where.append("active = 1")
    if category:
        where.append("category = ?")
        args.append(category)
    if q:
        where.append("(LOWER(name) LIKE ? OR LOWER(code) LIKE ? OR LOWER(supplier) LIKE ?)")
        args += [f"%{q}%"] * 3
    rows = conn.all(f"SELECT * FROM inventory_items WHERE {' AND '.join(where)}", args)
    cat_index = {c: i for i, c in enumerate(CATEGORIES)}
    rows = sorted(rows, key=lambda r: (cat_index.get(r["category"], 999), r["name"].lower()))
    no_price = conn.scalar("SELECT COUNT(*) FROM inventory_items WHERE active = 1 AND unit_price_cents IS NULL")
    return render_template("staff/inventory/items.html", rows=rows, groups=GROUPS, category=category, q=q, show=show, v=v, errors=errors,
                           no_price=no_price)


def _validate_item(conn, v, item_id=None):
    errors = {}
    if len(v["name"]) < 2:
        errors["name"] = "Enter the item name."
    elif conn.one("SELECT id FROM inventory_items WHERE LOWER(name) = LOWER(?) AND id != ?", (v["name"], item_id or 0)):
        errors["name"] = "An item with this name already exists."
    if not v["unit"]:
        errors["unit"] = "Enter the unit (e.g. box, pack, piece)."
    if v["category"] not in CATEGORIES:
        errors["category"] = "Choose a category."
    if v["price"]:
        p = parse_money(v["price"])
        if p is None or p < 0:
            errors["price"] = "Enter a price like 250 or 1,250.50."
    return errors


@bp.route("/items/<int:item_id>", methods=["GET", "POST"])
@require("inventory.manage")
def item_edit(item_id):
    conn = get_db()
    it = _item(conn, item_id)
    v = {"name": it["name"], "unit": it["unit"], "category": it["category"],
         "price": "" if it["unit_price_cents"] is None else f"{it['unit_price_cents'] / 100:.2f}", "supplier": it["supplier"],
         "notes": it["notes"], "active": it["active"]}
    errors = {}
    if request.method == "POST":
        v = {"name": clean(request.form.get("name"), 120), "unit": clean(request.form.get("unit"), 30),
             "category": request.form.get("category", ""), "price": clean(request.form.get("price"), 20),
             "supplier": clean(request.form.get("supplier"), 120), "notes": clean(request.form.get("notes"), 500),
             "active": 1 if request.form.get("active") else 0}
        errors = _validate_item(conn, v, it["id"])
        if not errors:
            new_price = parse_money(v["price"]) if v["price"] else None
            conn.update("inventory_items", it["id"], {"name": v["name"], "unit": v["unit"], "category": v["category"], "unit_price_cents": new_price,
                                                      "supplier": v["supplier"], "notes": v["notes"], "active": v["active"], "updated_at": now_str()})
            changes = [k for k, old, new in (("name", it["name"], v["name"]), ("unit", it["unit"], v["unit"]), ("category", it["category"], v["category"]),
                                              ("price", it["unit_price_cents"], new_price), ("supplier", it["supplier"], v["supplier"]),
                                              ("active", it["active"], v["active"])) if old != new]
            audit.record("inventory_item_updated", "inventory_item", it["id"], f"Updated inventory item {it['code']}: {', '.join(changes) or 'notes'}",
                         {"price_before": it["unit_price_cents"], "price_after": new_price} if "price" in changes else None)
            flash("Item saved.", "success")
            return redirect(url_for("inventory.items", category=v["category"]))
    return render_template("staff/inventory/item_edit.html", it=it, v=v, errors=errors, groups=GROUPS)

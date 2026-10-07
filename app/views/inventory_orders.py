"""Monthly order lists per branch (inventory location).

Before month end, staff with "Make the monthly order list" (inventory.order) make next month's list for their branch.
The list starts with the items that are low or out of stock there; they adjust quantities and add items (from the
item list, or typed in when it isn't listed). Then:

  draft --submit--> submitted --approve--> approved --ordered--> ordered --received--> received
                    (returned to draft with a note)                     (adds the received quantities to stock)

Approving, marking ordered and receiving need "Approve order lists" (inventory.order_approve) or super admin.
A reminder goes to the branch's order makers a few days before month end while next month's list isn't submitted.
"""
from __future__ import annotations

import calendar
import math
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, settings
from ..auth import login_required
from ..db import get_db
from ..notices import notify
from ..util import clean, now_str, parse_money, peso, to_int, today
from .inventory import _apply, fmt_qty, parse_qty, stock_rows, user_locations

bp = Blueprint("inv_orders", __name__, url_prefix="/staff/inventory/orders")

STATUSES = {"draft": ("Draft", ""), "submitted": ("Submitted, waiting for approval", "badge-amber"), "approved": ("Approved", "badge-blue"),
            "ordered": ("Ordered from supplier", "badge-blue"), "received": ("Received", "badge-green"), "cancelled": ("Cancelled", "badge-red")}
OPEN = ("draft", "submitted", "approved", "ordered")


def can_make():
    return g.user.is_super_admin or g.user.can("inventory.order")


def can_approve():
    return g.user.is_super_admin or g.user.can("inventory.order_approve")


def _guard():
    if not (can_make() or can_approve()):
        abort(403)


def month_label(m: str) -> str:
    y, mo = (int(x) for x in m.split("-"))
    return f"{calendar.month_name[mo]} {y}"


def next_month(d: date | None = None) -> str:
    d = d or today()
    return f"{d.year + (d.month == 12)}-{(d.month % 12) + 1:02d}"


def month_end(d: date | None = None) -> date:
    d = d or today()
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def suggested_lines(conn, location_id: int) -> list[dict]:
    """Low or out-of-stock items at this location, with a suggested quantity (back up to twice the reorder level)."""
    out = []
    for r in stock_rows(conn, location_id):
        if r["status"] not in ("out", "reorder"):
            continue
        level = r["reorder_level"]
        qty = math.ceil(max(1, (level * 2 if level else 1) - max(r["qty"] or 0, 0)))
        out.append({"item_id": r["id"], "name": r["name"], "unit": r["unit"], "qty": qty, "unit_price_cents": r["unit_price_cents"],
                    "note": f"In stock: {fmt_qty(r['qty'] or 0)}" + (f", reorder at {fmt_qty(level)}" if level is not None else "")})
    return out


def _order(conn, order_id):
    o = conn.one("SELECT o.*, l.name AS location, l.branch_id, u.name AS created_by_name, a.name AS approved_by_name FROM inventory_orders o "
                 "JOIN inventory_locations l ON l.id = o.location_id LEFT JOIN users u ON u.id = o.created_by "
                 "LEFT JOIN users a ON a.id = o.approved_by WHERE o.id = ?", (order_id,))
    if not o or o["location_id"] not in {x["id"] for x in user_locations(conn)}:
        abort(404)
    return o


def _lines(conn, order_id):
    return conn.all("SELECT * FROM inventory_order_lines WHERE order_id = ? ORDER BY sort_order, id", (order_id,))


def _approvers(conn, branch_id) -> list[int]:
    from ..permissions import load_user_permissions
    out = []
    for u in conn.all("SELECT id, role, access_role FROM users WHERE active = 1"):
        if u["role"] == "super_admin":
            out.append(u["id"])
        elif "inventory.order_approve" in load_user_permissions(conn, u["id"], u["access_role"] or u["role"]) and (
                branch_id is None or conn.one("SELECT 1 AS x FROM user_branches WHERE user_id = ? AND branch_id = ?", (u["id"], branch_id))):
            out.append(u["id"])
    return out


def _makers(conn, branch_id) -> list[int]:
    from ..permissions import load_user_permissions
    out = []
    for u in conn.all("SELECT u.id, u.role, u.access_role FROM users u JOIN user_branches ub ON ub.user_id = u.id "
                      "WHERE u.active = 1 AND ub.branch_id = ? AND u.role != 'super_admin'", (branch_id,)):
        if "inventory.order" in load_user_permissions(conn, u["id"], u["access_role"] or u["role"]):
            out.append(u["id"])
    return out


@bp.route("", methods=["GET", "POST"])
@login_required
def index():
    _guard()
    conn = get_db()
    locs = user_locations(conn)
    if request.method == "POST":
        if not can_make():
            abort(403)
        loc = next((x for x in locs if x["id"] == to_int(request.form.get("location_id"))), None)
        month = request.form.get("for_month") or next_month()
        try:
            y, m = (int(x) for x in month.split("-"))
            month = f"{y}-{m:02d}"
            assert 1 <= m <= 12 and 2020 <= y <= 2100
        except (ValueError, AssertionError):
            month = None
        if not loc or not month:
            flash("Choose the branch and the month.", "error")
            return redirect(url_for("inv_orders.index"))
        existing = conn.one("SELECT id FROM inventory_orders WHERE location_id = ? AND for_month = ? AND status != 'cancelled'", (loc["id"], month))
        if existing:
            flash(f"{loc['name']} already has an order list for {month_label(month)}.", "info")
            return redirect(url_for("inv_orders.order", order_id=existing["id"]))
        with conn.transaction():
            oid = conn.insert("inventory_orders", {"location_id": loc["id"], "for_month": month, "status": "draft", "created_by": g.user.id,
                                                   "created_at": now_str(), "updated_at": now_str()})
            sug = suggested_lines(conn, loc["id"])
            for i, ln in enumerate(sug):
                conn.insert("inventory_order_lines", {**ln, "order_id": oid, "sort_order": i})
            audit.record("inventory_order_created", "inventory_order", oid, f"Order list {loc['name']} {month}", branch_id=loc["branch_id"])
        flash(f"Order list started with {len(sug)} low or out-of-stock item{'s' if len(sug) != 1 else ''}. Check the quantities and add what else is needed."
              if sug else "Order list started. Add the items you need.", "success")
        return redirect(url_for("inv_orders.order", order_id=oid))
    ids = [x["id"] for x in locs] or [0]
    status = request.args.get("status", "open")
    where, args = [f"o.location_id IN ({','.join('?' for _ in ids)})"], list(ids)
    if status == "open":
        where.append("o.status IN ('draft','submitted','approved','ordered')")
    elif status in STATUSES:
        where.append("o.status = ?")
        args.append(status)
    rows = conn.all("SELECT o.*, l.name AS location, u.name AS created_by_name, (SELECT COUNT(*) FROM inventory_order_lines x WHERE x.order_id = o.id) AS n_lines, "
                    "(SELECT COALESCE(SUM(ROUND(COALESCE(x.approved_qty, x.qty) * x.unit_price_cents)), 0) FROM inventory_order_lines x WHERE x.order_id = o.id) AS est "
                    "FROM inventory_orders o JOIN inventory_locations l ON l.id = o.location_id LEFT JOIN users u ON u.id = o.created_by "
                    f"WHERE {' AND '.join(where)} ORDER BY o.for_month DESC, l.sort_order, o.id DESC LIMIT 300", args)
    nm = next_month()
    missing = [x for x in locs if x["branch_id"] and not conn.one(
        "SELECT 1 AS x FROM inventory_orders WHERE location_id = ? AND for_month = ? AND status != 'cancelled'", (x["id"], nm))]
    return render_template("staff/inventory/orders.html", rows=rows, locs=locs, status=status, statuses=STATUSES, next_month=nm,
                           month_label=month_label, missing=missing, due=month_end(), can_make=can_make(), can_approve=can_approve())


@bp.route("/<int:order_id>", methods=["GET", "POST"])
@login_required
def order(order_id):
    _guard()
    conn = get_db()
    o = _order(conn, order_id)
    lines = _lines(conn, order_id)
    editable = o["status"] == "draft" and can_make() or o["status"] in ("draft", "submitted") and can_approve()
    if request.method == "POST":
        f = request.form
        action = f.get("action", "save")
        back = redirect(url_for("inv_orders.order", order_id=order_id))
        if action in ("save", "add", "remove", "submit") and not editable:
            abort(403)
        if action in ("approve", "return", "ordered", "receive") and not can_approve():
            abort(403)
        allowed_from = {"submit": ("draft",), "approve": ("submitted",), "return": ("submitted",), "ordered": ("approved",),
                        "receive": ("approved", "ordered"), "cancel": ("draft", "submitted", "approved")}
        if action in allowed_from and o["status"] not in allowed_from[action]:
            flash("This order list has already moved on. Refresh the page.", "error")
            return back
        with conn.transaction():
            if action in ("save", "submit", "approve"):
                for ln in lines:
                    if action == "approve":
                        q = parse_qty(f.get(f"approved_{ln['id']}"))
                        conn.execute("UPDATE inventory_order_lines SET approved_qty = ? WHERE id = ?", (q if q is not None else ln["qty"], ln["id"]))
                    else:
                        q = parse_qty(f.get(f"qty_{ln['id']}"))
                        if q is not None and q > 0:
                            price = parse_money(f.get(f"price_{ln['id']}")) if f.get(f"price_{ln['id']}") else ln["unit_price_cents"]
                            conn.execute("UPDATE inventory_order_lines SET qty = ?, note = ?, unit_price_cents = ? WHERE id = ?",
                                         (q, clean(f.get(f"note_{ln['id']}"), 200), price, ln["id"]))
                if action != "approve":
                    conn.execute("UPDATE inventory_orders SET notes = ?, updated_at = ? WHERE id = ?", (clean(f.get("notes"), 1000), now_str(), order_id))
            if action == "add":
                name = clean(f.get("item"), 160)
                q = parse_qty(f.get("qty"))
                if not name or not q or q <= 0:
                    flash("Type the item and a quantity.", "error")
                    return back
                it = conn.one("SELECT * FROM inventory_items WHERE active = 1 AND lower(name) = lower(?)", (name,))
                dup = it and conn.one("SELECT id FROM inventory_order_lines WHERE order_id = ? AND item_id = ?", (order_id, it["id"]))
                if dup:
                    conn.execute("UPDATE inventory_order_lines SET qty = qty + ? WHERE id = ?", (q, dup["id"]))
                else:
                    conn.insert("inventory_order_lines", {"order_id": order_id, "item_id": it["id"] if it else None, "name": it["name"] if it else name,
                                                          "unit": it["unit"] if it else clean(f.get("unit"), 30), "qty": q,
                                                          "unit_price_cents": it["unit_price_cents"] if it else parse_money(f.get("price") or ""),
                                                          "note": clean(f.get("note"), 200), "sort_order": len(lines)})
                flash("Item added." if it or dup else "Item added (not in the item list: typed as written).", "success")
            elif action == "remove":
                conn.execute("DELETE FROM inventory_order_lines WHERE id = ? AND order_id = ?", (to_int(f.get("line_id")), order_id))
            elif action == "submit":
                if not _lines(conn, order_id):
                    flash("Add at least one item before submitting.", "error")
                    return back
                conn.execute("UPDATE inventory_orders SET status = 'submitted', submitted_by = ?, submitted_at = ?, review_note = '' WHERE id = ?",
                             (g.user.id, now_str(), order_id))
                notify(conn, _approvers(conn, o["branch_id"]), "inventory_order", f"Order list to approve: {o['location']}",
                       f"{month_label(o['for_month'])} · {len(_lines(conn, order_id))} items", f"/staff/inventory/orders/{order_id}", exclude=g.user.id)
                flash("Submitted for approval.", "success")
            elif action == "return":
                conn.execute("UPDATE inventory_orders SET status = 'draft', review_note = ?, updated_at = ? WHERE id = ?",
                             (clean(f.get("review_note"), 500), now_str(), order_id))
                notify(conn, [o["created_by"], o["submitted_by"]], "inventory_order", f"Order list returned: {o['location']}",
                       clean(f.get("review_note"), 200) or "Please check and submit again.", f"/staff/inventory/orders/{order_id}", exclude=g.user.id)
                flash("Returned to the branch for changes.", "success")
            elif action == "approve":
                conn.execute("UPDATE inventory_orders SET status = 'approved', approved_by = ?, approved_at = ?, review_note = ? WHERE id = ?",
                             (g.user.id, now_str(), clean(f.get("review_note"), 500), order_id))
                notify(conn, [o["created_by"], o["submitted_by"]], "inventory_order", f"Order list approved: {o['location']}",
                       month_label(o["for_month"]), f"/staff/inventory/orders/{order_id}", exclude=g.user.id)
                flash("Approved.", "success")
            elif action == "ordered":
                conn.execute("UPDATE inventory_orders SET status = 'ordered', ordered_at = ? WHERE id = ?", (now_str(), order_id))
                flash("Marked as ordered from the supplier.", "success")
            elif action == "receive":
                loc = conn.one("SELECT * FROM inventory_locations WHERE id = ?", (o["location_id"],))
                added = 0
                for ln in lines:
                    q = parse_qty(f.get(f"received_{ln['id']}"))
                    q = q if q is not None else 0
                    conn.execute("UPDATE inventory_order_lines SET received_qty = ? WHERE id = ?", (q, ln["id"]))
                    if q > 0 and ln["item_id"]:
                        item = conn.one("SELECT * FROM inventory_items WHERE id = ?", (ln["item_id"],))
                        _apply(conn, loc, item, change=q, kind="received", note=f"Order list #{order_id} ({month_label(o['for_month'])})")
                        added += 1
                conn.execute("UPDATE inventory_orders SET status = 'received', received_by = ?, received_at = ? WHERE id = ?",
                             (g.user.id, now_str(), order_id))
                flash(f"Received. {added} item{'s' if added != 1 else ''} added to {loc['name']} stock."
                      + (" Items typed in (not in the item list) aren't added to stock." if any(not ln["item_id"] for ln in lines) else ""), "success")
            elif action == "cancel":
                if not (can_approve() or (o["status"] in ("draft", "submitted") and o["created_by"] == g.user.id)):
                    abort(403)
                conn.execute("UPDATE inventory_orders SET status = 'cancelled', updated_at = ? WHERE id = ?", (now_str(), order_id))
                flash("Order list cancelled.", "success")
            elif action == "save":
                flash("Saved.", "success")
            if action not in ("save", "add", "remove"):
                audit.record(f"inventory_order_{action}", "inventory_order", order_id, f"Order list {o['location']} {o['for_month']}: {action}",
                             branch_id=o["branch_id"])
        return back
    from ..inventory_content import CATEGORIES  # noqa: F401  (item picker groups by category in the template)
    items = conn.all("SELECT name, unit FROM inventory_items WHERE active = 1 ORDER BY name")
    total = sum(round((ln["approved_qty"] if ln["approved_qty"] is not None else ln["qty"]) * ln["unit_price_cents"])
                for ln in lines if ln["unit_price_cents"] is not None)
    return render_template("staff/inventory/order.html", o=o, lines=lines, items=items, statuses=STATUSES, month_label=month_label,
                           editable=editable, can_approve=can_approve(), can_make=can_make(), total=total, fmt_qty=fmt_qty, peso=peso)


@bp.route("/<int:order_id>/print")
@login_required
def order_print(order_id):
    _guard()
    conn = get_db()
    o = _order(conn, order_id)
    return render_template("staff/inventory/order_print.html", o=o, lines=_lines(conn, order_id), statuses=STATUSES, month_label=month_label,
                           fmt_qty=fmt_qty)


def run_reminders(conn) -> int:
    """Daily: a few days before month end, remind each branch's order makers if next month's list isn't submitted yet."""
    days = int(settings.get("inventory.order_reminder_days", conn) or 0)
    if days <= 0:
        return 0
    t = today()
    if t < month_end(t) - timedelta(days=days - 1):
        return 0
    nm = next_month(t)
    sent = 0
    for loc in conn.all("SELECT * FROM inventory_locations WHERE active = 1 AND branch_id IS NOT NULL"):
        key = f"inventory.order_reminded.{loc['id']}.{nm}"
        if settings.get(key, conn):
            continue
        done = conn.one("SELECT 1 AS x FROM inventory_orders WHERE location_id = ? AND for_month = ? AND status NOT IN ('draft','cancelled')",
                        (loc["id"], nm))
        if done:
            continue
        users = _makers(conn, loc["branch_id"])
        if users:
            notify(conn, users, "inventory_order_due", f"Order list for {month_label(nm)} due by {month_end(t).strftime('%b')} {month_end(t).day}",
                   f"{loc['name']}: make and submit next month's order list.", "/staff/inventory/orders")
            sent += 1
        settings.put(key, True, None, conn)
    return sent

"""Fee schedule (billing price list), grouped by category. Used by the progress note and bill line pickers.

Editing needs "Edit the fee schedule" (super admin by default). Everyone who bills can see the prices in the pickers.
"""
from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..fee_schedule import classify
from ..fee_schedule_data import CATEGORIES
from ..sheets import SheetError, read_table
from ..util import clean, now_str, parse_money, peso, to_int

bp = Blueprint("fees", __name__, url_prefix="/staff/admin/fees")


def active_fees(conn):
    """For the pickers: active items, grouped order (category, then list order)."""
    order = {c: i for i, c in enumerate(CATEGORIES)}
    rows = conn.all("SELECT * FROM fee_schedule WHERE active = 1")
    return sorted(rows, key=lambda r: (order.get(r["category"], 99), r["sort_order"], r["name"]))


@bp.route("/", methods=["GET", "POST"])
@require("fees.manage")
def index():
    conn = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            fid = to_int(request.form.get("id"))
            row = conn.one("SELECT * FROM fee_schedule WHERE id = ?", (fid,))
            price = parse_money(request.form.get("price"))
            name = clean(request.form.get("name"), 200)
            cat = request.form.get("category")
            if not row or price is None or price < 0 or not name or (cat not in CATEGORIES and cat != "Other"):
                flash("Enter a name, a category and a price like 1500 or 1500.00.", "error")
            else:
                new = {"name": name, "unit": clean(request.form.get("unit"), 80), "price_cents": price, "category": cat,
                       "active": 1 if request.form.get("active") else 0}
                changes = {k: [row[k], v] for k, v in new.items() if row[k] != v}
                if changes:
                    conn.update("fee_schedule", fid, {**new, "updated_at": now_str(), "updated_by": g.user.id})
                    audit.record("fee_changed", "fee_schedule", fid, f"Fee schedule: {name}", changes)
                flash(f"Saved {name}: {peso(price)}.", "success")
        elif action == "add":
            name = clean(request.form.get("name"), 200)
            price = parse_money(request.form.get("price"))
            if not name or price is None or price < 0:
                flash("Enter the service name and price.", "error")
            else:
                cat = request.form.get("category") or classify(name)
                fid = conn.insert("fee_schedule", {"name": name, "unit": clean(request.form.get("unit"), 80), "price_cents": price,
                                                   "category": cat if cat in CATEGORIES else classify(name), "active": 1,
                                                   "sort_order": (conn.scalar("SELECT MAX(sort_order) FROM fee_schedule") or 0) + 1,
                                                   "updated_at": now_str(), "updated_by": g.user.id})
                audit.record("fee_added", "fee_schedule", fid, f"Added to fee schedule: {name} {peso(price)}")
                flash(f"Added {name}.", "success")
        return redirect(url_for("fees.index", q=request.form.get("q") or None, cat=request.form.get("cat") or None))
    q = clean(request.args.get("q"), 80).lower()
    cat = request.args.get("cat") or ""
    show_inactive = bool(request.args.get("inactive"))
    rows = conn.all("SELECT f.*, u.name AS by_name FROM fee_schedule f LEFT JOIN users u ON u.id = f.updated_by")
    order = {c: i for i, c in enumerate(CATEGORIES)}
    rows = sorted(rows, key=lambda r: (order.get(r["category"], 99), r["sort_order"], r["name"]))
    counts = {}
    for r in rows:
        if r["active"]:
            counts[r["category"]] = counts.get(r["category"], 0) + 1
    if not show_inactive:
        rows = [r for r in rows if r["active"]]
    if cat:
        rows = [r for r in rows if r["category"] == cat]
    if q:
        rows = [r for r in rows if q in r["name"].lower() or q in (r["unit"] or "").lower()]
    groups = []
    for r in rows:
        if not groups or groups[-1][0] != r["category"]:
            groups.append((r["category"], []))
        groups[-1][1].append(r)
    return render_template("staff/admin/fees.html", groups=groups, categories=CATEGORIES, counts=counts, q=q, cat=cat,
                           show_inactive=show_inactive, total=sum(counts.values()))


@bp.route("/import", methods=["POST"])
@require("fees.manage")
def import_file():
    """Update prices from an Excel/CSV like SERVICES.xlsx (SERVICES/PROCEDURE, UNIT, PRICE). Same name + unit = update;
    new names are added and sorted into a category automatically. Nothing is deleted."""
    conn = get_db()
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose the Excel or CSV file.", "error")
        return redirect(url_for("fees.index"))
    try:
        table = read_table(f.filename, f.read(5 * 1024 * 1024))
    except SheetError as exc:
        flash(str(exc), "error")
        return redirect(url_for("fees.index"))

    def col(row, *names):
        for n in names:
            if n in row:
                return " ".join(str(row[n] or "").split())
        return ""

    existing = {(r["name"].upper(), (r["unit"] or "").upper()): r for r in conn.all("SELECT * FROM fee_schedule")}
    added = updated = skipped = 0
    with conn.transaction():
        nxt = (conn.scalar("SELECT MAX(sort_order) FROM fee_schedule") or 0) + 1
        for row in table:
            name = col(row, "services/procedure", "service", "services", "procedure", "name")[:200]
            unit = col(row, "unit")[:80]
            price = parse_money(col(row, "price", "amount").replace("₱", "").replace(",", ""))
            if not name:
                continue
            if price is None or price < 0:
                skipped += 1
                continue
            hit = existing.get((name.upper(), unit.upper()))
            if hit:
                if hit["price_cents"] != price or not hit["active"]:
                    conn.update("fee_schedule", hit["id"], {"price_cents": price, "active": 1, "updated_at": now_str(), "updated_by": g.user.id})
                    updated += 1
            else:
                conn.insert("fee_schedule", {"name": name, "unit": unit, "price_cents": price, "category": classify(name), "active": 1,
                                             "sort_order": nxt, "updated_at": now_str(), "updated_by": g.user.id})
                existing[(name.upper(), unit.upper())] = {"id": None}
                nxt += 1
                added += 1
        audit.record("fees_imported", "fee_schedule", None, f"Imported fee schedule: {added} added, {updated} price changes",
                     {"added": added, "updated": updated, "skipped": skipped})
    flash(f"Fee schedule updated: {added} added, {updated} price change(s)" + (f", {skipped} row(s) skipped (no valid price)" if skipped else "") + ".",
          "success")
    return redirect(url_for("fees.index"))

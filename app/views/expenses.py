"""Clinic expenses per branch: Add (draft) -> Post (final, counted in reports) -> optional Void.

Each entry: date and time, branch, category, item name, description, quantity x unit price (= amount), who spent it,
supplier, payment method, OR/receipt no., notes and an optional receipt photo. Reports: daily, monthly or any date range,
with totals per branch, per category and per day (print or CSV)."""
from __future__ import annotations

import csv
import io

from datetime import date as date_cls, timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import require
from ..billing import PAYMENT_METHODS
from ..db import get_db
from ..permissions import branch_filter
from ..uploads import document_path, save_document
from ..util import clean, now, now_str, parse_date, parse_money, peso, to_int, today
from .common import branches_for_user, date_range_args

bp = Blueprint("expenses", __name__, url_prefix="/staff/expenses")

CATEGORIES = ["Dental supplies", "Laboratory fees", "Rent", "Utilities (power, water, internet)", "Salaries & wages",
              "Equipment & maintenance", "Marketing & advertising", "Professional fees", "Taxes, permits & licenses",
              "Transportation & delivery", "Office supplies", "Pantry & cleaning supplies", "Food & meals", "Repairs",
              "Miscellaneous"]


def _scope(alias="e"):
    frag, params = branch_filter(g.user, f"{alias}.branch_id")
    if not g.user.can("expenses.view"):
        frag += f" AND {alias}.created_by = ?"  # with only 'Add Expenses', users see just their own entries
        params = [*params, g.user.id]
    return frag, params


@bp.route("/", methods=["GET", "POST"])
@require("expenses.view", "expenses.add", any_of=True)
def index():
    conn = get_db()
    if request.method == "POST":
        if not g.user.can("expenses.add"):
            abort(403)
        branch_id = to_int(request.form.get("branch_id"))
        d = parse_date(request.form.get("expense_date")) or today()
        tm = clean(request.form.get("expense_time"), 5)
        category = request.form.get("category")
        method = request.form.get("method")
        item = clean(request.form.get("item"), 150)
        qty_txt = (request.form.get("qty") or "1").strip()
        try:
            qty = float(qty_txt)
        except ValueError:
            qty = -1
        unit = parse_money(request.form.get("unit_price")) if (request.form.get("unit_price") or "").strip() else None
        amount = parse_money(request.form.get("amount")) if (request.form.get("amount") or "").strip() else None
        if amount is None and unit is not None and qty > 0:
            amount = round(unit * qty)
        receipt = request.files.get("receipt")
        if not branch_id or not g.user.in_branch(branch_id):
            flash("Choose one of your branches.", "error")
        elif not item and not clean(request.form.get("description"), 300):
            flash("Enter the item name or a description.", "error")
        elif not amount or amount <= 0 or qty <= 0 or category not in CATEGORIES or method not in PAYMENT_METHODS or d > today():
            flash("Enter a category, the price (or quantity and unit price), a payment method and a date that isn't in the future.", "error")
        elif tm and not (len(tm) == 5 and tm[2] == ":" and tm[:2].isdigit() and tm[3:].isdigit() and int(tm[:2]) < 24 and int(tm[3:]) < 60):
            flash("Enter the time like 14:30.", "error")
        else:
            stored = ""
            if receipt and receipt.filename:
                stored, _mime, _size, _orig, err = save_document(receipt)
                if err:
                    flash(f"Receipt: {err}", "error")
                    return redirect(url_for("expenses.index"))
            eid = conn.insert("expenses", {"branch_id": branch_id, "expense_date": d.isoformat(), "expense_time": tm or now().strftime("%H:%M"),
                                           "category": category, "item": item, "description": clean(request.form.get("description"), 300),
                                           "qty": qty, "unit_price_cents": unit, "spent_by": clean(request.form.get("spent_by"), 120) or g.user.name,
                                           "payee": clean(request.form.get("payee"), 150), "amount_cents": amount, "method": method,
                                           "reference": clean(request.form.get("reference"), 80), "notes": clean(request.form.get("notes"), 500),
                                           "receipt_stored": stored or "", "status": "draft", "created_by": g.user.id, "created_at": now_str()})
            audit.record("expense_added", "expense", eid, f"Added expense {peso(amount)} ({category}: {item or 'no item name'})", branch_id=branch_id)
            flash(f"Expense of {peso(amount)} added. It counts in reports once it's posted.", "success")
        return redirect(url_for("expenses.index"))
    start, end = date_range_args(31)
    frag, params = _scope()
    where, args = [frag, "e.expense_date BETWEEN ? AND ?"], [*params, start.isoformat(), end.isoformat()]
    status = request.args.get("status")
    if status in ("draft", "posted", "void"):
        where.append("e.status = ?")
        args.append(status)
    category = request.args.get("category")
    if category in CATEGORIES:
        where.append("e.category = ?")
        args.append(category)
    branch = to_int(request.args.get("branch"))
    if branch:
        where.append("e.branch_id = ?")
        args.append(branch)
    rows = conn.all("SELECT e.*, b.name AS branch, u.name AS by_name, pu.name AS posted_by_name FROM expenses e "
                    "JOIN branches b ON b.id = e.branch_id LEFT JOIN users u ON u.id = e.created_by LEFT JOIN users pu ON pu.id = e.posted_by "
                    f"WHERE {' AND '.join(where)} ORDER BY e.expense_date DESC, e.expense_time DESC, e.id DESC LIMIT 500", args)
    by_cat = {}
    for r in rows:
        if r["status"] == "posted":
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + r["amount_cents"]
    totals = {s: sum(r["amount_cents"] for r in rows if r["status"] == s) for s in ("draft", "posted")}
    return render_template("staff/expenses/index.html", rows=rows, start=start, end=end, status=status, category=category, branch=branch,
                           categories=CATEGORIES, by_cat=sorted(by_cat.items(), key=lambda x: -x[1]), totals=totals,
                           branches=branches_for_user(g.user), today=today().isoformat(), now_hm=now().strftime("%H:%M"))


def _load(expense_id):
    e = get_db().one("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    if not e or not g.user.in_branch(e["branch_id"]):
        abort(404)
    return e


@bp.route("/<int:expense_id>/post", methods=["POST"])
@require("expenses.post")
def post(expense_id):
    conn = get_db()
    e = _load(expense_id)
    if e["status"] == "draft":
        conn.execute("UPDATE expenses SET status = 'posted', posted_by = ?, posted_at = ? WHERE id = ?", (g.user.id, now_str(), expense_id))
        audit.record("expense_posted", "expense", expense_id, f"Posted expense {peso(e['amount_cents'])}", branch_id=e["branch_id"])
        flash("Expense posted.", "success")
    return redirect(request.referrer if request.referrer and "/staff/expenses" in request.referrer else url_for("expenses.index"))


@bp.route("/<int:expense_id>/void", methods=["POST"])
@require("expenses.post")
def void(expense_id):
    conn = get_db()
    e = _load(expense_id)
    reason = clean(request.form.get("reason"), 300)
    if e["status"] == "void" or not reason:
        flash("Give a reason for voiding.", "error")
    else:
        conn.execute("UPDATE expenses SET status = 'void', void_reason = ? WHERE id = ?", (reason, expense_id))
        audit.record("expense_voided", "expense", expense_id, f"Voided expense {peso(e['amount_cents'])}", {"reason": reason}, e["branch_id"])
        flash("Expense voided.", "success")
    return redirect(url_for("expenses.index"))


@bp.route("/<int:expense_id>/delete", methods=["POST"])
@require("expenses.add")
def delete_draft(expense_id):
    conn = get_db()
    e = _load(expense_id)
    if e["status"] != "draft" or (e["created_by"] != g.user.id and not g.user.can("expenses.post")):
        abort(403)
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    audit.record("expense_draft_deleted", "expense", expense_id, f"Deleted draft expense {peso(e['amount_cents'])}", dict(e), e["branch_id"])
    flash("Draft expense deleted.", "success")
    return redirect(url_for("expenses.index"))


@bp.route("/export.csv")
@require("expenses.view")
def export():
    if not g.user.can("reports.export"):
        abort(403)
    conn = get_db()
    start, end = date_range_args(31)
    frag, params = _scope()
    rows = conn.all("SELECT e.*, b.name AS branch FROM expenses e JOIN branches b ON b.id = e.branch_id "
                    f"WHERE {frag} AND e.expense_date BETWEEN ? AND ? ORDER BY e.expense_date, e.expense_time", [*params, start.isoformat(), end.isoformat()])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Time", "Branch", "Category", "Item", "Description", "Qty", "Unit price (PHP)", "Amount (PHP)", "Spent by",
                "Supplier / paid to", "Method", "OR / receipt no.", "Notes", "Status"])
    for r in rows:
        w.writerow([r["expense_date"], r["expense_time"], r["branch"], r["category"], r["item"], r["description"], r["qty"],
                    "" if r["unit_price_cents"] is None else r["unit_price_cents"] / 100, r["amount_cents"] / 100, r["spent_by"], r["payee"],
                    PAYMENT_METHODS.get(r["method"], r["method"]), r["reference"], r["notes"], r["status"]])
    audit.record("report_exported", "report", None, "Exported expenses CSV", {"from": start.isoformat(), "to": end.isoformat()})
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="dental-haven-expenses-{start}-to-{end}.csv"',
                             "Cache-Control": "no-store"})


@bp.route("/<int:expense_id>/receipt")
@require("expenses.view", "expenses.add", any_of=True)
def receipt(expense_id):
    e = _load(expense_id)
    if not e["receipt_stored"] or not (g.user.can("expenses.view") or e["created_by"] == g.user.id):
        abort(404)
    resp = send_file(document_path(e["receipt_stored"]), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


def _report_range():
    """mode=daily (day), monthly (month=YYYY-MM) or range (from/to). Returns (mode, start, end, label)."""
    mode = request.args.get("mode", "daily")
    t = today()
    if mode == "monthly":
        m = request.args.get("month") or t.strftime("%Y-%m")
        try:
            y, mo = int(m[:4]), int(m[5:7])
            start = date_cls(y, mo, 1)
        except (ValueError, IndexError):
            start = t.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return mode, start, end, start.strftime("%B %Y")
    if mode == "range":
        start, end = date_range_args(31)
        return mode, start, end, f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"
    day = parse_date(request.args.get("day")) or t
    return "daily", day, day, day.strftime("%A, %B %d, %Y")


@bp.route("/report")
@require("expenses.view")
def report():
    """Expense report: totals per branch (posted, and pending drafts), per category, per day, and the full list."""
    conn = get_db()
    mode, start, end, label = _report_range()
    branches = branches_for_user(g.user)
    chosen = [b["id"] for b in branches if str(b["id"]) in request.args.getlist("branch")] or [b["id"] for b in branches]
    frag, params = _scope()
    marks = ",".join("?" for _ in chosen) or "NULL"
    rows = conn.all("SELECT e.*, b.name AS branch, u.name AS by_name FROM expenses e JOIN branches b ON b.id = e.branch_id "
                    "LEFT JOIN users u ON u.id = e.created_by "
                    f"WHERE {frag} AND e.branch_id IN ({marks}) AND e.expense_date BETWEEN ? AND ? AND e.status != 'void' "
                    "ORDER BY e.expense_date, e.expense_time, e.id", [*params, *chosen, start.isoformat(), end.isoformat()])
    picked_cats = [c for c in request.args.getlist("category") if c in CATEGORIES]
    if picked_cats:
        rows = [r for r in rows if r["category"] in picked_cats]
    include_pending = bool(request.args.get("pending"))
    counted = [r for r in rows if r["status"] == "posted" or (include_pending and r["status"] == "draft")]
    names = {b["id"]: b["name"] for b in branches}
    counted_ids = {r["id"] for r in counted}
    per_branch = {bid: {"name": names[bid], "n": 0, "total": 0, "pending": 0, "pending_n": 0} for bid in chosen}
    for r in rows:
        pb = per_branch[r["branch_id"]]
        if r["status"] == "draft":
            pb["pending"] += r["amount_cents"]
            pb["pending_n"] += 1
        if r["id"] in counted_ids:
            pb["n"] += 1
            pb["total"] += r["amount_cents"]
    cats = sorted({r["category"] for r in counted}, key=lambda c: CATEGORIES.index(c) if c in CATEGORIES else 99)
    matrix = {c: {bid: 0 for bid in chosen} for c in cats}
    for r in counted:
        matrix[r["category"]][r["branch_id"]] += r["amount_cents"]
    days = {}
    for r in counted:
        d = days.setdefault(r["expense_date"], {bid: 0 for bid in chosen})
        d[r["branch_id"]] += r["amount_cents"]
    grand = sum(p["total"] for p in per_branch.values())
    if request.args.get("format") == "csv":
        if not g.user.can("reports.export"):
            abort(403)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"Dental Haven expense report: {label}"])
        if picked_cats:
            w.writerow(["Categories: " + ", ".join(picked_cats)])
        w.writerow([])
        w.writerow(["Summary per branch", "Entries", "Total (PHP)", "Pending, not posted (PHP)"])
        for p in per_branch.values():
            w.writerow([p["name"], p["n"], p["total"] / 100, p["pending"] / 100])
        w.writerow(["ALL BRANCHES", sum(p["n"] for p in per_branch.values()), grand / 100, sum(p["pending"] for p in per_branch.values()) / 100])
        w.writerow([])
        w.writerow(["Category", *[names[b] for b in chosen], "Total (PHP)"])
        for c in cats:
            w.writerow([c, *[matrix[c][b] / 100 for b in chosen], sum(matrix[c].values()) / 100])
        w.writerow([])
        w.writerow(["Date", "Time", "Branch", "Category", "Item", "Description", "Qty", "Unit price", "Amount (PHP)", "Spent by", "Supplier",
                    "Method", "OR / receipt no.", "Status"])
        for r in counted:
            w.writerow([r["expense_date"], r["expense_time"], r["branch"], r["category"], r["item"], r["description"], r["qty"],
                        "" if r["unit_price_cents"] is None else r["unit_price_cents"] / 100, r["amount_cents"] / 100, r["spent_by"],
                        r["payee"], PAYMENT_METHODS.get(r["method"], r["method"]), r["reference"], r["status"]])
        audit.record("report_exported", "report", None, f"Exported expense report ({label})")
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="expenses-{start}-to-{end}.csv"', "Cache-Control": "no-store"})
    return render_template("staff/expenses/report.html", mode=mode, start=start, end=end, label=label, branches=branches, chosen=chosen,
                           names=names, per_branch=per_branch, matrix=matrix, cats=cats, days=sorted(days.items()), rows=counted,
                           grand=grand, include_pending=include_pending, today=today(), args=request.args,
                           all_categories=CATEGORIES, picked_cats=picked_cats)

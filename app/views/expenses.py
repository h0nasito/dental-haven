"""Clinic expenses per branch: Add (draft) -> Post (final, counted in reports) -> optional Void."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..billing import PAYMENT_METHODS
from ..db import get_db
from ..permissions import branch_filter
from ..util import clean, now_str, parse_date, parse_money, peso, to_int, today
from .common import branches_for_user, date_range_args

bp = Blueprint("expenses", __name__, url_prefix="/staff/expenses")

CATEGORIES = ["Dental supplies", "Laboratory fees", "Rent", "Utilities (power, water, internet)", "Salaries & wages",
              "Equipment & maintenance", "Marketing & advertising", "Professional fees", "Taxes, permits & licenses",
              "Transportation & delivery", "Office supplies", "Miscellaneous"]


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
        amount = parse_money(request.form.get("amount"))
        d = parse_date(request.form.get("expense_date")) or today()
        category = request.form.get("category")
        method = request.form.get("method")
        if not branch_id or not g.user.in_branch(branch_id):
            flash("Choose one of your branches.", "error")
        elif not amount or category not in CATEGORIES or method not in PAYMENT_METHODS or d > today():
            flash("Enter a category, an amount, a payment method and a date that isn't in the future.", "error")
        else:
            eid = conn.insert("expenses", {"branch_id": branch_id, "expense_date": d.isoformat(), "category": category,
                                           "description": clean(request.form.get("description"), 300),
                                           "payee": clean(request.form.get("payee"), 150), "amount_cents": amount, "method": method,
                                           "reference": clean(request.form.get("reference"), 80), "status": "draft",
                                           "created_by": g.user.id, "created_at": now_str()})
            audit.record("expense_added", "expense", eid, f"Added expense {peso(amount)} ({category})", branch_id=branch_id)
            flash("Expense added. It counts in reports once it's posted.", "success")
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
    rows = conn.all("SELECT e.*, b.name AS branch, u.name AS by_name, pu.name AS posted_by_name FROM expenses e "
                    "JOIN branches b ON b.id = e.branch_id LEFT JOIN users u ON u.id = e.created_by LEFT JOIN users pu ON pu.id = e.posted_by "
                    f"WHERE {' AND '.join(where)} ORDER BY e.expense_date DESC, e.id DESC LIMIT 500", args)
    by_cat = {}
    for r in rows:
        if r["status"] == "posted":
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + r["amount_cents"]
    totals = {s: sum(r["amount_cents"] for r in rows if r["status"] == s) for s in ("draft", "posted")}
    return render_template("staff/expenses/index.html", rows=rows, start=start, end=end, status=status, category=category,
                           categories=CATEGORIES, by_cat=sorted(by_cat.items(), key=lambda x: -x[1]), totals=totals,
                           branches=branches_for_user(g.user), today=today().isoformat())


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
                    f"WHERE {frag} AND e.expense_date BETWEEN ? AND ? ORDER BY e.expense_date", [*params, start.isoformat(), end.isoformat()])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Branch", "Category", "Description", "Payee", "Method", "Reference", "Amount (PHP)", "Status"])
    for r in rows:
        w.writerow([r["expense_date"], r["branch"], r["category"], r["description"], r["payee"], PAYMENT_METHODS.get(r["method"], r["method"]),
                    r["reference"], r["amount_cents"] / 100, r["status"]])
    audit.record("report_exported", "report", None, "Exported expenses CSV", {"from": start.isoformat(), "to": end.isoformat()})
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="dental-haven-expenses-{start}-to-{end}.csv"',
                             "Cache-Control": "no-store"})

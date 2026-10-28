"""Laboratory expenses: what the lab spends (materials, rent, utilities, courier, ...).

Recorded by people who handle lab billing (and the super admin). An expense counts as soon as it is saved; a mistake is
voided with a reason instead of deleted, so the history stays. The Lab financial report subtracts these from the
payments received to show the lab's net for the period."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import login_required
from ..db import get_db
from ..uploads import document_path, save_document
from ..util import clean, now_str, parse_date, parse_money, peso, to_int, today
from .common import date_range_args
from .lab_works import _in, _lab_ids, _need, lab_display, lab_parse_pay, lab_pay_label, lab_pay_options, my_labs

bp = Blueprint("lab_expenses", __name__, url_prefix="/staff/lab/expenses")

CATEGORIES = ["Lab materials & supplies", "Zirconia, e.max & CAD/CAM materials", "Outsourced lab work", "Equipment & tools",
              "Repairs & maintenance", "Rent", "Electricity", "Water", "Internet & phone", "Courier & delivery",
              "Transportation", "Salaries & wages", "Office supplies", "Food & meals", "Taxes, permits & licenses",
              "Miscellaneous"]


def summary(conn, lab_ids: list[int], start: str, end: str) -> dict:
    """Lab expenses in a period (voided ones left out): total, by category and by where the money came from."""
    marks = _in(lab_ids)
    rows = conn.all(f"SELECT category, method, account, SUM(amount_cents) AS amt FROM lab_expenses WHERE status = 'ok' "
                    f"AND lab_id IN ({marks}) AND expense_date BETWEEN ? AND ? GROUP BY category, method, account",
                    [*lab_ids, start, end]) if lab_ids else []
    by_cat, by_src = {}, {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + r["amt"]
        k = lab_pay_label(r["method"], r["account"])
        by_src[k] = by_src.get(k, 0) + r["amt"]
    cats = sorted(by_cat.items(), key=lambda x: (CATEGORIES.index(x[0]) if x[0] in CATEGORIES else 99, x[0]))
    return {"total": sum(by_cat.values()), "by_category": cats, "by_source": by_src}


def _load(expense_id):
    e = get_db().one("SELECT * FROM lab_expenses WHERE id = ?", (expense_id,))
    if not e or e["lab_id"] not in _lab_ids():
        abort(404)
    return e


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    _need("lab.billing")
    conn = get_db()
    labs = my_labs(conn)
    ids = [l["id"] for l in labs]
    if request.method == "POST":
        lab_id = to_int(request.form.get("lab_id")) or (ids[0] if len(ids) == 1 else None)
        d = parse_date(request.form.get("expense_date")) or today()
        category = request.form.get("category")
        item = clean(request.form.get("item"), 150)
        description = clean(request.form.get("description"), 300)
        try:
            qty = float((request.form.get("qty") or "1").strip())
        except ValueError:
            qty = -1
        unit = parse_money(request.form.get("unit_price")) if (request.form.get("unit_price") or "").strip() else None
        amount = parse_money(request.form.get("amount")) if (request.form.get("amount") or "").strip() else None
        if amount is None and unit is not None and qty > 0:
            amount = round(unit * qty)
        pay = lab_parse_pay(request.form.get("paid_with"), conn)
        receipt = request.files.get("receipt")
        if lab_id not in ids:
            flash("Choose the laboratory.", "error")
        elif not item and not description:
            flash("Enter what was bought or paid for.", "error")
        elif category not in CATEGORIES:
            flash("Choose a category.", "error")
        elif not amount or amount <= 0 or qty <= 0:
            flash("Enter the amount (or the quantity and unit price).", "error")
        elif not pay:
            flash("Choose how it was paid.", "error")
        elif d > today():
            flash("The date can't be in the future.", "error")
        else:
            stored = ""
            if receipt and receipt.filename:
                stored, _mime, _size, _orig, err = save_document(receipt)
                if err:
                    flash(f"Receipt: {err}", "error")
                    return redirect(url_for("lab_expenses.index"))
            eid = conn.insert("lab_expenses", {
                "lab_id": lab_id, "expense_date": d.isoformat(), "category": category, "item": item, "description": description,
                "qty": qty, "unit_price_cents": unit, "amount_cents": amount, "payee": clean(request.form.get("payee"), 150),
                "method": pay[0], "account": pay[1], "reference": clean(request.form.get("reference"), 80),
                "notes": clean(request.form.get("notes"), 500), "receipt_stored": stored or "", "status": "ok",
                "created_by": g.user.id, "created_at": now_str()})
            audit.record("lab_expense_added", "lab_expense", eid, f"Lab expense {peso(amount)} ({category}: {item or description})")
            flash(f"Lab expense of {peso(amount)} saved.", "success")
        return redirect(url_for("lab_expenses.index"))

    start, end = date_range_args(31)
    if not request.args.get("from"):
        start = end.replace(day=1)
    where, args = [f"e.lab_id IN ({_in(ids)})", "e.expense_date BETWEEN ? AND ?"], [*ids, start.isoformat(), end.isoformat()]
    category = request.args.get("category") if request.args.get("category") in CATEGORIES else ""
    if category:
        where.append("e.category = ?")
        args.append(category)
    show_void = request.args.get("void") == "1"
    if not show_void:
        where.append("e.status = 'ok'")
    rows = conn.all("SELECT e.*, l.name AS lab, u.name AS by_name, vu.name AS voided_by_name FROM lab_expenses e "
                    "JOIN laboratories l ON l.id = e.lab_id LEFT JOIN users u ON u.id = e.created_by LEFT JOIN users vu ON vu.id = e.voided_by "
                    f"WHERE {' AND '.join(where)} ORDER BY e.expense_date DESC, e.id DESC LIMIT 1000", args) if ids else []
    if request.args.get("format") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        safe = lambda x: ("'" + x) if isinstance(x, str) and x[:1] in ("=", "+", "-", "@") else x  # noqa: E731
        w.writerow(["Date", "Laboratory", "Category", "Item", "Description", "Qty", "Unit price (PHP)", "Amount (PHP)", "Paid with",
                    "Supplier / paid to", "OR / reference", "Notes", "Status", "Recorded by"])
        for r in rows:
            w.writerow([safe(x) for x in (r["expense_date"], lab_display(r["lab"]), r["category"], r["item"], r["description"], r["qty"],
                                           (r["unit_price_cents"] / 100) if r["unit_price_cents"] is not None else "", r["amount_cents"] / 100,
                                           lab_pay_label(r["method"], r["account"]), r["payee"], r["reference"], r["notes"],
                                           "Voided" if r["status"] == "void" else "", r["by_name"] or "")])
        w.writerow(["", "", "", "", "", "", "Total", sum(r["amount_cents"] for r in rows if r["status"] == "ok") / 100])
        audit.record("lab_expenses_exported", "lab_expense", None, f"Exported lab expenses {start} to {end}")
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="lab-expenses-{start}-to-{end}.csv"', "Cache-Control": "no-store"})
    rep = summary(conn, ids, start.isoformat(), end.isoformat())
    if category:
        rep["total"] = sum(r["amount_cents"] for r in rows if r["status"] == "ok")
    return render_template("staff/lab_works/expenses.html", rows=rows, rep=rep, start=start, end=end, category=category,
                           categories=CATEGORIES, labs=labs, lab_display=lab_display, show_void=show_void,
                           pay_options=lab_pay_options(conn), lab_pay_label=lab_pay_label, today=today().isoformat())


@bp.route("/<int:expense_id>/void", methods=["POST"])
@login_required
def void(expense_id):
    _need("lab.billing")
    e = _load(expense_id)
    reason = clean(request.form.get("reason"), 200)
    if e["status"] == "void":
        flash("This expense is already voided.", "info")
    elif not reason:
        flash("Enter the reason for voiding.", "error")
    else:
        get_db().execute("UPDATE lab_expenses SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                         (reason, g.user.id, now_str(), expense_id))
        audit.record("lab_expense_voided", "lab_expense", expense_id, f"Voided lab expense {peso(e['amount_cents'])}: {reason}")
        flash("Expense voided. It no longer counts in the totals.", "success")
    return redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/staff/lab/expenses") else url_for("lab_expenses.index"))


@bp.route("/<int:expense_id>/receipt")
@login_required
def receipt(expense_id):
    _need("lab.billing")
    e = _load(expense_id)
    if not e["receipt_stored"]:
        abort(404)
    resp = send_file(document_path(e["receipt_stored"]), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

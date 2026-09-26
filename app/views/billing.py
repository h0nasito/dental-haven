"""Invoices, payments, refunds/voids and sales, collections and operations reports (with CSV export)."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, settings
from ..auth import require
from ..billing import (CREDIT_METHOD, PAYMENT_METHODS, collections, compute_totals, credit_balance, line_amount,
                       next_invoice_number, paid_amount, payment_state)
from ..db import get_db
from ..permissions import branch_filter, can_see_patient
from ..util import clean, now_str, parse_date, parse_money, peso, to_int, today
from .common import branches_for_user, date_range_args, paginate, services

bp = Blueprint("billing", __name__, url_prefix="/staff")


def _load_invoice(invoice_id):
    conn = get_db()
    inv = conn.one("SELECT i.*, p.first_name, p.last_name, p.chart_no, p.address, b.name AS branch, b.address AS branch_address, "
                   "b.phone AS branch_phone, u.name AS created_by_name FROM invoices i JOIN patients p ON p.id = i.patient_id "
                   "JOIN branches b ON b.id = i.branch_id LEFT JOIN users u ON u.id = i.created_by WHERE i.id = ?", (invoice_id,))
    if not inv:
        abort(404)
    if not g.user.in_branch(inv["branch_id"]):
        abort(403)
    return inv


def _recalc(conn, invoice_id):
    inv = conn.one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    items = conn.all("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    totals = compute_totals(items, inv["discount_cents"], conn)
    conn.update("invoices", invoice_id, totals)


@bp.app_context_processor
def _ctx():
    return {"PAYMENT_METHODS": PAYMENT_METHODS, "PAYMENT_LABELS": {**PAYMENT_METHODS, CREDIT_METHOD: "Account credit"}}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@bp.route("/invoices")
@require("billing.view")
def invoices():
    conn = get_db()
    bf, bp_ = branch_filter(g.user, "i.branch_id")
    start, end = date_range_args(60)
    where, args = [bf, "(i.status = 'draft' OR (i.issued_at >= ? AND i.issued_at <= ?))"], [*bp_, start.isoformat(), end.isoformat()]
    status = request.args.get("status")
    if status in ("draft", "issued", "void"):
        where.append("i.status = ?")
        args.append(status)
    total = conn.scalar(f"SELECT COUNT(*) FROM invoices i WHERE {' AND '.join(where)}", args)
    pg = paginate(total, 50)
    rows = conn.all(
        "SELECT i.*, p.first_name, p.last_name, b.name AS branch, "
        "(SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END),0) FROM payments WHERE invoice_id=i.id AND status='valid') AS paid "
        f"FROM invoices i JOIN patients p ON p.id = i.patient_id JOIN branches b ON b.id = i.branch_id WHERE {' AND '.join(where)} "
        "ORDER BY COALESCE(i.issued_at, i.created_at) DESC, i.id DESC LIMIT ? OFFSET ?", [*args, pg["limit"], pg["offset"]])
    for r in rows:
        r["state"] = payment_state(r["total_cents"], r["paid"], r["status"])
    return render_template("staff/billing/invoices.html", rows=rows, pg=pg, start=start, end=end, status=status)


@bp.route("/invoices/new", methods=["GET", "POST"])
@require("billing.manage")
def invoice_new():
    conn = get_db()
    patient_id = to_int(request.values.get("patient_id"))
    appointment_id = to_int(request.values.get("appointment_id"))
    if not patient_id or not can_see_patient(conn, g.user, patient_id):
        flash("Open the patient (or appointment) first, then create the invoice from there.", "info")
        return redirect(url_for("patients.index"))
    patient = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    appt = None
    if appointment_id:
        appt = conn.one("SELECT a.*, s.name AS service, s.default_price_cents FROM appointments a JOIN services s ON s.id = a.service_id "
                        "WHERE a.id = ? AND a.patient_id = ?", (appointment_id, patient_id))
    branch_id = to_int(request.form.get("branch_id")) if request.method == "POST" else \
        (appt["branch_id"] if appt else (g.user.active_branch_id or patient["preferred_branch_id"]))
    if request.method == "POST":
        if not branch_id or not g.user.in_branch(branch_id):
            flash("Choose one of your branches.", "error")
        else:
            with conn.transaction():
                inv_id = conn.insert("invoices", {"branch_id": branch_id, "patient_id": patient_id,
                                                  "appointment_id": appt["id"] if appt else None, "status": "draft",
                                                  "created_by": g.user.id, "created_at": now_str()})
                if appt:
                    price = appt["default_price_cents"] or 0
                    conn.insert("invoice_items", {"invoice_id": inv_id, "service_id": appt["service_id"], "description": appt["service"],
                                                  "qty": 1, "unit_price_cents": price, "discount_cents": 0, "amount_cents": price})
                _recalc(conn, inv_id)
                audit.record("invoice_created", "invoice", inv_id, "Draft invoice created", branch_id=branch_id)
            return redirect(url_for("billing.invoice", invoice_id=inv_id))
    return render_template("staff/billing/invoice_new.html", patient=patient, appt=appt, branch_id=branch_id,
                           branches=branches_for_user(g.user))


@bp.route("/invoices/<int:invoice_id>")
@require("billing.view")
def invoice(invoice_id):
    conn = get_db()
    inv = _load_invoice(invoice_id)
    items = conn.all("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,))
    payments = conn.all("SELECT p.*, u.name AS received_by_name, v.name AS voided_by_name FROM payments p "
                        "LEFT JOIN users u ON u.id = p.received_by LEFT JOIN users v ON v.id = p.voided_by "
                        "WHERE p.invoice_id = ? ORDER BY p.id", (invoice_id,))
    paid = paid_amount(conn, invoice_id)
    history = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                       "WHERE a.entity_type = 'invoice' AND a.entity_id = ? ORDER BY a.id DESC", (invoice_id,))
    return render_template("staff/billing/invoice.html", inv=inv, items=items, payments=payments, paid=paid,
                           credit=credit_balance(conn, inv["patient_id"]),
                           balance=inv["total_cents"] - paid, state=payment_state(inv["total_cents"], paid, inv["status"]),
                           services=services(), history=history, tax_label=settings.get("invoice.tax_label"),
                           tax_enabled=settings.get("invoice.tax_enabled"), tax_inclusive=settings.get("invoice.tax_inclusive"),
                           today=today().isoformat())


@bp.route("/invoices/<int:invoice_id>/print")
@require("billing.view")
def invoice_print(invoice_id):
    conn = get_db()
    inv = _load_invoice(invoice_id)
    items = conn.all("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,))
    paid = paid_amount(conn, invoice_id)
    return render_template("staff/billing/invoice_print.html", inv=inv, items=items, paid=paid,
                           balance=inv["total_cents"] - paid, tax_label=settings.get("invoice.tax_label"),
                           tax_enabled=settings.get("invoice.tax_enabled"), tax_inclusive=settings.get("invoice.tax_inclusive"))


EDIT_ACTION_PERMS = {"add_item": "billing.manage", "issue": "billing.manage", "delete": "billing.manage",
                     "remove_item": "bills.edit", "discount": "bills.edit"}


@bp.route("/invoices/<int:invoice_id>/edit", methods=["POST"])
@require("billing.view")
def invoice_edit(invoice_id):
    conn = get_db()
    inv = _load_invoice(invoice_id)
    action = request.form.get("action")
    if action not in EDIT_ACTION_PERMS:
        abort(400)
    if not g.user.can(EDIT_ACTION_PERMS[action]):
        abort(403)
    if inv["status"] != "draft" and action in ("add_item", "remove_item", "discount", "issue", "delete"):
        flash("Only draft invoices can be changed. Void and re-issue if needed.", "error")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id))
    with conn.transaction(immediate=True):
        if action == "add_item":
            desc = clean(request.form.get("description"), 200)
            svc_id = to_int(request.form.get("service_id"))
            if not desc and svc_id:
                svc = conn.one("SELECT name FROM services WHERE id = ?", (svc_id,))
                desc = svc["name"] if svc else ""
            qty = to_int(request.form.get("qty"), 1) or 1
            unit = parse_money(request.form.get("unit_price"))
            disc = parse_money(request.form.get("discount")) or 0
            if not desc or unit is None or not 1 <= qty <= 100:
                flash("Enter a description, quantity and price (e.g. 1500 or 1500.00).", "error")
            else:
                amount = line_amount(qty, unit, disc)
                conn.insert("invoice_items", {"invoice_id": invoice_id, "service_id": svc_id, "description": desc, "qty": qty,
                                              "unit_price_cents": unit, "discount_cents": min(disc, qty * unit), "amount_cents": amount})
                audit.record("invoice_item_added", "invoice", invoice_id, f"Added {desc} {peso(amount)}", branch_id=inv["branch_id"])
        elif action == "remove_item":
            item_id = to_int(request.form.get("item_id"))
            conn.execute("DELETE FROM invoice_items WHERE id = ? AND invoice_id = ?", (item_id, invoice_id))
            audit.record("invoice_item_removed", "invoice", invoice_id, "Removed line", branch_id=inv["branch_id"])
        elif action == "discount":
            disc = parse_money(request.form.get("discount")) or 0
            conn.execute("UPDATE invoices SET discount_cents = ?, notes = ? WHERE id = ?",
                         (disc, clean(request.form.get("notes"), 500), invoice_id))
            audit.record("invoice_discount", "invoice", invoice_id, f"Invoice discount {peso(disc)}",
                         {"reason": clean(request.form.get("notes"), 500)}, inv["branch_id"])
        elif action == "issue":
            items = conn.all("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            if not items:
                flash("Add at least one line before issuing.", "error")
            else:
                _recalc(conn, invoice_id)
                number = next_invoice_number(conn, inv["branch_id"])
                conn.execute("UPDATE invoices SET status = 'issued', number = ?, issued_at = ? WHERE id = ?",
                             (number, today().isoformat(), invoice_id))
                audit.record("invoice_issued", "invoice", invoice_id, f"Issued {number}", branch_id=inv["branch_id"])
                flash(f"Invoice {number} issued.", "success")
                return redirect(url_for("billing.invoice", invoice_id=invoice_id))
        elif action == "delete":
            conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            conn.execute("DELETE FROM invoices WHERE id = ? AND status = 'draft'", (invoice_id,))
            audit.record("invoice_draft_deleted", "invoice", invoice_id, "Deleted draft", branch_id=inv["branch_id"])
            flash("Draft deleted.", "success")
            return redirect(url_for("patients.detail", patient_id=inv["patient_id"]))
        _recalc(conn, invoice_id)
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


PAYMENT_ACTION_PERMS = {"payment": "payments.add", "refund": "billing.void", "void_payment": "billing.void",
                        "apply_credit": "credit.apply"}


@bp.route("/invoices/<int:invoice_id>/payments", methods=["POST"])
@require("billing.view")
def payment(invoice_id):
    conn = get_db()
    inv = _load_invoice(invoice_id)
    action = request.form.get("action", "payment")
    if action not in PAYMENT_ACTION_PERMS:
        abort(400)
    if not g.user.can(PAYMENT_ACTION_PERMS[action]):
        abort(403)
    if inv["status"] != "issued":
        flash("Payments can only be recorded on issued invoices.", "error")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id))
    with conn.transaction(immediate=True):
        paid = paid_amount(conn, invoice_id)
        if action in ("payment", "refund"):
            if action == "refund" and not g.user.can("billing.void"):
                abort(403)
            amount = parse_money(request.form.get("amount"))
            method = request.form.get("method")
            received = parse_date(request.form.get("received_at")) or today()
            note = clean(request.form.get("notes"), 300)
            if not amount or amount <= 0 or method not in PAYMENT_METHODS or method == CREDIT_METHOD:
                flash("Enter an amount and a payment method.", "error")
            elif action == "payment" and amount > inv["total_cents"] - paid:
                flash(f"That's more than the balance ({peso(inv['total_cents'] - paid)}).", "error")
            elif action == "refund" and (amount > paid or not note):
                flash("A refund can't exceed the amount paid, and needs a reason.", "error")
            elif received > today():
                flash("The payment date can't be in the future.", "error")
            else:
                pid = conn.insert("payments", {"invoice_id": invoice_id, "branch_id": inv["branch_id"], "kind": action,
                                               "amount_cents": amount, "method": method, "reference": clean(request.form.get("reference"), 80),
                                               "received_at": received.isoformat(), "received_by": g.user.id, "status": "valid",
                                               "notes": note, "created_at": now_str()})
                audit.record("payment_recorded" if action == "payment" else "refund_recorded", "invoice", invoice_id,
                             f"{'Payment' if action == 'payment' else 'Refund'} {peso(amount)} via {PAYMENT_METHODS[method]}",
                             {"payment_id": pid, "reason": note}, inv["branch_id"])
                flash("Payment recorded." if action == "payment" else "Refund recorded.", "success")
        elif action == "apply_credit":
            amount = parse_money(request.form.get("amount"))
            available = credit_balance(conn, inv["patient_id"])
            balance = inv["total_cents"] - paid
            if not amount or amount <= 0 or amount > min(available, balance):
                flash(f"Enter an amount up to {peso(min(available, balance))} (available credit or bill balance, whichever is lower).", "error")
            else:
                pid = conn.insert("payments", {"invoice_id": invoice_id, "branch_id": inv["branch_id"], "kind": "payment",
                                               "amount_cents": amount, "method": CREDIT_METHOD, "reference": "",
                                               "received_at": today().isoformat(), "received_by": g.user.id, "status": "valid",
                                               "notes": "Paid from account credit", "created_at": now_str()})
                conn.insert("patient_credits", {"patient_id": inv["patient_id"], "branch_id": inv["branch_id"], "kind": "applied",
                                                "amount_cents": amount, "invoice_id": invoice_id, "payment_id": pid,
                                                "entry_date": today().isoformat(), "notes": f"Applied to {inv['number']}",
                                                "created_by": g.user.id, "created_at": now_str()})
                audit.record("credit_applied", "invoice", invoice_id, f"Applied account credit {peso(amount)}", {"payment_id": pid}, inv["branch_id"])
                flash("Account credit applied.", "success")
        elif action == "void_payment":
            pay_id = to_int(request.form.get("payment_id"))
            reason = clean(request.form.get("reason"), 300)
            p = conn.one("SELECT * FROM payments WHERE id = ? AND invoice_id = ? AND status = 'valid'", (pay_id, invoice_id))
            if not p or not reason:
                flash("Choose a payment and give a reason.", "error")
            else:
                conn.execute("UPDATE payments SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                             (reason, g.user.id, now_str(), pay_id))
                # voiding a credit application gives the credit back to the patient
                conn.execute("UPDATE patient_credits SET status = 'void' WHERE payment_id = ? AND kind = 'applied'", (pay_id,))
                audit.record("payment_voided", "invoice", invoice_id, f"Voided {p['kind']} {peso(p['amount_cents'])}",
                             {"payment_id": pay_id, "reason": reason}, inv["branch_id"])
                flash("Payment voided.", "success")
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/void", methods=["POST"])
@require("billing.void")
def invoice_void(invoice_id):
    conn = get_db()
    inv = _load_invoice(invoice_id)
    reason = clean(request.form.get("reason"), 300)
    with conn.transaction(immediate=True):
        if inv["status"] != "issued":
            flash("Only issued invoices can be voided.", "error")
        elif paid_amount(conn, invoice_id) != 0:
            flash("Refund or void the payments first, so the invoice has no net payments.", "error")
        elif not reason:
            flash("Give a reason for voiding.", "error")
        else:
            conn.execute("UPDATE invoices SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                         (reason, g.user.id, now_str(), invoice_id))
            audit.record("invoice_voided", "invoice", invoice_id, f"Voided {inv['number']}", {"reason": reason}, inv["branch_id"])
            flash("Invoice voided. The number stays reserved and appears in reports as void.", "success")
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _report_branches(conn):
    requested = to_int(request.args.get("branch"))
    ids = g.user.scope_branch_ids
    if requested:
        if requested not in g.user.branch_ids:
            abort(403)
        ids = [requested]
    return ids


def _sales_data(conn, ids, start, end):
    marks = ",".join("?" for _ in ids) or "NULL"
    s, e = start.isoformat(), end.isoformat()
    by_branch = []
    for b in conn.all(f"SELECT id, name FROM branches WHERE id IN ({marks}) ORDER BY sort_order", ids):
        sales = conn.one("SELECT COUNT(*) AS n, COALESCE(SUM(total_cents),0) AS total, COALESCE(SUM(discount_cents),0) AS disc, "
                         "COALESCE(SUM(tax_cents),0) AS tax FROM invoices WHERE status='issued' AND branch_id=? AND issued_at BETWEEN ? AND ?",
                         (b["id"], s, e))
        coll = collections(conn, [b["id"]], s, e)
        expenses = conn.scalar("SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE status='posted' AND branch_id=? "
                               "AND expense_date BETWEEN ? AND ?", (b["id"], s, e))
        voids = conn.scalar("SELECT COUNT(*) FROM invoices WHERE status='void' AND branch_id=? AND issued_at BETWEEN ? AND ?", (b["id"], s, e))
        by_branch.append({"branch": b["name"], "invoices": sales["n"], "sales": sales["total"], "discounts": sales["disc"],
                          "tax": sales["tax"], "received": coll["received"], "refunded": coll["refunded"],
                          "collections": coll["net"], "deposits": coll["deposits"], "voids": voids, "expenses": expenses,
                          "net_cash": coll["net"] - expenses})
    methods = conn.all(
        "SELECT method, SUM(amount) AS amount, SUM(n) AS n FROM ("
        f"SELECT method, SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END) AS amount, COUNT(*) AS n FROM payments "
        f"WHERE status='valid' AND method != '{CREDIT_METHOD}' AND branch_id IN ({marks}) AND received_at BETWEEN ? AND ? GROUP BY method "
        "UNION ALL "
        f"SELECT method, SUM(CASE WHEN kind='deposit' THEN amount_cents ELSE -amount_cents END) AS amount, COUNT(*) AS n FROM patient_credits "
        f"WHERE status='valid' AND kind IN ('deposit','refund') AND branch_id IN ({marks}) AND entry_date BETWEEN ? AND ? GROUP BY method"
        ") x GROUP BY method ORDER BY amount DESC", [*ids, s, e, *ids, s, e])
    services_rows = conn.all(
        "SELECT COALESCE(sv.name, 'Other / custom') AS service, COUNT(*) AS lines, SUM(ii.qty) AS qty, SUM(ii.amount_cents) AS amount "
        f"FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN services sv ON sv.id = ii.service_id "
        f"WHERE i.status='issued' AND i.branch_id IN ({marks}) AND i.issued_at BETWEEN ? AND ? GROUP BY COALESCE(sv.name, 'Other / custom') ORDER BY amount DESC",
        [*ids, s, e])
    daily = conn.all(f"SELECT issued_at AS d, SUM(total_cents) AS sales FROM invoices WHERE status='issued' AND branch_id IN ({marks}) "
                     "AND issued_at BETWEEN ? AND ? GROUP BY issued_at ORDER BY issued_at", [*ids, s, e])
    return by_branch, methods, services_rows, daily


def _outstanding(conn, ids):
    marks = ",".join("?" for _ in ids) or "NULL"
    rows = conn.all(
        "SELECT i.id, i.number, i.issued_at, i.total_cents, b.name AS branch, p.id AS patient_id, p.first_name, p.last_name, "
        "(SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END),0) FROM payments WHERE invoice_id=i.id AND status='valid') AS paid "
        f"FROM invoices i JOIN branches b ON b.id = i.branch_id JOIN patients p ON p.id = i.patient_id WHERE i.status='issued' AND i.branch_id IN ({marks}) "
        "ORDER BY i.issued_at", ids)
    out = []
    for r in rows:
        r["balance"] = r["total_cents"] - r["paid"]
        if r["balance"] > 0:
            r["age_days"] = (today() - parse_date(r["issued_at"])).days
            out.append(r)
    return out


@bp.route("/reports/sales")
@require("reports.sales")
def sales():
    conn = get_db()
    start, end = date_range_args(30)
    ids = _report_branches(conn)
    by_branch, methods, services_rows, daily = _sales_data(conn, ids, start, end)
    totals = {k: sum(r[k] for r in by_branch) for k in ("invoices", "sales", "discounts", "tax", "received", "refunded", "collections", "voids",
                                                          "expenses", "net_cash", "deposits")}
    outstanding = _outstanding(conn, ids)
    max_daily = max([d["sales"] for d in daily] + [1])
    return render_template("staff/billing/sales.html", start=start, end=end, by_branch=by_branch, totals=totals, methods=methods,
                           services_rows=services_rows, daily=daily, max_daily=max_daily, outstanding=outstanding,
                           outstanding_total=sum(r["balance"] for r in outstanding), branches=branches_for_user(g.user),
                           branch=to_int(request.args.get("branch")))


@bp.route("/reports/operations")
@require("reports.operations")
def operations():
    conn = get_db()
    start, end = date_range_args(30)
    ids = _report_branches(conn)
    marks = ",".join("?" for _ in ids) or "NULL"
    s, e = start.isoformat(), (end + timedelta(days=1)).isoformat()
    by_status = conn.all(f"SELECT status, COUNT(*) AS n FROM appointments WHERE branch_id IN ({marks}) AND start_at >= ? AND start_at < ? GROUP BY status",
                         [*ids, s, e])
    by_source = conn.all(f"SELECT source, COUNT(*) AS n FROM appointments WHERE branch_id IN ({marks}) AND start_at >= ? AND start_at < ? GROUP BY source ORDER BY n DESC",
                         [*ids, s, e])
    by_service = conn.all(f"SELECT sv.name AS service, COUNT(*) AS n, SUM(CASE WHEN a.status='completed' THEN 1 ELSE 0 END) AS completed "
                          f"FROM appointments a JOIN services sv ON sv.id = a.service_id WHERE a.branch_id IN ({marks}) AND a.start_at >= ? AND a.start_at < ? "
                          "GROUP BY sv.name ORDER BY n DESC", [*ids, s, e])
    by_dentist = conn.all(f"SELECT COALESCE(u.name, 'Unassigned') AS dentist, COUNT(*) AS n, SUM(CASE WHEN a.status='completed' THEN 1 ELSE 0 END) AS completed, "
                          "SUM(CASE WHEN a.status='no_show' THEN 1 ELSE 0 END) AS no_show "
                          f"FROM appointments a LEFT JOIN users u ON u.id = a.dentist_id WHERE a.branch_id IN ({marks}) AND a.start_at >= ? AND a.start_at < ? "
                          "GROUP BY COALESCE(u.name, 'Unassigned') ORDER BY n DESC", [*ids, s, e])
    by_branch = conn.all(f"SELECT b.name AS branch, COUNT(a.id) AS n, SUM(CASE WHEN a.status='completed' THEN 1 ELSE 0 END) AS completed, "
                         "COUNT(DISTINCT CASE WHEN a.status='completed' THEN a.patient_id END) AS patients "
                         f"FROM branches b LEFT JOIN appointments a ON a.branch_id = b.id AND a.start_at >= ? AND a.start_at < ? "
                         f"WHERE b.id IN ({marks}) GROUP BY b.name, b.sort_order ORDER BY b.sort_order", [s, e, *ids])
    leads = conn.all(f"SELECT source, COUNT(*) AS n, SUM(CASE WHEN status IN ('booked','converted') THEN 1 ELSE 0 END) AS won "
                     f"FROM leads WHERE (branch_id IN ({marks}) OR branch_id IS NULL) AND created_at >= ? AND created_at < ? GROUP BY source ORDER BY n DESC",
                     [*ids, s, e])
    new_patients = conn.scalar(f"SELECT COUNT(*) FROM patients WHERE preferred_branch_id IN ({marks}) AND created_at >= ? AND created_at < ?", [*ids, s, e])
    requests_ = conn.all(f"SELECT status, COUNT(*) AS n FROM booking_requests WHERE branch_id IN ({marks}) AND created_at >= ? AND created_at < ? GROUP BY status",
                         [*ids, s, e])
    return render_template("staff/billing/operations.html", start=start, end=end, by_status=by_status, by_source=by_source,
                           by_service=by_service, by_dentist=by_dentist, by_branch=by_branch, leads=leads,
                           new_patients=new_patients, requests_=requests_, branches=branches_for_user(g.user),
                           branch=to_int(request.args.get("branch")))


@bp.route("/reports/export/<kind>.csv")
@require("reports.export")
def export(kind):
    conn = get_db()
    start, end = date_range_args(30)
    ids = _report_branches(conn)
    buf = io.StringIO()
    w = csv.writer(buf)
    if kind == "sales":
        if not g.user.can("reports.sales"):
            abort(403)
        by_branch, _m, _s, _d = _sales_data(conn, ids, start, end)
        w.writerow(["Branch", "Invoices issued", "Sales (PHP)", "Discounts (PHP)", "Tax (PHP)", "Money received incl. deposits (PHP)",
                    "Refunds (PHP)", "Net collections (PHP)", "Posted expenses (PHP)", "Collections less expenses (PHP)",
                    "Voided invoices", "From", "To"])
        for r in by_branch:
            w.writerow([r["branch"], r["invoices"], r["sales"] / 100, r["discounts"] / 100, r["tax"] / 100, r["received"] / 100,
                        r["refunded"] / 100, r["collections"] / 100, r["expenses"] / 100, r["net_cash"] / 100, r["voids"],
                        start.isoformat(), end.isoformat()])
    elif kind == "services":
        if not g.user.can("reports.sales"):
            abort(403)
        _b, _m, services_rows, _d = _sales_data(conn, ids, start, end)
        w.writerow(["Service", "Invoice lines", "Quantity", "Sales (PHP)", "From", "To"])
        for r in services_rows:
            w.writerow([r["service"], r["lines"], r["qty"], r["amount"] / 100, start.isoformat(), end.isoformat()])
    elif kind == "outstanding":
        if not g.user.can("reports.sales"):
            abort(403)
        w.writerow(["Invoice", "Issued", "Branch", "Patient", "Total (PHP)", "Paid (PHP)", "Balance (PHP)", "Age (days)"])
        for r in _outstanding(conn, ids):
            w.writerow([r["number"], r["issued_at"], r["branch"], f"{r['last_name']}, {r['first_name']}", r["total_cents"] / 100,
                        r["paid"] / 100, r["balance"] / 100, r["age_days"]])
    elif kind == "payments":
        if not g.user.can("reports.sales"):
            abort(403)
        marks = ",".join("?" for _ in ids) or "NULL"
        rows = conn.all(f"SELECT p.*, i.number, b.name AS branch FROM payments p JOIN invoices i ON i.id = p.invoice_id JOIN branches b ON b.id = p.branch_id "
                        f"WHERE p.branch_id IN ({marks}) AND p.received_at BETWEEN ? AND ? ORDER BY p.received_at, p.id",
                        [*ids, start.isoformat(), end.isoformat()])
        w.writerow(["Date", "Branch", "Invoice", "Type", "Method", "Reference", "Amount (PHP)", "Status", "Void reason"])
        for r in rows:
            w.writerow([r["received_at"], r["branch"], r["number"], r["kind"], PAYMENT_METHODS.get(r["method"], r["method"]),
                        r["reference"], (r["amount_cents"] if r["kind"] == "payment" else -r["amount_cents"]) / 100, r["status"], r["void_reason"]])
    elif kind == "appointments":
        if not g.user.can("reports.operations"):
            abort(403)
        marks = ",".join("?" for _ in ids) or "NULL"
        rows = conn.all(f"SELECT a.start_at, a.status, a.source, b.name AS branch, s.name AS service, u.name AS dentist FROM appointments a "
                        f"JOIN branches b ON b.id = a.branch_id JOIN services s ON s.id = a.service_id LEFT JOIN users u ON u.id = a.dentist_id "
                        f"WHERE a.branch_id IN ({marks}) AND a.start_at >= ? AND a.start_at < ? ORDER BY a.start_at",
                        [*ids, start.isoformat(), (end + timedelta(days=1)).isoformat()])
        w.writerow(["Start", "Branch", "Service", "Dentist", "Source", "Status"])  # no patient identifiers in operational export
        for r in rows:
            w.writerow([r["start_at"], r["branch"], r["service"], r["dentist"] or "", r["source"], r["status"]])
    else:
        abort(404)
    audit.record("report_exported", "report", None, f"Exported {kind} CSV", {"from": start.isoformat(), "to": end.isoformat(), "branches": ids})
    filename = f"dental-haven-{kind}-{start.isoformat()}-to-{end.isoformat()}.csv"
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Account credit (patient deposits / advance payments)
# ---------------------------------------------------------------------------

@bp.route("/patients/<int:patient_id>/credit", methods=["POST"])
@require("billing.view")
def patient_credit(patient_id):
    conn = get_db()
    if not can_see_patient(conn, g.user, patient_id):
        abort(403)
    action = request.form.get("action", "deposit")
    if (action == "deposit" and not g.user.can("payments.add")) or (action == "refund" and not g.user.can("billing.void")) \
            or action not in ("deposit", "refund"):
        abort(403)
    amount = parse_money(request.form.get("amount"))
    branch_id = to_int(request.form.get("branch_id"))
    method = request.form.get("method")
    entry = parse_date(request.form.get("entry_date")) or today()
    note = clean(request.form.get("notes"), 300)
    back = redirect(url_for("patients.detail", patient_id=patient_id) + "#billing")
    if not branch_id or not g.user.in_branch(branch_id):
        flash("Choose one of your branches.", "error")
        return back
    if not amount or amount <= 0 or method not in PAYMENT_METHODS or entry > today():
        flash("Enter an amount, a payment method and a date that isn't in the future.", "error")
        return back
    with conn.transaction(immediate=True):
        if action == "refund":
            if amount > credit_balance(conn, patient_id) or not note:
                flash("A refund can't exceed the patient's credit, and needs a reason.", "error")
                return back
        cid = conn.insert("patient_credits", {"patient_id": patient_id, "branch_id": branch_id, "kind": action, "amount_cents": amount,
                                              "method": method, "reference": clean(request.form.get("reference"), 80),
                                              "entry_date": entry.isoformat(), "notes": note, "created_by": g.user.id,
                                              "created_at": now_str()})
        audit.record("credit_" + action, "patient", patient_id, f"Account credit {action} {peso(amount)} via {PAYMENT_METHODS[method]}",
                     {"credit_id": cid, "reason": note}, branch_id)
    flash("Deposit recorded as account credit." if action == "deposit" else "Credit refund recorded.", "success")
    return back

"""Invoices, payments, refunds/voids and sales, collections and operations reports (with CSV export)."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, settings
from ..auth import require
from ..billing import (CREDIT_METHOD, PAYMENT_METHODS, parse_pay, pay_label, collections, commission_dentists, compute_totals, credit_balance,
                       invoice_commission_info, lab_share, line_amount, next_invoice_number, paid_amount, payment_state)
from ..db import get_db
from ..fee_schedule import picker_options
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


def _received_branch(inv) -> int:
    """The branch where the money was received (the cashier picks it; a patient from Malolos may pay at Guiguinto).
    Collections, the daily report and deposits count the payment there. Default: the cashier's selected branch, else the
    bill's branch."""
    bid = to_int(request.form.get("received_branch_id"))
    if bid and g.user.in_branch(bid):
        return bid
    return inv["branch_id"]


def _my_pay_branches():
    from .common import branches_for_user
    return branches_for_user(g.user) if getattr(g, "user", None) else []


@bp.app_context_processor
def _ctx():
    from ..billing import pay_label, pay_options
    return {"PAYMENT_METHODS": PAYMENT_METHODS, "PAYMENT_LABELS": {**PAYMENT_METHODS, CREDIT_METHOD: "Account credit"},
            "pay_options": pay_options, "pay_label": pay_label, "my_pay_branches": _my_pay_branches}


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
    from .patients import notes_to_bill
    to_bill = notes_to_bill(conn, g.user.scope_branch_ids)
    return render_template("staff/billing/invoices.html", rows=rows, pg=pg, start=start, end=end, status=status, to_bill=to_bill)


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
                                                  "qty": 1, "unit_price_cents": price, "discount_cents": 0, "amount_cents": price,
                                                  "dentist_id": appt["dentist_id"], "done_on": appt["start_at"][:10]})
                _recalc(conn, inv_id)
                audit.record("invoice_created", "invoice", inv_id, "Draft invoice created", branch_id=branch_id)
            return redirect(url_for("billing.invoice", invoice_id=inv_id))
    return render_template("staff/billing/invoice_new.html", patient=patient, appt=appt, branch_id=branch_id,
                           branches=branches_for_user(g.user))


@bp.route("/invoices/<int:invoice_id>/payments/<int:payment_id>/branch", methods=["POST"])
@require("bills.edit")
def payment_branch(invoice_id, payment_id):
    """Correct the branch a payment was received at (it counts in that branch's collections, daily report and deposits)."""
    conn = get_db()
    inv = _load_invoice(invoice_id)
    p = conn.one("SELECT p.*, b.name AS branch_name FROM payments p LEFT JOIN branches b ON b.id = p.branch_id "
                 "WHERE p.id = ? AND p.invoice_id = ? AND p.status = 'valid'", (payment_id, invoice_id))
    if not p or p["method"] == CREDIT_METHOD:
        abort(404)
    bid = to_int(request.form.get("branch_id"))
    if not bid or not g.user.in_branch(bid) or (p["branch_id"] and not g.user.in_branch(p["branch_id"])):
        abort(403)
    if bid != p["branch_id"]:
        conn.execute("UPDATE payments SET branch_id = ? WHERE id = ?", (bid, payment_id))
        name = conn.scalar("SELECT name FROM branches WHERE id = ?", (bid,))
        audit.record("payment_branch_changed", "invoice", invoice_id,
                     f"Payment {peso(p['amount_cents'])} on {(p['received_at'] or '')[:10]}: received at {name} (was {p['branch_name']})",
                     {"payment_id": payment_id}, bid)
        flash(f"The payment now counts in {name}'s collections for {(p['received_at'] or '')[:10]}.", "success")
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/branch", methods=["POST"])
@require("bills.edit")
def invoice_branch(invoice_id):
    """Move a bill to another branch (e.g. the work was done at Guiguinto but the bill was made under Malolos), while it
    has no payments. The bill number stays."""
    conn = get_db()
    inv = _load_invoice(invoice_id)
    bid = to_int(request.form.get("branch_id"))
    back = redirect(url_for("billing.invoice", invoice_id=invoice_id))
    if inv["status"] == "void" or not bid or bid == inv["branch_id"] or not g.user.in_branch(bid):
        flash("Choose one of your branches.", "error")
        return back
    if conn.scalar("SELECT COUNT(*) FROM payments WHERE invoice_id = ? AND status = 'valid'", (invoice_id,)):
        flash("This bill has payments, so it stays at its branch. Record new payments with “Received at” set to the branch "
              "that got the money.", "error")
        return back
    conn.execute("UPDATE invoices SET branch_id = ? WHERE id = ?", (bid, invoice_id))
    name = conn.scalar("SELECT name FROM branches WHERE id = ?", (bid,))
    audit.record("invoice_branch_changed", "invoice", invoice_id, f"Bill moved from {inv['branch']} to {name}", branch_id=bid)
    flash(f"Bill moved to {name}.", "success")
    return back


@bp.route("/invoices/<int:invoice_id>/discount", methods=["POST"])
@require("bills.edit")
def issued_discount(invoice_id):
    """Discount on an issued bill (e.g. senior citizen/PWD, promo): an amount or a % of the bill, with a reason. The bill's
    total can't go below what's already paid. Replaces the bill's earlier discount; recorded in the bill's history."""
    conn = get_db()
    inv = _load_invoice(invoice_id)
    back = url_for("billing.invoice", invoice_id=invoice_id)
    if inv["status"] != "issued":
        flash("Only issued bills here; on a draft, use Invoice discount.", "error")
        return redirect(back)
    raw = (request.form.get("value") or "").strip().rstrip("%")
    reason = clean(request.form.get("reason"), 300)
    sub_total = inv["subtotal_cents"]
    if request.form.get("kind") == "percent":
        try:
            pct = float(raw)
        except ValueError:
            pct = -1
        disc = round(sub_total * pct / 100) if 0 <= pct <= 100 else None
    else:
        disc = parse_money(raw) if raw else 0
    paid = paid_amount(conn, invoice_id)
    if disc is None or disc < 0 or disc > sub_total:
        flash("Enter a discount between 0 and the bill's subtotal (or 0–100%).", "error")
    elif len(reason) < 3:
        flash("Write the reason for the discount (e.g. Senior citizen, ID checked).", "error")
    elif compute_totals(conn.all("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,)), disc, conn)["total_cents"] < paid:
        flash(f"With this discount the bill would be less than what's already paid ({peso(paid)}). Refund or void a payment first.", "error")
    else:
        conn.execute("UPDATE invoices SET discount_cents = ? WHERE id = ?", (disc, invoice_id))
        _recalc(conn, invoice_id)
        if reason and reason not in (inv["notes"] or ""):
            conn.execute("UPDATE invoices SET notes = ? WHERE id = ?", ((f"{inv['notes']} · " if inv["notes"] else "") + f"Discount: {reason}"[:500],
                                                                       invoice_id))
        audit.record("invoice_discount", "invoice", invoice_id, f"Discount {peso(disc)} on issued bill (was {peso(inv['discount_cents'] or 0)})",
                     {"reason": reason}, inv["branch_id"])
        flash(f"Discount of {peso(disc)} applied." if disc else "Discount removed.", "success")
    return redirect(back)


@bp.route("/invoices/<int:invoice_id>/mymeds-paid", methods=["POST"])
@require("billing.void")
def mymeds_paid(invoice_id):
    """An imported MyMedsPH bill that MyMedsPH shows as paid but isn't paid here: record the payment as "Paid in MyMedsPH",
    dated on the bill date, so it doesn't count as money received today (daily collection, deposits). Void it like any
    payment. Billing report uploads count it as already paid."""
    import secrets
    from ..billing import LEGACY_METHOD
    conn = get_db()
    inv = _load_invoice(invoice_id)
    bal = inv["total_cents"] - paid_amount(conn, invoice_id)
    amt = parse_money(request.form.get("amount"))
    if not inv["legacy"] or inv["status"] != "issued":
        abort(404)
    if not amt or amt <= 0 or amt > bal:
        flash(f"Enter an amount up to the balance ({bal / 100:,.2f}).", "error")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id))
    day = (inv["issued_at"] or inv["created_at"])[:10]
    pid = conn.insert("payments", {"invoice_id": invoice_id, "branch_id": inv["branch_id"], "kind": "payment", "amount_cents": amt,
                                   "method": LEGACY_METHOD, "account": "", "reference": clean(request.form.get("reference"), 80),
                                   "received_at": f"{day} 12:00:00", "received_by": g.user.id, "status": "valid",
                                   "notes": "Paid in MyMedsPH (marked by staff)", "created_at": now_str(),
                                   "legacy_key": f"mmm:{invoice_id}:{secrets.token_hex(4)}"})
    audit.record("payment_mymeds_marked", "invoice", invoice_id, f"Marked {amt / 100:,.2f} as paid in MyMedsPH", {"payment": pid},
                 inv["branch_id"])
    flash("Recorded as paid in MyMedsPH, on the bill date (not in today's collections).", "success")
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>")
@require("billing.view")
def invoice(invoice_id):
    conn = get_db()
    inv = _load_invoice(invoice_id)
    items = conn.all("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,))
    payments = conn.all("SELECT p.*, u.name AS received_by_name, v.name AS voided_by_name, pb.name AS branch_name FROM payments p "
                        "LEFT JOIN users u ON u.id = p.received_by LEFT JOIN users v ON v.id = p.voided_by LEFT JOIN branches pb ON pb.id = p.branch_id "
                        "WHERE p.invoice_id = ? ORDER BY p.id", (invoice_id,))
    paid = paid_amount(conn, invoice_id)
    history = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                       "WHERE a.entity_type = 'invoice' AND a.entity_id = ? ORDER BY a.id DESC", (invoice_id,))
    appt = conn.one("SELECT dentist_id, start_at FROM appointments WHERE id = ?", (inv["appointment_id"],)) if inv["appointment_id"] else None
    inv_dentists = conn.all("SELECT u.id, u.name FROM users u JOIN user_branches ub ON ub.user_id = u.id WHERE u.role = 'dentist' AND u.active = 1 "
                            "AND ub.branch_id = ? ORDER BY u.name", (inv["branch_id"],))
    lab_cases = conn.all("SELECT id, case_type, teeth, lab_fee_cents, sent_on FROM lab_cases WHERE patient_id = ? AND status != 'cancelled' "
                         "ORDER BY id DESC LIMIT 20", (inv["patient_id"],))
    dentist_names = {d["id"]: d["name"] for d in conn.all("SELECT id, name FROM users WHERE role = 'dentist'")}
    manual_comm = conn.all("SELECT c.*, e.full_name AS dentist, u.name AS by_name FROM dentist_commissions c JOIN employees e ON e.id = c.employee_id "
                           "LEFT JOIN users u ON u.id = c.created_by WHERE c.invoice_id = ? AND c.status = 'valid' ORDER BY c.earned_on, c.id",
                           (invoice_id,))
    return render_template("staff/billing/invoice.html", inv=inv, items=items, payments=payments, paid=paid, inv_dentists=inv_dentists,
                           manual_comm=manual_comm, comm_dentists=commission_dentists(conn), comm_info=invoice_commission_info(conn, inv),
                           fee_options=picker_options(conn) if inv["status"] == "draft" else [],
                           lab_cases=lab_cases, dentist_names=dentist_names, default_dentist=appt["dentist_id"] if appt else None,
                           default_done=(appt["start_at"][:10] if appt else today().isoformat()),
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
    pays = conn.all("SELECT p.*, s.stored_name AS sig, s.not_signed_reason FROM payments p LEFT JOIN payment_signatures s ON s.id = p.signature_id "
                    "WHERE p.invoice_id = ? AND p.status = 'valid' ORDER BY p.received_at, p.id", (invoice_id,))
    return render_template("staff/billing/invoice_print.html", inv=inv, items=items, paid=paid, pays=pays,
                           balance=inv["total_cents"] - paid, tax_label=settings.get("invoice.tax_label"),
                           tax_enabled=settings.get("invoice.tax_enabled"), tax_inclusive=settings.get("invoice.tax_inclusive"))


def _commission_fields(conn, inv, form):
    """Dentist, date done and lab fee for a procedure line (used for dentist commission)."""
    dentist_id = to_int(form.get("dentist_id"))
    if dentist_id and not conn.one("SELECT id FROM users WHERE id = ? AND role = 'dentist'", (dentist_id,)):
        dentist_id = None
    done = parse_date(form.get("done_on"))
    if done and done > today():
        done = today()
    lab_case_id = to_int(form.get("lab_case_id"))
    lab_case = conn.one("SELECT * FROM lab_cases WHERE id = ? AND patient_id = ?", (lab_case_id, inv["patient_id"])) if lab_case_id else None
    fee = parse_money(form.get("lab_fee")) if form.get("lab_fee") else None
    if fee is None and lab_case and lab_case["lab_fee_cents"]:
        fee = lab_case["lab_fee_cents"]
    out = {"dentist_id": dentist_id, "done_on": (done or today()).isoformat() if dentist_id else (done.isoformat() if done else None),
           "lab_fee_cents": max(0, fee or 0), "lab_case_id": lab_case["id"] if lab_case else None}
    mode = form.get("commission_mode")
    if mode in ("auto", "percent", "amount"):
        out.update(commission_mode="auto", commission_bp=None, commission_cents=None)
        if mode == "percent":
            bp = pct_to_bp(form.get("commission_pct"))
            if bp is not None:
                out.update(commission_mode="percent", commission_bp=bp)
        elif mode == "amount":
            amt = parse_money(form.get("commission_amount")) if (form.get("commission_amount") or "").strip() else None
            if amt is not None and amt >= 0:
                out.update(commission_mode="amount", commission_cents=amt)
    return out


def pct_to_bp(text):
    t = (text or "").strip().rstrip("%")
    try:
        v = round(float(t) * 100)
    except ValueError:
        return None
    return v if 0 <= v <= 10000 else None


EDIT_ACTION_PERMS = {"add_item": "billing.manage", "issue": "billing.manage", "delete": "billing.manage",
                     "remove_item": "bills.edit", "discount": "bills.edit", "commission": "bills.edit"}


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
    if inv["status"] == "void" and action == "commission":
        flash("This invoice is void.", "error")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id))
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
                extra = _commission_fields(conn, inv, request.form)
                conn.insert("invoice_items", {"invoice_id": invoice_id, "service_id": svc_id, "description": desc, "qty": qty,
                                              "tooth": clean(request.form.get("tooth"), 40),
                                              "unit_price_cents": unit, "discount_cents": min(disc, qty * unit), "amount_cents": amount, **extra})
                audit.record("invoice_item_added", "invoice", invoice_id, f"Added {desc} {peso(amount)}", branch_id=inv["branch_id"])
        elif action == "commission":
            item = conn.one("SELECT * FROM invoice_items WHERE id = ? AND invoice_id = ?", (to_int(request.form.get("item_id")), invoice_id))
            if item:
                extra = _commission_fields(conn, inv, request.form)
                if request.form.get("commission_mode") in ("percent", "amount") and extra.get("commission_mode") != request.form.get("commission_mode"):
                    flash("Enter the commission % (0–100) or the commission amount, e.g. 500 or 500.00.", "error")
                    return redirect(url_for("billing.invoice", invoice_id=invoice_id))
                conn.execute("UPDATE invoice_items SET dentist_id = ?, done_on = ?, lab_fee_cents = ?, lab_case_id = ?, "
                             "commission_mode = ?, commission_bp = ?, commission_cents = ?, legacy_dentist = 0 WHERE id = ?",
                             (extra["dentist_id"], extra["done_on"], extra["lab_fee_cents"], extra["lab_case_id"],
                              extra.get("commission_mode", item["commission_mode"]), extra.get("commission_bp", item["commission_bp"]),
                              extra.get("commission_cents", item["commission_cents"]), item["id"]))
                keys = ("dentist_id", "done_on", "lab_fee_cents", "commission_mode", "commission_bp", "commission_cents")
                audit.record("invoice_item_commission", "invoice", invoice_id, f"Dentist / date done / lab fee / commission set on '{item['description']}'",
                             {"before": {k: item[k] for k in keys}, "after": extra}, inv["branch_id"])
                flash("Saved. Dentist payroll uses this line from the date done.", "success")
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
                flash("Add at least one item (a service or procedure) with the Add button below before issuing the invoice.", "error")
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
    back = request.form.get("next") or ""
    if action == "remove_item" and back.startswith(f"/staff/patients/{inv['patient_id']}") and "//" not in back:
        flash("Item removed from the draft invoice.", "success")
        return redirect(back)
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


PAYMENT_ACTION_PERMS = {"payment": "payments.add", "multi": "payments.add", "refund": "billing.void", "void_payment": "billing.void",
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
            pm = parse_pay(request.form.get("method"), conn)
            method, account = pm or ("", "")
            received = parse_date(request.form.get("received_at")) or today()
            note = clean(request.form.get("notes"), 300)
            if not amount or amount <= 0 or not pm:
                flash("Enter an amount and a payment method.", "error")
            elif action == "payment" and amount > inv["total_cents"] - paid:
                flash(f"That's more than the balance ({peso(inv['total_cents'] - paid)}).", "error")
            elif action == "refund" and (amount > paid or not note):
                flash("A refund can't exceed the amount paid, and needs a reason.", "error")
            elif received > today():
                flash("The payment date can't be in the future.", "error")
            else:
                pid = conn.insert("payments", {"invoice_id": invoice_id, "branch_id": _received_branch(inv), "kind": action,
                                               "amount_cents": amount, "method": method, "account": account,
                                               "reference": clean(request.form.get("reference"), 80),
                                               "received_at": received.isoformat(), "received_by": g.user.id, "status": "valid",
                                               "notes": note, "created_at": now_str()})
                audit.record("payment_recorded" if action == "payment" else "refund_recorded", "invoice", invoice_id,
                             f"{'Payment' if action == 'payment' else 'Refund'} {peso(amount)} via {pay_label(method, account)}",
                             {"payment_id": pid, "reason": note}, inv["branch_id"])
                flash("Payment recorded." if action == "payment" else "Refund recorded.", "success")
        elif action == "multi":
            err = _multi_payment(conn, inv, paid)
            if err:
                flash(err, "error")
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
                # a voided payment earns no commission
                conn.execute("UPDATE dentist_commissions SET status = 'void', voided_by = ?, voided_at = ? WHERE payment_id = ? AND status = 'valid'",
                             (g.user.id, now_str(), pay_id))
                audit.record("payment_voided", "invoice", invoice_id, f"Voided {p['kind']} {peso(p['amount_cents'])}",
                             {"payment_id": pay_id, "reason": reason}, inv["branch_id"])
                flash("Payment voided.", "success")
    if request.form.get("return_to") == "patient":
        return redirect(url_for("patients.detail", patient_id=inv["patient_id"], tab="billing"))
    return redirect(url_for("billing.invoice", invoice_id=invoice_id))


def _multi_payment(conn, inv, paid):
    """Several payment lines (e.g. part cash, part GCash) saved together with the patient's signature."""
    from ..uploads import save_signature
    methods, amounts = request.form.getlist("method"), request.form.getlist("amount")
    lines = []
    for m, a in zip(methods, amounts):
        if not (a or "").strip():
            continue
        amt = parse_money(a)
        pm = parse_pay(m, conn)
        if not amt or amt <= 0 or not pm:
            return "Each payment line needs a payment type and an amount like 1500 or 1500.00."
        lines.append((pm, amt))
    if not lines:
        return "Add at least one payment line with an amount."
    total = sum(a for _m, a in lines)
    if total > inv["total_cents"] - paid:
        return f"That's more than the balance ({peso(inv['total_cents'] - paid)})."
    received = parse_date(request.form.get("received_at")) or today()
    if received > today():
        return "The payment date can't be in the future."
    reason = clean(request.form.get("not_signed_reason"), 200)
    stored = ""
    data_url = request.form.get("signature") or ""
    if data_url:
        stored, err = save_signature(data_url)
        if err:
            return err
    elif not reason:
        return "Ask the patient to sign, or tick 'Patient can't sign' and give the reason."
    comm = None
    comm_dentist = to_int(request.form.get("comm_dentist_id"))
    if comm_dentist:
        if not (g.user.can("commission.record") or g.user.can("bills.edit")):
            abort(403)
        emp = conn.one("SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id WHERE u.id = ? AND u.role = 'dentist'", (comm_dentist,))
        if not emp:
            return "That dentist has no employee record yet (Staff & payroll → Employees), so commission can't be recorded."
        mode = request.form.get("comm_mode") or ("amount" if (request.form.get("comm_amount") or "").strip() else "percent")
        info = invoice_commission_info(conn, inv)
        base = total - lab_share(total, info["lab_fee_cents"], inv["total_cents"])
        if mode == "amount":
            amt = parse_money(request.form.get("comm_amount")) if (request.form.get("comm_amount") or "").strip() else None
            if amt is None or amt < 0:
                return "Enter the dentist's commission amount, e.g. 600 or 600.00, or choose “No commission”."
            if amt > total:
                return "The commission can't be more than the payment."
            comm = {"employee_id": emp["id"], "amount": amt, "bp": None, "base": base}
        else:
            bp = pct_to_bp(request.form.get("comm_pct"))
            if bp is None:
                return "Enter the dentist's commission % (0–100), or choose “No commission”."
            comm = {"employee_id": emp["id"], "amount": None, "bp": bp, "base": base}
    sig_id = conn.insert("payment_signatures", {"invoice_id": inv["id"], "patient_id": inv["patient_id"], "stored_name": stored,
                                                "not_signed_reason": "" if stored else reason, "captured_by": g.user.id,
                                                "created_at": now_str()})
    ref, note = clean(request.form.get("reference"), 80), clean(request.form.get("notes"), 300)
    at_branch = _received_branch(inv)
    for (m, account), amt in lines:
        pid = conn.insert("payments", {"invoice_id": inv["id"], "branch_id": at_branch, "kind": "payment", "amount_cents": amt,
                                       "method": m, "account": account, "reference": ref, "received_at": received.isoformat(), "received_by": g.user.id,
                                       "status": "valid", "notes": note, "signature_id": sig_id, "created_at": now_str()})
        audit.record("payment_recorded", "invoice", inv["id"], f"Payment {peso(amt)} via {pay_label(m, account)}",
                     {"payment_id": pid, "signed": bool(stored)}, inv["branch_id"])
    comm_note = ""
    if comm:
        from ..payroll import add_manual_commission
        _cid, err = add_manual_commission(conn, None, comm["employee_id"], received, comm["base"], comm["bp"], comm["amount"], g.user.id,
                                          invoice_id=inv["id"], payment_id=pid,
                                          description=clean(request.form.get("comm_desc"), 200) or f"Payment on {inv['number']}")
        comm_note = " Dentist commission recorded." if not err else f" Commission not recorded: {err}"
    flash(f"Payment of {peso(total)} recorded" + (" with the patient's signature." if stored else ".") + comm_note, "success")
    return None


@bp.route("/invoices/<int:invoice_id>/dentist-commission", methods=["POST"])
@require("commission.record", "bills.edit", any_of=True)
def dentist_commission(invoice_id):
    """Manual dentist commission linked to this bill, e.g. for each ortho adjustment the patient pays for."""
    from ..payroll import add_manual_commission
    conn = get_db()
    inv = _load_invoice(invoice_id)
    if request.form.get("action") == "void":
        c = conn.one("SELECT * FROM dentist_commissions WHERE id = ? AND invoice_id = ? AND status = 'valid'",
                     (to_int(request.form.get("commission_id")), invoice_id))
        if not c:
            abort(404)
        conn.execute("UPDATE dentist_commissions SET status = 'void', voided_by = ?, voided_at = ? WHERE id = ?", (g.user.id, now_str(), c["id"]))
        audit.record("dentist_commission_voided", "invoice", invoice_id, f"Removed manual dentist commission {peso(c['amount_cents'])}",
                     {"commission_id": c["id"]}, inv["branch_id"])
        flash("Commission removed.", "success")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id) + "#dentist-commission")
    if inv["status"] != "issued":
        flash("Add manual commission on an issued bill.", "error")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id))
    earned = parse_date(request.form.get("earned_on")) or today()
    amt_txt, base_txt, pct_txt = ((request.form.get(k) or "").strip() for k in ("amount", "base", "pct"))
    pay = None
    if request.form.get("payment_id"):
        # commission on one payment row: base = that payment, dated on the payment date
        pay = conn.one("SELECT * FROM payments WHERE id = ? AND invoice_id = ? AND status = 'valid' AND kind = 'payment'",
                       (to_int(request.form.get("payment_id")), invoice_id))
        if not pay:
            abort(404)
        if conn.one("SELECT id FROM dentist_commissions WHERE payment_id = ? AND status = 'valid'", (pay["id"],)):
            flash("This payment already has a dentist commission. Remove it first to change it.", "error")
            return redirect(url_for("billing.invoice", invoice_id=invoice_id))
        earned = parse_date(pay["received_at"])
        info = invoice_commission_info(conn, inv)
        base_txt = "%.2f" % ((pay["amount_cents"] - lab_share(pay["amount_cents"], info["lab_fee_cents"], inv["total_cents"])) / 100)
        if not amt_txt and not pct_txt:
            flash("Enter a % of the payment or an amount.", "error")
            return redirect(url_for("billing.invoice", invoice_id=invoice_id))
    amount = parse_money(amt_txt) if amt_txt else None
    base = parse_money(base_txt) if base_txt else None
    bp = pct_to_bp(pct_txt) if pct_txt else None
    if earned > today() or (amt_txt and amount is None) or (base_txt and base is None) or (pct_txt and bp is None):
        flash("Check the date (not in the future), amounts (e.g. 1500 or 1500.00) and % (0–100).", "error")
        return redirect(url_for("billing.invoice", invoice_id=invoice_id) + "#dentist-commission")
    desc = clean(request.form.get("description"), 200) or ((pay["notes"] or f"Payment {PAYMENT_METHODS.get(pay['method'], pay['method'])}") if pay else "")
    cid, err = add_manual_commission(conn, to_int(request.form.get("dentist_id")), None, earned, base, bp, amount, g.user.id,
                                     invoice_id=invoice_id, payment_id=pay["id"] if pay else None, description=desc)
    if err:
        flash(err, "error")
    else:
        c = conn.one("SELECT amount_cents FROM dentist_commissions WHERE id = ?", (cid,))
        audit.record("dentist_commission_added", "invoice", invoice_id, f"Manual dentist commission {peso(c['amount_cents'])} for {earned.isoformat()}",
                     {"commission_id": cid}, inv["branch_id"])
        flash(f"Commission of {peso(c['amount_cents'])} recorded. It counts in the payroll cutoff that includes {earned.isoformat()}.", "success")
    return redirect(url_for("billing.invoice", invoice_id=invoice_id) + "#dentist-commission")


@bp.route("/invoices/<int:invoice_id>/signatures/<int:sig_id>")
@require("billing.view")
def signature(invoice_id, sig_id):
    from flask import send_file
    from ..uploads import document_path
    _load_invoice(invoice_id)
    s = get_db().one("SELECT * FROM payment_signatures WHERE id = ? AND invoice_id = ?", (sig_id, invoice_id))
    if not s or not s["stored_name"]:
        abort(404)
    resp = send_file(document_path(s["stored_name"]), mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


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


def collections_by_service(conn, ids, start, end) -> list[dict]:
    """Money received in the period by type of service: each payment (or refund) is shared over its bill's lines in
    proportion to their amounts, by the date received, so braces installments paid this month count under Orthodontics
    even if the bill is from an earlier year. Deposits not yet applied to a bill are their own row."""
    from ..case_types import Classifier
    marks = ",".join("?" for _ in ids) or "NULL"
    s, e = start.isoformat(), end.isoformat()
    pays = {r["invoice_id"]: r["amt"] for r in conn.all(
        "SELECT invoice_id, SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END) AS amt FROM payments "
        f"WHERE status = 'valid' AND method != '{CREDIT_METHOD}' AND branch_id IN ({marks}) AND substr(received_at, 1, 10) BETWEEN ? AND ? "
        "GROUP BY invoice_id", [*ids, s, e])}
    kind = Classifier(conn)
    out: dict[str, dict] = {}
    inv_ids = list(pays)
    lines: dict[int, list] = {}
    for i in range(0, len(inv_ids), 500):
        chunk = inv_ids[i:i + 500]
        for ln in conn.all(f"SELECT ii.invoice_id, ii.amount_cents, ii.description, sv.category AS scat, u.name AS dentist FROM invoice_items ii "
                           f"LEFT JOIN services sv ON sv.id = ii.service_id LEFT JOIN users u ON u.id = ii.dentist_id "
                           f"WHERE ii.invoice_id IN ({','.join('?' * len(chunk))})", chunk):
            lines.setdefault(ln["invoice_id"], []).append(ln)
    docs: dict[str, dict] = {}
    for inv, amt in pays.items():
        ls = lines.get(inv) or []
        tot = sum(max(0, l["amount_cents"]) for l in ls)
        if not tot:
            for bucket, key in ((out, "Other"), (docs, "No dentist set")):
                r = bucket.setdefault(key, {"service": key, "amount": 0, "bills": set()})
                r["amount"] += amt
                r["bills"].add(inv)
            continue
        for l in ls:
            part = round(amt * max(0, l["amount_cents"]) / tot)
            for bucket, key in ((out, kind(l["description"], l["scat"])), (docs, l["dentist"] or "No dentist set")):
                r = bucket.setdefault(key, {"service": key, "amount": 0, "bills": set()})
                r["amount"] += part
                r["bills"].add(inv)
    dep = conn.scalar(f"SELECT COALESCE(SUM(CASE WHEN kind = 'deposit' THEN amount_cents ELSE -amount_cents END), 0) FROM patient_credits "
                      f"WHERE status = 'valid' AND kind IN ('deposit', 'refund') AND branch_id IN ({marks}) AND entry_date BETWEEN ? AND ?",
                      [*ids, s, e]) or 0
    if dep:
        out["Patient deposits (not yet on a bill)"] = {"service": "Patient deposits (not yet on a bill)", "amount": dep, "bills": set()}
    rows = [{"service": r["service"], "amount": r["amount"], "bills": len(r["bills"])} for r in out.values() if r["amount"]]
    by_doc = [{"service": r["service"], "amount": r["amount"], "bills": len(r["bills"])} for r in docs.values() if r["amount"]]
    if dep:
        by_doc.append({"service": "Patient deposits (not yet on a bill)", "amount": dep, "bills": 0})
    return sorted(rows, key=lambda r: -r["amount"]), sorted(by_doc, key=lambda r: (r["service"] in ("No dentist set", "Patient deposits (not yet on a bill)"), -r["amount"]))


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


@bp.route("/reports/daily-collection", methods=["GET", "POST"])
@require("reports.sales")
def daily_collection():
    """The daily collection report (the same as the automatic email), for any day; super admins can send it now."""
    from .. import daily_report, settings as _settings
    conn = get_db()
    d = parse_date(request.values.get("date")) or today()
    if d > today():
        d = today()
    if request.method == "POST":
        if not g.user.is_super_admin:
            abort(403)
        sent, msg = daily_report.send(conn, d.isoformat())
        audit.record("daily_report_sent", "report", None, f"Daily collection report {d.isoformat()} sent manually", {"result": msg})
        flash(msg, "success" if sent else "error")
        return redirect(url_for("billing.daily_collection", date=d.isoformat()))
    branch_ids = set(g.user.branch_ids)
    reports = [r for r, b in zip(daily_report.build(conn, d.isoformat()),
                                 conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")) if g.user.is_super_admin or b["id"] in branch_ids]
    sends = conn.all("SELECT * FROM report_sends ORDER BY id DESC LIMIT 10") if g.user.is_super_admin else []
    return render_template("staff/billing/daily_collection.html", d=d, reports=reports, sends=sends,
                           auto=_settings.get("report.daily_enabled", conn), at=_settings.get("report.daily_time", conn) or "23:00",
                           to=daily_report.recipients(conn))


@bp.route("/reports/financial", methods=["GET", "POST"])
@require("reports.sales")
def financial():
    """Collections by where the money went (Cash, GCash, Bank transfer – BDO, ...) and per bank account."""
    from .. import finance_report, settings as _settings
    from ..billing import banks
    conn = get_db()
    if request.method == "POST":
        if not g.user.is_super_admin:
            abort(403)
        names = []
        for line in (request.form.get("banks") or "").splitlines():
            n = clean(line, 40)
            if n and n.lower() not in {x.lower() for x in names} and n.lower() != "gcash" and ":" not in n:
                names.append(n)
        if names:
            _settings.put("finance.banks", names, g.user.id, conn)
            audit.record("finance_banks_saved", "settings", None, "Bank accounts: " + ", ".join(names))
            flash("Bank accounts saved.", "success")
        return redirect(url_for("billing.financial"))
    start, end = date_range_args(31)
    if "from" not in request.args:
        start = today().replace(day=1)
    mine = [b for b in conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order") if b["id"] in g.user.branch_ids]
    bid = to_int(request.args.get("branch"))
    shown = [b for b in mine if b["id"] == bid] or mine
    rep = finance_report.build(conn, shown, start.isoformat(), end.isoformat())
    posted_only = request.args.get("posted") == "1"
    st = finance_report.statement(conn, shown, start.isoformat(), end.isoformat(), rep["branch_totals"], posted_only)
    if request.args.get("format") == "csv":
        if not g.user.can("reports.export"):
            abort(403)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Where the payment went", *[b["name"] for b in shown], "Total (PHP)"])
        for r in rep["rows"]:
            w.writerow([r["label"], *[r["net"][b["id"]] / 100 for b in shown], r["total"] / 100])
        w.writerow(["Total", *[rep["branch_totals"][b["id"]] / 100 for b in shown], rep["total"] / 100])
        w.writerow([])
        w.writerow(["Gross less expenses", *[b["name"] for b in shown], "Total (PHP)"])
        w.writerow(["Gross collections", *[st["gross"].get(b["id"], 0) / 100 for b in shown], st["gross_total"] / 100])
        for r in st["rows"]:
            w.writerow(["Less: " + r["label"], *[r["by"][b["id"]] / 100 for b in shown], r["total"] / 100])
        w.writerow(["Total expenses", *[st["expenses"][b["id"]] / 100 for b in shown], st["expenses_total"] / 100])
        w.writerow(["NET", *[st["net"][b["id"]] / 100 for b in shown], st["net_total"] / 100])
        w.writerow([])
        by, summary = _financial_summary(conn, shown, start, end, posted_only)
        w.writerow([f"Summary by {by}", *[b["name"] for b in shown], "Collections (PHP)", "Expenses (PHP)", "Net (PHP)"])
        for r in summary:
            w.writerow([r["label"], *[r["by_branch"][b["id"]] / 100 for b in shown], r["gross"] / 100, r["expenses"] / 100, r["net"] / 100])
        w.writerow([])
        w.writerow(["Account", "Paid in directly", "Cash deposited", "Total (PHP)"])
        for a in rep["accounts"]:
            w.writerow([a["name"], a["direct"] / 100, a["cash_deposited"] / 100, a["total"] / 100])
        audit.record("financial_report_exported", "report", None, f"Financial report {start} to {end}")
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="financial-report-{start}-to-{end}.csv"', "Cache-Control": "no-store"})
    by, summary = _financial_summary(conn, shown, start, end, posted_only)
    t = today()
    ly = t.replace(year=t.year - 1, month=1, day=1)
    lm_end = t.replace(day=1) - timedelta(days=1)
    presets = [("Today", t, t), ("This month", t.replace(day=1), t), ("Last month", lm_end.replace(day=1), lm_end),
               ("This year", t.replace(month=1, day=1), t), ("Last year", ly, ly.replace(month=12, day=31))]
    return render_template("staff/billing/financial.html", rep=rep, st=st, posted_only=posted_only, shown=shown, mine=mine, bid=bid if len(shown) == 1 and len(mine) > 1 else None,
                           start=start, end=end, banks=banks(conn), by=by, summary=summary, presets=presets)


def _financial_summary(conn, shown, start, end, posted_only: bool):
    """Collections, expenses and net per day, month or year inside the chosen dates (?by=day|month|year;
    by default days for up to two months, months for up to three years, else years)."""
    from .. import finance_report
    days = (end - start).days + 1
    by = request.args.get("by") if request.args.get("by") in ("day", "month", "year") else \
        ("day" if days <= 62 else "month" if days <= 1100 else "year")
    if by == "day" and days > 400:
        by = "month"
    buckets, d = [], start
    while d <= end:
        if by == "day":
            e = d
            label = d.strftime("%a, %b %-d, %Y")
        elif by == "month":
            nxt = d.replace(day=1, year=d.year + (d.month == 12), month=d.month % 12 + 1)
            e = min(end, nxt - timedelta(days=1))
            label = d.strftime("%B %Y")
        else:
            e = min(end, d.replace(month=12, day=31))
            label = str(d.year)
        buckets.append((label, d, e))
        d = e + timedelta(days=1)
    rows = []
    for label, s0, e0 in buckets:
        rep = finance_report.build(conn, shown, s0.isoformat(), e0.isoformat())
        st = finance_report.statement(conn, shown, s0.isoformat(), e0.isoformat(), rep["branch_totals"], posted_only)
        rows.append({"label": label, "start": s0, "end": e0, "gross": st["gross_total"], "expenses": st["expenses_total"], "net": st["net_total"],
                     "by_branch": {b["id"]: st["gross"].get(b["id"], 0) for b in shown}})
    top = max([r["gross"] for r in rows] + [1])
    for r in rows:
        r["pct"] = round(100 * max(0, r["gross"]) / top)
    return by, rows


@bp.route("/reports/sales")
@require("reports.sales")
def sales():
    conn = get_db()
    start, end = date_range_args(30)
    ids = _report_branches(conn)
    by_branch, methods, services_rows, daily = _sales_data(conn, ids, start, end)
    coll_services, coll_dentists = collections_by_service(conn, ids, start, end)
    totals = {k: sum(r[k] for r in by_branch) for k in ("invoices", "sales", "discounts", "tax", "received", "refunded", "collections", "voids",
                                                          "expenses", "net_cash", "deposits")}
    outstanding = _outstanding(conn, ids)
    max_daily = max([d["sales"] for d in daily] + [1])
    return render_template("staff/billing/sales.html", start=start, end=end, by_branch=by_branch, totals=totals, methods=methods,
                           coll_services=coll_services, coll_dentists=coll_dentists,
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
                     f"FROM leads WHERE spam = 0 AND (branch_id IN ({marks}) OR branch_id IS NULL) AND created_at >= ? AND created_at < ? GROUP BY source ORDER BY n DESC",
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
    pm = parse_pay(request.form.get("method"), conn)
    method, account = pm or ("", "")
    entry = parse_date(request.form.get("entry_date")) or today()
    note = clean(request.form.get("notes"), 300)
    back = redirect(url_for("patients.detail", patient_id=patient_id) + "#billing")
    if not branch_id or not g.user.in_branch(branch_id):
        flash("Choose one of your branches.", "error")
        return back
    if not amount or amount <= 0 or not pm or entry > today():
        flash("Enter an amount, a payment method and a date that isn't in the future.", "error")
        return back
    with conn.transaction(immediate=True):
        if action == "refund":
            if amount > credit_balance(conn, patient_id) or not note:
                flash("A refund can't exceed the patient's credit, and needs a reason.", "error")
                return back
        cid = conn.insert("patient_credits", {"patient_id": patient_id, "branch_id": branch_id, "kind": action, "amount_cents": amount,
                                              "method": method, "account": account, "reference": clean(request.form.get("reference"), 80),
                                              "entry_date": entry.isoformat(), "notes": note, "created_by": g.user.id,
                                              "created_at": now_str()})
        audit.record("credit_" + action, "patient", patient_id, f"Account credit {action} {peso(amount)} via {pay_label(method, account)}",
                     {"credit_id": cid, "reason": note}, branch_id)
    flash("Deposit recorded as account credit." if action == "deposit" else "Credit refund recorded.", "success")
    return back


@bp.route("/reports/business")
@require("reports.sales")
def business():
    """Monthly business report: scorecard, key ratios, costs by group, takeaways (vs the month before)."""
    from datetime import date as _date
    from .. import business_report as br
    conn = get_db()
    raw = request.args.get("month") or today().strftime("%Y-%m")
    try:
        m = _date(int(raw[:4]), int(raw[5:7]), 1)
    except (ValueError, IndexError):
        m = today().replace(day=1)
    mine = [b for b in conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order") if b["id"] in g.user.branch_ids]
    bid = to_int(request.args.get("branch"))
    shown = [b for b in mine if b["id"] == bid] or mine
    start, end = br.month_bounds(m)
    end = min(end, today()) if start <= today() else end
    prev_m = (start - timedelta(days=1)).replace(day=1)
    p0, p1 = br.month_bounds(prev_m)
    if start <= today() <= br.month_bounds(m)[1]:
        p1 = min(p1, p0 + (end - start))          # month so far: compare with the same days of the month before
    cur, prev = br.figures(conn, shown, start, end), br.figures(conn, shown, p0, p1)
    label, plabel = start.strftime("%B %Y"), prev_m.strftime("%B")
    notes = br.takeaways(cur, prev, label, plabel)
    if request.args.get("format") == "csv":
        if not g.user.can("reports.export"):
            abort(403)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"Business report {label}", ", ".join(b["name"] for b in shown)])
        w.writerow(["Item", f"{label} (PHP)", f"{prev_m.strftime('%B %Y')} (PHP)"])
        for k, lab in (("gross", "Gross collections"), ("expenses", "Total expenses"), ("payroll", "Total payroll"), ("net", "Net profit")):
            w.writerow([lab, cur[k] / 100, prev[k] / 100])
        for k, lab in (("margin", "Net profit margin %"), ("supply_pct", "Dental supply / lab cost %"), ("payroll_pct", "Payroll cost %")):
            w.writerow([lab, cur[k] if cur[k] is not None else "", prev[k] if prev[k] is not None else ""])
        for gname, gv in cur["groups"].items():
            w.writerow([gname, gv["total"] / 100, prev["groups"][gname]["total"] / 100])
            for item, amt in gv["lines"]:
                w.writerow([f"  {item}", amt / 100, ""])
        for n in notes:
            w.writerow(["Takeaway", n])
        audit.record("business_report_exported", "report", None, f"Business report {label}")
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="business-report-{start.strftime("%Y-%m")}.csv"', "Cache-Control": "no-store"})
    months = []
    d = today().replace(day=1)
    for _ in range(24):
        months.append(d)
        d = (d - timedelta(days=1)).replace(day=1)
    from ..tithe import rate as tithe_rate
    return render_template("staff/billing/business.html", cur=cur, prev=prev, label=label, plabel=plabel, notes=notes, groups=br.GROUPS,
                           month=start, months=months, mine=mine, shown=shown, bid=bid if len(shown) == 1 and len(mine) > 1 else None,
                           partial=end < br.month_bounds(m)[1], prev_range=(p0, p1), tithe_pct=tithe_rate(conn))

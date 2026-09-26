"""Price quotations: an itemised estimate a dentist or staff member prepares for a patient (or someone who
isn't a patient yet), priced from Administration → Price list. Printable, and can become a draft invoice.

A quotation is an estimate, not a bill: nothing here records a payment or changes the patient's balance.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..billing import line_amount
from ..db import get_db
from ..permissions import branch_filter, can_see_patient
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import branches_for_user

bp = Blueprint("quotes", __name__, url_prefix="/staff/quotes")

STATUSES = {"draft": "Draft", "issued": "Given to patient", "accepted": "Accepted", "declined": "Declined"}
DEFAULT_VALID_DAYS = 30

QUOTE_SELECT = ("SELECT q.*, b.name AS branch, b.address AS branch_address, b.phone AS branch_phone, "
                "p.first_name, p.last_name, p.chart_no, u.name AS dentist, cb.name AS created_by_name "
                "FROM quotations q JOIN branches b ON b.id = q.branch_id LEFT JOIN patients p ON p.id = q.patient_id "
                "LEFT JOIN users u ON u.id = q.dentist_id LEFT JOIN users cb ON cb.id = q.created_by")


def _dentists(conn, branch_id):
    return conn.all("SELECT u.id, u.name FROM users u JOIN user_branches ub ON ub.user_id = u.id "
                    "WHERE u.role = 'dentist' AND u.active = 1 AND ub.branch_id = ? ORDER BY u.name", (branch_id,))


def _load(quote_id):
    conn = get_db()
    q = conn.one(QUOTE_SELECT + " WHERE q.id = ?", (quote_id,))
    if not q:
        abort(404)
    if not g.user.in_branch(q["branch_id"]):
        abort(403)
    if q["patient_id"] and not can_see_patient(conn, g.user, q["patient_id"]):
        abort(403)
    return q


def _recalc(conn, quote_id):
    q = conn.one("SELECT * FROM quotations WHERE id = ?", (quote_id,))
    subtotal = sum(i["amount_cents"] for i in conn.all("SELECT amount_cents FROM quotation_items WHERE quotation_id = ?", (quote_id,)))
    discount = max(0, min(q["discount_cents"] or 0, subtotal))
    conn.update("quotations", quote_id, {"subtotal_cents": subtotal, "discount_cents": discount, "total_cents": subtotal - discount,
                                         "updated_at": now_str()})


def _next_number(conn, branch_id):
    """QT-MAL-2026-0001, per branch and year. Call inside a transaction."""
    seq = conn.one("SELECT prefix FROM invoice_sequences WHERE branch_id = ?", (branch_id,))
    b = conn.one("SELECT slug FROM branches WHERE id = ?", (branch_id,))
    prefix = seq["prefix"] if seq else (b["slug"][:3].upper() if b else "DH")
    year = today().year
    stem = f"QT-{prefix}-{year}-"
    last = conn.one("SELECT number FROM quotations WHERE number LIKE ? ORDER BY number DESC LIMIT 1", (stem + "%",))
    n = int(last["number"].rsplit("-", 1)[1]) + 1 if last else 1
    return f"{stem}{n:04d}"


def price_list(conn):
    return conn.all("SELECT p.*, s.name AS service FROM price_items p LEFT JOIN services s ON s.id = p.service_id "
                    "WHERE p.published = 1 ORDER BY s.sort_order, p.sort_order, p.id")


# ---------------------------------------------------------------------------
@bp.route("")
@require("quotes.view")
def index():
    conn = get_db()
    status = request.args.get("status", "")
    bf, bpar = branch_filter(g.user, "q.branch_id")
    where, args = [bf], list(bpar)
    if status in STATUSES:
        where.append("q.status = ?")
        args.append(status)
    if g.user.role == "dentist":
        where.append("(q.dentist_id = ? OR q.created_by = ?)")
        args += [g.user.id, g.user.id]
    rows = conn.all(QUOTE_SELECT + f" WHERE {' AND '.join(where)} ORDER BY q.id DESC LIMIT 200", args)
    return render_template("staff/quotes/index.html", rows=rows, status=status, statuses=STATUSES)


@bp.route("/new", methods=["GET", "POST"])
@require("quotes.manage")
def new():
    conn = get_db()
    patient_id = to_int(request.values.get("patient_id"))
    appointment_id = to_int(request.values.get("appointment_id"))
    patient = None
    if patient_id:
        if not can_see_patient(conn, g.user, patient_id):
            abort(403)
        patient = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    appt = conn.one("SELECT * FROM appointments WHERE id = ? AND patient_id = ?", (appointment_id, patient_id)) if appointment_id and patient_id else None
    branches = branches_for_user(g.user)
    default_branch = (appt["branch_id"] if appt else None) or g.user.active_branch_id or (patient["preferred_branch_id"] if patient else None) \
        or (branches[0]["id"] if branches else None)
    v = {"branch_id": default_branch, "client_name": "", "client_contact": "",
         "dentist_id": g.user.id if g.user.role == "dentist" else (appt["dentist_id"] if appt else None),
         "valid_until": (today() + timedelta(days=DEFAULT_VALID_DAYS)).isoformat()}
    errors = {}
    if request.method == "POST":
        v.update({"branch_id": to_int(request.form.get("branch_id")), "client_name": clean(request.form.get("client_name"), 120),
                  "client_contact": clean(request.form.get("client_contact"), 120), "dentist_id": to_int(request.form.get("dentist_id")),
                  "valid_until": clean(request.form.get("valid_until"), 10)})
        if not v["branch_id"] or not g.user.in_branch(v["branch_id"]):
            errors["branch_id"] = "Choose one of your branches."
        if not patient and len(v["client_name"]) < 2:
            errors["client_name"] = "Enter the name of the person the quotation is for."
        valid = parse_date(v["valid_until"])
        if not valid or valid < today():
            errors["valid_until"] = "Choose a date from today onwards."
        if v["dentist_id"] and not any(d["id"] == v["dentist_id"] for d in _dentists(conn, v["branch_id"] or 0)):
            v["dentist_id"] = None
        if not errors:
            qid = conn.insert("quotations", {
                "branch_id": v["branch_id"], "patient_id": patient["id"] if patient else None,
                "client_name": "" if patient else v["client_name"], "client_contact": "" if patient else v["client_contact"],
                "dentist_id": v["dentist_id"], "appointment_id": appt["id"] if appt else None, "status": "draft",
                "valid_until": valid.isoformat(), "created_by": g.user.id, "created_at": now_str(), "updated_at": now_str()})
            audit.record("quote_created", "quotation", qid, "Draft quotation created", branch_id=v["branch_id"])
            return redirect(url_for("quotes.edit", quote_id=qid))
    dentists = _dentists(conn, v["branch_id"]) if v["branch_id"] else []
    return render_template("staff/quotes/new.html", patient=patient, appt=appt, v=v, errors=errors, branches=branches, dentists=dentists)


@bp.route("/<int:quote_id>", methods=["GET", "POST"])
@require("quotes.view")
def edit(quote_id):
    conn = get_db()
    q = _load(quote_id)
    if request.method == "POST":
        if not g.user.can("quotes.manage"):
            abort(403)
        action = request.form.get("action")
        editable = q["status"] == "draft"
        if action == "add_item" and editable:
            pid = to_int(request.form.get("price_item_id"))
            p = conn.one("SELECT * FROM price_items WHERE id = ?", (pid,)) if pid else None
            desc = clean(request.form.get("description"), 200) or (p["name"] if p else "")
            qty = max(1, min(99, to_int(request.form.get("qty"), 1) or 1))
            unit = parse_money(request.form.get("unit_price"))
            if unit is None and p:
                unit = p["price_from_cents"]
            disc = parse_money(request.form.get("discount")) or 0
            if not desc or unit is None:
                flash("Choose a treatment from the price list, or type a description and a price.", "error")
            else:
                seq = (conn.scalar("SELECT MAX(seq) FROM quotation_items WHERE quotation_id = ?", (quote_id,)) or 0) + 1
                conn.insert("quotation_items", {
                    "quotation_id": quote_id, "price_item_id": p["id"] if p else None, "service_id": p["service_id"] if p else None,
                    "description": desc, "tooth": clean(request.form.get("tooth"), 60), "qty": qty, "unit_price_cents": unit,
                    "discount_cents": min(disc, qty * unit), "amount_cents": line_amount(qty, unit, disc),
                    "sample_price": 1 if (p and p["sample"] and unit == p["price_from_cents"]) else 0, "seq": seq})
                _recalc(conn, quote_id)
        elif action == "remove_item" and editable:
            conn.execute("DELETE FROM quotation_items WHERE id = ? AND quotation_id = ?", (to_int(request.form.get("item_id")), quote_id))
            _recalc(conn, quote_id)
        elif action == "details" and editable:
            valid = parse_date(request.form.get("valid_until"))
            did = to_int(request.form.get("dentist_id"))
            conn.update("quotations", quote_id, {
                "discount_cents": parse_money(request.form.get("discount")) or 0, "notes": clean(request.form.get("notes"), 2000),
                "valid_until": valid.isoformat() if valid else q["valid_until"],
                "dentist_id": did if did and any(d["id"] == did for d in _dentists(conn, q["branch_id"])) else None})
            _recalc(conn, quote_id)
            flash("Quotation updated.", "success")
        elif action == "issue" and editable:
            if not conn.scalar("SELECT COUNT(*) FROM quotation_items WHERE quotation_id = ?", (quote_id,)):
                flash("Add at least one item first.", "error")
            else:
                with conn.transaction(immediate=True):
                    conn.update("quotations", quote_id, {"status": "issued", "number": q["number"] or _next_number(conn, q["branch_id"]),
                                                         "issued_at": now_str(), "updated_at": now_str()})
                audit.record("quote_issued", "quotation", quote_id, "Quotation finalised", branch_id=q["branch_id"])
                flash("Quotation finalised. Print it or give it to the patient.", "success")
        elif action in ("accepted", "declined") and q["status"] == "issued":
            conn.update("quotations", quote_id, {"status": action, "updated_at": now_str()})
            audit.record("quote_" + action, "quotation", quote_id, f"Quotation {action}", branch_id=q["branch_id"])
        elif action == "reopen" and q["status"] in ("issued", "declined") and not q["invoice_id"]:
            conn.update("quotations", quote_id, {"status": "draft", "updated_at": now_str()})
            audit.record("quote_reopened", "quotation", quote_id, "Quotation reopened for editing", branch_id=q["branch_id"])
        elif action == "duplicate":
            with conn.transaction():
                nid = conn.insert("quotations", {k: q[k] for k in ("branch_id", "patient_id", "client_name", "client_contact", "dentist_id",
                                                                   "discount_cents", "notes")}
                                  | {"status": "draft", "valid_until": (today() + timedelta(days=DEFAULT_VALID_DAYS)).isoformat(),
                                     "created_by": g.user.id, "created_at": now_str(), "updated_at": now_str()})
                for it in conn.all("SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY seq", (quote_id,)):
                    conn.insert("quotation_items", {k: it[k] for k in ("price_item_id", "service_id", "description", "tooth", "qty",
                                                                       "unit_price_cents", "discount_cents", "amount_cents", "sample_price", "seq")}
                                | {"quotation_id": nid})
                _recalc(conn, nid)
            audit.record("quote_created", "quotation", nid, f"Copied from quotation {q['number'] or q['id']}", branch_id=q["branch_id"])
            return redirect(url_for("quotes.edit", quote_id=nid))
        elif action == "to_invoice" and q["status"] == "accepted" and not q["invoice_id"]:
            if not g.user.can("billing.manage"):
                abort(403)
            if not q["patient_id"]:
                flash("Register the person as a patient first, then create a new quotation for them to bill it.", "error")
            else:
                from .billing import _recalc as invoice_recalc
                with conn.transaction():
                    inv_id = conn.insert("invoices", {"branch_id": q["branch_id"], "patient_id": q["patient_id"],
                                                      "appointment_id": q["appointment_id"], "status": "draft",
                                                      "discount_cents": q["discount_cents"], "notes": f"From quotation {q['number']}",
                                                      "created_by": g.user.id, "created_at": now_str()})
                    for it in conn.all("SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY seq", (quote_id,)):
                        desc = it["description"] + (f" (tooth {it['tooth']})" if it["tooth"] else "")
                        conn.insert("invoice_items", {"invoice_id": inv_id, "service_id": it["service_id"], "description": desc[:200],
                                                      "qty": it["qty"], "unit_price_cents": it["unit_price_cents"],
                                                      "discount_cents": it["discount_cents"], "amount_cents": it["amount_cents"]})
                    invoice_recalc(conn, inv_id)
                    conn.update("quotations", quote_id, {"invoice_id": inv_id, "updated_at": now_str()})
                    audit.record("invoice_created", "invoice", inv_id, f"Draft invoice from quotation {q['number']}", branch_id=q["branch_id"])
                flash("Draft invoice created from the quotation. Check it before issuing.", "success")
                return redirect(url_for("billing.invoice", invoice_id=inv_id))
        elif action == "delete" and q["status"] == "draft":
            with conn.transaction():
                conn.execute("DELETE FROM quotation_items WHERE quotation_id = ?", (quote_id,))
                conn.execute("DELETE FROM quotations WHERE id = ?", (quote_id,))
            audit.record("quote_deleted", "quotation", quote_id, "Draft quotation deleted", branch_id=q["branch_id"])
            flash("Draft quotation deleted.", "success")
            return redirect(url_for("quotes.index"))
        return redirect(url_for("quotes.edit", quote_id=quote_id))
    items = conn.all("SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY seq", (quote_id,))
    return render_template("staff/quotes/edit.html", q=q, items=items, prices=price_list(conn), statuses=STATUSES,
                           dentists=_dentists(conn, q["branch_id"]), today=today().isoformat())


@bp.route("/<int:quote_id>/print")
@require("quotes.view")
def print_view(quote_id):
    conn = get_db()
    q = _load(quote_id)
    items = conn.all("SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY seq", (quote_id,))
    return render_template("staff/quotes/print.html", q=q, items=items, statuses=STATUSES)

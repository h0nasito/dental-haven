"""Outside-clinic lab works: dental work other clinics send to our laboratory (DSDL), with invoices,
discounts and payment acknowledgment receipts.

Access
- lab.works   : see, add and update works, and the clinics list.
- lab.billing : invoices, discounts, payments and receipts.
Both apply only to the labs a user is assigned to (Users → Authorized laboratories). Super admins see all.
No role has these permissions by default; a super admin grants them in Role access.

The acknowledgment receipt confirms a payment was received. It is NOT a BIR official receipt.
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import login_required
from ..db import get_db
from ..notices import lab_staff, notify, run_lab_due_checks
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .labs import CASE_TYPES

bp = Blueprint("lab_works", __name__, url_prefix="/staff/lab")

from ..lab_status import WORK_STATUSES as STATUSES, label as status_label, sql_list  # noqa: E402
from ..lab_status import OPEN as _OPEN  # noqa: E402
OPEN = sql_list(k for k in _OPEN if k != "sent")
ARCHES = {"": "—", "upper": "Upper", "lower": "Lower", "both": "Upper & lower"}
METHODS = {"cash": "Cash", "gcash": "GCash", "maya": "Maya", "bank": "Bank transfer", "check": "Check", "card": "Card"}
LAB_FULL_NAMES = {"DSDL": "Digital Solutions Dental Laboratory"}


def lab_display(name):
    full = LAB_FULL_NAMES.get(name)
    return f"{full} ({name})" if full else name


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def my_labs(conn=None):
    conn = conn or get_db()
    if g.user.is_super_admin:
        return conn.all("SELECT * FROM laboratories WHERE active = 1 ORDER BY id")
    return conn.all("SELECT l.* FROM laboratories l JOIN user_labs ul ON ul.lab_id = l.id WHERE ul.user_id = ? AND l.active = 1 ORDER BY l.id",
                    (g.user.id,))


def _need(perm):
    if not (g.user.is_super_admin or (g.user.can(perm) and my_labs())):
        abort(403)


def _lab_ids():
    return [l["id"] for l in my_labs()]


def _in(ids):
    return ",".join("?" for _ in ids) or "NULL"


def price_items(conn, lab_ids, active_only=True):
    if not lab_ids:
        return []
    return conn.all(f"SELECT * FROM lab_price_items WHERE lab_id IN ({_in(lab_ids)})" + (" AND active = 1" if active_only else "")
                    + " ORDER BY lab_id, sort_order, id", list(lab_ids))


def branch_clients(conn, lab_ids) -> None:
    """Each active branch is a client of each lab, so the lab can bill the branch for its lab cases."""
    for lab_id in lab_ids:
        for b in conn.all("SELECT * FROM branches WHERE active = 1"):
            if not conn.one("SELECT id FROM lab_clients WHERE lab_id = ? AND branch_id = ?", (lab_id, b["id"])):
                conn.insert("lab_clients", {"lab_id": lab_id, "branch_id": b["id"], "clinic_name": f"Dental Haven {b['name']} (branch)",
                                            "contact_number": (b["phone"] or "")[:60], "address": (b["address"] or "")[:300],
                                            "created_at": now_str()})


def case_label(c) -> str:
    """How a branch lab case appears on a lab invoice (chart number, not the patient's name)."""
    return (f"Case #{c['id']} · {c['case_type']}" + (f" · {c['teeth']}" if c["teeth"] else "") + f" · {c['chart_no']}"
            + (f" · {c['dentist']}" if c["dentist"] else ""))[:200]


def item_groups(conn, items) -> list[dict]:
    """Invoice lines grouped by branch lab case or outside clinic work (each with a heading and subtotal); other lines come last."""
    order, groups = [], {}
    for it in items:
        key = ("c", it["case_id"]) if it["case_id"] else (("w", it["work_id"]) if it["work_id"] else None)
        if key not in groups:
            c = conn.one("SELECT c.id, c.case_type, c.teeth, p.chart_no, u.name AS dentist FROM lab_cases c JOIN patients p ON p.id = c.patient_id "
                         "LEFT JOIN users u ON u.id = c.dentist_id WHERE c.id = ?", (key[1],)) if key and key[0] == "c" else None
            w = conn.one("SELECT id, number, case_type, teeth, patient_ref, doctor FROM lab_works WHERE id = ?", (key[1],)) \
                if key and key[0] == "w" else None
            groups[key] = {"case": c, "work": w, "items": [], "subtotal": 0}
            order.append(key)
        groups[key]["items"].append(it)
        groups[key]["subtotal"] += it["amount_cents"]
    order = [k for k in order if k is not None] + [k for k in order if k is None]
    return [groups[k] for k in order]


def sync_case_prices(conn, invoice_id) -> None:
    """A branch case's lab price = what its lines on its (not voided) lab invoice add up to."""
    for r in conn.all("SELECT DISTINCT case_id FROM lab_invoice_items WHERE invoice_id = ? AND case_id IS NOT NULL", (invoice_id,)):
        total = conn.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM lab_invoice_items WHERE invoice_id = ? AND case_id = ?",
                            (invoice_id, r["case_id"])) or 0
        conn.execute("UPDATE lab_cases SET lab_fee_cents = ? WHERE id = ?", (max(0, total), r["case_id"]))


def _work(conn, work_id):
    ids = _lab_ids()
    w = conn.one(f"SELECT w.*, i.number AS invoice_number, i.status AS invoice_status FROM lab_works w LEFT JOIN lab_invoices i ON i.id = w.invoice_id "
                 f"WHERE w.id = ? AND w.lab_id IN ({_in(ids)})", [work_id, *ids])
    if not w:
        abort(404)
    return w


def _invoice(conn, invoice_id):
    ids = _lab_ids()
    inv = conn.one(f"SELECT * FROM lab_invoices WHERE id = ? AND lab_id IN ({_in(ids)})", [invoice_id, *ids])
    if not inv:
        abort(404)
    return inv


def _next_number(conn, table, prefix):
    stem = f"{prefix}-{today().year}-"
    last = conn.one(f"SELECT number FROM {table} WHERE number LIKE ? ORDER BY number DESC LIMIT 1", (stem + "%",)) if table != "lab_payments" else \
        conn.one("SELECT receipt_no AS number FROM lab_payments WHERE receipt_no LIKE ? ORDER BY receipt_no DESC LIMIT 1", (stem + "%",))
    n = int(last["number"].rsplit("-", 1)[1]) + 1 if last else 1
    return f"{stem}{n:04d}"


def _client_for(conn, lab_id, clinic_name, doctor, contact):
    c = conn.one("SELECT * FROM lab_clients WHERE lab_id = ? AND LOWER(clinic_name) = LOWER(?)", (lab_id, clinic_name))
    if c:
        upd = {}
        if doctor and not c["doctor"]:
            upd["doctor"] = doctor
        if contact and not c["contact_number"]:
            upd["contact_number"] = contact
        if upd:
            conn.update("lab_clients", c["id"], upd)
        return c["id"]
    return conn.insert("lab_clients", {"lab_id": lab_id, "clinic_name": clinic_name, "doctor": doctor, "contact_number": contact,
                                       "active": 1, "created_at": now_str()})


def _work_form(form, labs):
    v = {k: clean(form.get(k), 1000) for k in ("lab_id", "clinic_name", "doctor", "contact_number", "patient_ref", "case_type", "units", "arch",
                                                "teeth", "shade", "material", "instructions", "received_on", "due_on", "price")}
    errors = {}
    v["lab_id"] = to_int(v["lab_id"]) or (labs[0]["id"] if len(labs) == 1 else None)
    if not any(l["id"] == v["lab_id"] for l in labs):
        errors["lab_id"] = "Choose the laboratory."
    if len(v["clinic_name"]) < 2:
        errors["clinic_name"] = "Enter the dental clinic's name."
    if v["case_type"] not in CASE_TYPES:
        errors["case_type"] = "Choose the type of case."
    units = to_int(v["units"])
    if units is None or units < 1 or units > 99:
        errors["units"] = "Enter the number of units (1 to 99)."
    if v["arch"] not in ARCHES:
        v["arch"] = ""
    rec = parse_date(v["received_on"])
    if not rec or rec > today():
        errors["received_on"] = "Enter the date received (not in the future)."
    due = parse_date(v["due_on"]) if v["due_on"] else None
    if v["due_on"] and not due:
        errors["due_on"] = "Enter the due date as YYYY-MM-DD."
    elif due and rec and due < rec:
        errors["due_on"] = "The due date can't be before the date received."
    price = parse_money(v["price"]) if v["price"] else None
    if v["price"] and (price is None or price < 0):
        errors["price"] = "Enter the price per unit, like 3500 or 3,500.00."
    clean_v = {"lab_id": v["lab_id"], "clinic_name": v["clinic_name"][:120], "doctor": v["doctor"][:120], "contact_number": v["contact_number"][:60],
               "patient_ref": v["patient_ref"][:60], "case_type": v["case_type"], "units": units or 1, "arch": v["arch"], "teeth": v["teeth"][:60],
               "shade": v["shade"][:30], "material": v["material"][:80], "instructions": v["instructions"][:1000],
               "received_on": rec.isoformat() if rec else None, "due_on": due.isoformat() if due else None, "price_cents": price}
    return v, clean_v, errors


def _recalc(conn, invoice_id):
    inv = conn.one("SELECT * FROM lab_invoices WHERE id = ?", (invoice_id,))
    sub = sum(i["amount_cents"] for i in conn.all("SELECT amount_cents FROM lab_invoice_items WHERE invoice_id = ?", (invoice_id,)))
    disc = max(0, min(inv["discount_cents"] or 0, sub))
    paid = conn.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM lab_payments WHERE invoice_id = ? AND status = 'ok'", (invoice_id,)) or 0
    conn.update("lab_invoices", invoice_id, {"subtotal_cents": sub, "discount_cents": disc, "total_cents": sub - disc, "paid_cents": paid,
                                             "updated_at": now_str()})


KINDS = {"outside": "Outside clinics", "branch": "Dental Haven branches"}


def _kind_sql(kind, alias="i"):
    """SQL to keep only invoices to outside clinics or only to our own branches."""
    if kind == "outside":
        return f" AND {alias}.client_id IN (SELECT id FROM lab_clients WHERE branch_id IS NULL)"
    if kind == "branch":
        return f" AND {alias}.client_id IN (SELECT id FROM lab_clients WHERE branch_id IS NOT NULL)"
    return ""


def pay_status(inv):
    if inv["status"] == "void":
        return "void"
    if inv["status"] == "draft":
        return "draft"
    if inv["paid_cents"] >= inv["total_cents"]:
        return "paid"
    return "partial" if inv["paid_cents"] else "unpaid"


PAY_LABELS = {"draft": ("Draft", ""), "unpaid": ("Unpaid", "badge-amber"), "partial": ("Partly paid", "badge-amber"), "paid": ("Paid", "badge-green"),
              "void": ("Void", "badge-red")}


# ---------------------------------------------------------------------------
# Works
# ---------------------------------------------------------------------------

@bp.route("/works")
@login_required
def works():
    _need("lab.works")
    conn = get_db()
    run_lab_due_checks(conn)
    ids = _lab_ids()
    status = request.args.get("status", "open")
    q = clean(request.args.get("q"), 80).lower()
    client = to_int(request.args.get("client"))
    where, args = [f"w.lab_id IN ({_in(ids)})"], list(ids)
    if status == "open":
        where.append(f"w.status IN {OPEN}")
    elif status in STATUSES:
        where.append("w.status = ?")
        args.append(status)
    if client:
        where.append("w.client_id = ?")
        args.append(client)
    if q:
        where.append("(LOWER(w.number) LIKE ? OR LOWER(w.clinic_name) LIKE ? OR LOWER(w.doctor) LIKE ? OR LOWER(w.patient_ref) LIKE ?)")
        args += [f"%{q}%"] * 4
    rows = conn.all("SELECT w.*, i.number AS invoice_number FROM lab_works w LEFT JOIN lab_invoices i ON i.id = w.invoice_id "
                    f"WHERE {' AND '.join(where)} ORDER BY CASE WHEN w.status IN {OPEN} THEN 0 ELSE 1 END, "
                    "CASE WHEN w.due_on IS NULL THEN 1 ELSE 0 END, w.due_on, w.id DESC LIMIT 400", args)
    counts = {r["status"]: r["n"] for r in conn.all(f"SELECT status, COUNT(*) AS n FROM lab_works WHERE lab_id IN ({_in(ids)}) GROUP BY status", ids)}
    clients = conn.all(f"SELECT id, clinic_name FROM lab_clients WHERE lab_id IN ({_in(ids)}) ORDER BY clinic_name", ids)
    return render_template("staff/lab_works/index.html", rows=rows, status=status, statuses=STATUSES, counts=counts, q=q, client=client,
                           clients=clients, arches=ARCHES, today=today().isoformat(), soon=(today() + timedelta(days=1)).isoformat())


@bp.route("/works/new", methods=["GET", "POST"])
@login_required
def work_new():
    _need("lab.works")
    conn = get_db()
    labs = my_labs(conn)
    v = {"lab_id": labs[0]["id"] if labs else None, "clinic_name": "", "doctor": "", "contact_number": "", "patient_ref": "",
         "case_type": CASE_TYPES[0], "units": "1", "arch": "", "teeth": "", "shade": "", "material": "", "instructions": "",
         "received_on": today().isoformat(), "due_on": "", "price": ""}
    client_id = to_int(request.args.get("client"))
    if client_id and request.method == "GET":
        c = conn.one(f"SELECT * FROM lab_clients WHERE id = ? AND lab_id IN ({_in(_lab_ids())})", [client_id, *_lab_ids()])
        if c:
            v.update({"lab_id": c["lab_id"], "clinic_name": c["clinic_name"], "doctor": c["doctor"], "contact_number": c["contact_number"]})
    errors = {}
    if request.method == "POST":
        v, data, errors = _work_form(request.form, labs)
        if not errors:
            with conn.transaction():
                cid = _client_for(conn, data["lab_id"], data["clinic_name"], data["doctor"], data["contact_number"])
                number = _next_number(conn, "lab_works", "LW")
                wid = conn.insert("lab_works", {**data, "number": number, "client_id": cid, "status": "accepted", "created_by": g.user.id,
                                                "created_at": now_str(), "updated_at": now_str()})
                conn.insert("lab_work_events", {"work_id": wid, "user_id": g.user.id, "status": "accepted", "note": "Work received", "created_at": now_str()})
                notify(conn, lab_staff(conn, data["lab_id"]), "lab_new", f"New work {number}: {data['case_type']}",
                       f"From {data['clinic_name']}" + (f", due {data['due_on']}" if data["due_on"] else ""), f"/staff/lab/works/{wid}",
                       exclude=g.user.id)
                audit.record("lab_work_created", "lab_work", wid, f"Outside work {number} from {data['clinic_name']}")
            flash(f"Saved as {number}.", "success")
            return redirect(url_for("lab_works.work", work_id=wid))
    clinics = conn.all(f"SELECT clinic_name, doctor, contact_number FROM lab_clients WHERE lab_id IN ({_in(_lab_ids())}) AND active = 1 ORDER BY clinic_name",
                       _lab_ids())
    return render_template("staff/lab_works/form.html", v=v, errors=errors, labs=labs, case_types=CASE_TYPES, arches=ARCHES, clinics=clinics,
                           price_list=price_items(conn, [l["id"] for l in labs]),
                           work=None, lab_display=lab_display)


@bp.route("/works/<int:work_id>", methods=["GET", "POST"])
@login_required
def work(work_id):
    _need("lab.works")
    conn = get_db()
    w = _work(conn, work_id)
    if request.method == "POST":
        st = request.form.get("status")
        note = clean(request.form.get("note"), 500)
        if st not in STATUSES:
            abort(400)
        upd = {"status": st, "updated_at": now_str()}
        if st == "delivered":
            d = parse_date(request.form.get("delivered_on")) or today()
            upd["delivered_on"] = min(d, today()).isoformat()
        elif w["delivered_on"] and st != "delivered":
            upd["delivered_on"] = None
        with conn.transaction():
            conn.update("lab_works", w["id"], upd)
            conn.insert("lab_work_events", {"work_id": w["id"], "user_id": g.user.id, "status": st, "note": note, "created_at": now_str()})
            if st != w["status"]:
                notify(conn, lab_staff(conn, w["lab_id"]), "lab_status", f"{w['number']} is now {STATUSES[st]}",
                       f"{w['case_type']} for {w['clinic_name']}", f"/staff/lab/works/{w['id']}", exclude=g.user.id)
            audit.record("lab_work_updated", "lab_work", w["id"], f"{w['number']} → {STATUSES[st]}", {"note": note})
        flash("Status updated.", "success")
        return redirect(url_for("lab_works.work", work_id=w["id"]))
    events = conn.all("SELECT e.*, u.name AS by_name FROM lab_work_events e LEFT JOIN users u ON u.id = e.user_id WHERE e.work_id = ? ORDER BY e.id DESC",
                      (w["id"],))
    lab = conn.one("SELECT * FROM laboratories WHERE id = ?", (w["lab_id"],))
    from ..lab_commission import entries, technicians
    return render_template("staff/lab_works/work.html", w=w, events=events, statuses=STATUSES, arches=ARCHES, lab=lab, lab_display=lab_display,
                           comm_entries=entries(conn, work_id=w["id"]), comm_techs=technicians(conn),
                           can_bill=g.user.is_super_admin or g.user.can("lab.billing"), today=today().isoformat())


@bp.route("/works/<int:work_id>/edit", methods=["GET", "POST"])
@login_required
def work_edit(work_id):
    _need("lab.works")
    conn = get_db()
    w = _work(conn, work_id)
    labs = my_labs(conn)
    v = {**{k: (w[k] if w[k] is not None else "") for k in ("lab_id", "clinic_name", "doctor", "contact_number", "patient_ref", "case_type", "units",
                                                          "arch", "teeth", "shade", "material", "instructions", "received_on", "due_on")},
         "price": "" if w["price_cents"] is None else f"{w['price_cents'] / 100:.2f}"}
    errors = {}
    if request.method == "POST":
        v, data, errors = _work_form(request.form, labs)
        if not errors:
            with conn.transaction():
                cid = _client_for(conn, data["lab_id"], data["clinic_name"], data["doctor"], data["contact_number"])
                reset = {"due_soon_notified": 0, "overdue_notified": 0} if data["due_on"] != w["due_on"] else {}
                conn.update("lab_works", w["id"], {**data, "client_id": cid, "updated_at": now_str(), **reset})
                audit.record("lab_work_edited", "lab_work", w["id"], f"Edited {w['number']}")
            flash("Saved.", "success")
            return redirect(url_for("lab_works.work", work_id=w["id"]))
    clinics = conn.all(f"SELECT clinic_name, doctor, contact_number FROM lab_clients WHERE lab_id IN ({_in(_lab_ids())}) AND active = 1 ORDER BY clinic_name",
                       _lab_ids())
    return render_template("staff/lab_works/form.html", v=v, errors=errors, labs=labs, case_types=CASE_TYPES, arches=ARCHES, clinics=clinics,
                           price_list=price_items(conn, [l["id"] for l in labs]),
                           work=w, lab_display=lab_display)


@bp.route("/works/export.csv")
@login_required
def works_export():
    _need("lab.works")
    conn = get_db()
    ids = _lab_ids()
    start = parse_date(request.args.get("from")) or (today() - timedelta(days=30))
    end = parse_date(request.args.get("to")) or today()
    rows = conn.all(f"SELECT w.*, i.number AS invoice_number FROM lab_works w LEFT JOIN lab_invoices i ON i.id = w.invoice_id "
                    f"WHERE w.lab_id IN ({_in(ids)}) AND w.received_on BETWEEN ? AND ? ORDER BY w.received_on, w.id", [*ids, start.isoformat(), end.isoformat()])
    buf = io.StringIO()
    wr = csv.writer(buf)
    wr.writerow(["Work no.", "Dental clinic", "Doctor", "Contact number", "Type of case", "Units", "Arch", "Teeth", "Shade", "Date received",
                 "Due date", "Date delivered", "Status", "Price per unit (PHP)", "Invoice"])
    safe = lambda x: ("'" + x) if isinstance(x, str) and x[:1] in ("=", "+", "-", "@") else x  # noqa: E731
    for r in rows:
        wr.writerow([safe(x) for x in (r["number"], r["clinic_name"], r["doctor"], r["contact_number"], r["case_type"], r["units"], ARCHES[r["arch"]],
                                        r["teeth"], r["shade"], r["received_on"], r["due_on"] or "", r["delivered_on"] or "", status_label(r["status"]),
                                        "" if r["price_cents"] is None else r["price_cents"] / 100, r["invoice_number"] or "")])
    audit.record("lab_works_exported", "lab_work", None, f"Exported outside works {start} to {end}")
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="lab-works-{start}-to-{end}.csv"', "Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Clinics
# ---------------------------------------------------------------------------

@bp.route("/clients", methods=["GET", "POST"])
@login_required
def clients():
    _need("lab.works")
    conn = get_db()
    ids = _lab_ids()
    if request.method == "POST":
        cid = to_int(request.form.get("client_id"))
        c = conn.one(f"SELECT * FROM lab_clients WHERE id = ? AND lab_id IN ({_in(ids)})", [cid, *ids])
        if not c:
            abort(404)
        name = clean(request.form.get("clinic_name"), 120)
        if len(name) < 2:
            flash("Enter the clinic name.", "error")
        else:
            conn.update("lab_clients", c["id"], {"clinic_name": name, "doctor": clean(request.form.get("doctor"), 120),
                                                 "contact_number": clean(request.form.get("contact_number"), 60),
                                                 "email": clean(request.form.get("email"), 120), "address": clean(request.form.get("address"), 300),
                                                 "active": 1 if request.form.get("active") else 0})
            audit.record("lab_client_updated", "lab_client", c["id"], f"Updated clinic {name}")
            flash("Clinic saved.", "success")
        return redirect(url_for("lab_works.clients"))
    rows = conn.all(f"SELECT c.*, (SELECT COUNT(*) FROM lab_works w WHERE w.client_id = c.id AND w.status IN {OPEN}) AS open_works, "
                    "(SELECT COUNT(*) FROM lab_works w WHERE w.client_id = c.id) AS all_works, "
                    "(SELECT COALESCE(SUM(total_cents - paid_cents), 0) FROM lab_invoices i WHERE i.client_id = c.id AND i.status = 'issued') AS balance_cents "
                    f"FROM lab_clients c WHERE c.lab_id IN ({_in(ids)}) ORDER BY c.active DESC, c.clinic_name", ids)
    edit = to_int(request.args.get("edit"))
    return render_template("staff/lab_works/clients.html", rows=rows, edit=edit, can_bill=g.user.is_super_admin or g.user.can("lab.billing"))


# ---------------------------------------------------------------------------
# Invoices, discounts, payments and receipts
# ---------------------------------------------------------------------------

@bp.route("/invoices")
@login_required
def invoices():
    _need("lab.billing")
    conn = get_db()
    ids = _lab_ids()
    show = request.args.get("show", "open")
    kind = request.args.get("kind") if request.args.get("kind") in KINDS else ""
    rows = conn.all(f"SELECT i.* FROM lab_invoices i WHERE i.lab_id IN ({_in(ids)}){_kind_sql(kind)} ORDER BY i.id DESC LIMIT 400", ids)
    for r in rows:
        r["pay"] = pay_status(r)
    if show == "open":
        rows = [r for r in rows if r["pay"] in ("draft", "unpaid", "partial")]
    branch_clients(conn, ids)
    uninvoiced = conn.all(f"SELECT c.id, c.clinic_name, COUNT(w.id) AS n FROM lab_works w JOIN lab_clients c ON c.id = w.client_id "
                          f"WHERE w.lab_id IN ({_in(ids)}) AND w.invoice_id IS NULL AND w.status != 'cancelled' GROUP BY c.id ORDER BY c.clinic_name", ids)
    branch_uninvoiced = conn.all(f"SELECT cl.id, cl.clinic_name, COUNT(lc.id) AS n FROM lab_cases lc JOIN lab_clients cl ON cl.lab_id = lc.lab_id "
                           f"AND cl.branch_id = lc.branch_id WHERE lc.lab_id IN ({_in(ids)}) AND lc.invoice_id IS NULL AND lc.status != 'cancelled' "
                           "GROUP BY cl.id ORDER BY cl.clinic_name", ids)
    n_branch_uninvoiced = len(branch_uninvoiced)
    uninvoiced += branch_uninvoiced
    outstanding = sum(r["total_cents"] - r["paid_cents"] for r in rows if r["pay"] in ("unpaid", "partial"))
    if kind == "outside":
        uninvoiced = uninvoiced[:len(uninvoiced) - n_branch_uninvoiced]
    elif kind == "branch":
        uninvoiced = uninvoiced[len(uninvoiced) - n_branch_uninvoiced:]
    return render_template("staff/lab_works/invoices.html", rows=rows, show=show, kind=kind, kinds=KINDS, labels=PAY_LABELS,
                           uninvoiced=uninvoiced, outstanding=outstanding)


@bp.route("/invoices/new", methods=["GET", "POST"])
@login_required
def invoice_new():
    _need("lab.billing")
    conn = get_db()
    ids = _lab_ids()
    branch_clients(conn, ids)
    client_id = to_int(request.values.get("client"))
    client = conn.one(f"SELECT * FROM lab_clients WHERE id = ? AND lab_id IN ({_in(ids)})", [client_id, *ids]) if client_id else None
    clients = conn.all(f"SELECT * FROM lab_clients WHERE lab_id IN ({_in(ids)}) AND active = 1 ORDER BY branch_id IS NULL, clinic_name", ids)
    works = conn.all("SELECT * FROM lab_works WHERE client_id = ? AND invoice_id IS NULL AND status != 'cancelled' ORDER BY received_on, id",
                     (client["id"],)) if client else []
    cases = conn.all("SELECT c.*, p.chart_no, u.name AS dentist FROM lab_cases c JOIN patients p ON p.id = c.patient_id "
                     "LEFT JOIN users u ON u.id = c.dentist_id WHERE c.lab_id = ? AND c.branch_id = ? AND c.invoice_id IS NULL "
                     "AND c.status != 'cancelled' ORDER BY c.sent_on, c.id", (client["lab_id"], client["branch_id"])) \
        if client and client["branch_id"] else []
    if request.method == "POST" and client:
        chosen = [w for w in works if request.form.get(f"w_{w['id']}")]
        chosen_cases = [c for c in cases if request.form.get(f"c_{c['id']}")]
        with conn.transaction():
            iid = conn.insert("lab_invoices", {"lab_id": client["lab_id"], "client_id": client["id"], "clinic_name": client["clinic_name"],
                                               "doctor": client["doctor"], "contact_number": client["contact_number"], "status": "draft",
                                               "due_on": (today() + timedelta(days=30)).isoformat(), "created_by": g.user.id,
                                               "created_at": now_str(), "updated_at": now_str()})
            for w in chosen:
                desc = f"{w['number']} · {w['case_type']}" + (f" · {w['teeth']}" if w["teeth"] else "") + (f" · {ARCHES[w['arch']]}" if w["arch"] else "") \
                    + (f" · Dr. {w['doctor']}" if w["doctor"] and not w["doctor"].lower().startswith("dr") else (f" · {w['doctor']}" if w["doctor"] else ""))
                price = w["price_cents"] or 0
                conn.insert("lab_invoice_items", {"invoice_id": iid, "work_id": w["id"], "description": desc[:200], "qty": w["units"],
                                                  "unit_price_cents": price, "discount_cents": 0, "amount_cents": price * w["units"]})
                conn.update("lab_works", w["id"], {"invoice_id": iid, "updated_at": now_str()})
            for c in chosen_cases:
                price = c["lab_fee_cents"] or 0
                conn.insert("lab_invoice_items", {"invoice_id": iid, "case_id": c["id"], "description": case_label(c), "qty": 1,
                                                  "unit_price_cents": price, "discount_cents": 0, "amount_cents": price})
                conn.update("lab_cases", c["id"], {"invoice_id": iid, "updated_at": now_str()})
            _recalc(conn, iid)
            audit.record("lab_invoice_created", "lab_invoice", iid,
                         f"Draft lab invoice for {client['clinic_name']} ({len(chosen)} works, {len(chosen_cases)} branch cases)")
        return redirect(url_for("lab_works.invoice", invoice_id=iid))
    return render_template("staff/lab_works/invoice_new.html", client=client, clients=clients, works=works, cases=cases, arches=ARCHES)


@bp.route("/prices", methods=["GET", "POST"])
@login_required
def prices():
    """The lab's price list. Lab users and branch staff with lab access can see it; lab billing users edit it."""
    conn = get_db()
    labs = my_labs(conn)
    if not labs and (g.user.can("lab.view") or g.user.can("lab.manage")):
        labs = conn.all("SELECT * FROM laboratories WHERE active = 1 ORDER BY id")
    if not labs:
        abort(403)
    can_edit = g.user.is_super_admin or (g.user.can("lab.billing") and bool(my_labs(conn)))
    lab_ids = [l["id"] for l in labs]
    if request.method == "POST":
        if not can_edit:
            abort(403)
        f = request.form
        with conn.transaction():
            if f.get("action") == "add":
                lab_id = to_int(f.get("lab_id"))
                price = parse_money(f.get("price"))
                name = clean(f.get("name"), 120)
                if lab_id not in lab_ids or not name or price is None or price < 0:
                    flash("Enter the item name and its price.", "error")
                else:
                    n = conn.scalar("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM lab_price_items WHERE lab_id = ?", (lab_id,))
                    conn.insert("lab_price_items", {"lab_id": lab_id, "category": clean(f.get("category"), 80), "name": name, "price_cents": price,
                                                    "unit": clean(f.get("unit"), 30), "note": clean(f.get("note"), 200), "sort_order": n,
                                                    "updated_at": now_str()})
                    audit.record("lab_price_added", "lab_price", None, f"Price list: added {name} ({price / 100:,.2f})")
                    flash("Added to the price list.", "success")
            else:
                changed = 0
                for it in price_items(conn, lab_ids, active_only=False):
                    if f"price_{it['id']}" not in f:
                        continue
                    price = parse_money(f.get(f"price_{it['id']}"))
                    vals = {"name": clean(f.get(f"name_{it['id']}"), 120) or it["name"], "unit": clean(f.get(f"unit_{it['id']}"), 30),
                            "note": clean(f.get(f"note_{it['id']}"), 200), "active": 1 if f.get(f"active_{it['id']}") else 0,
                            "price_cents": price if price is not None and price >= 0 else it["price_cents"]}
                    if any(vals[k] != it[k] for k in vals):
                        conn.update("lab_price_items", it["id"], {**vals, "updated_at": now_str()})
                        changed += 1
                        if vals["price_cents"] != it["price_cents"]:
                            audit.record("lab_price_changed", "lab_price", it["id"],
                                         f"Price list: {vals['name']} {it['price_cents'] / 100:,.2f} -> {vals['price_cents'] / 100:,.2f}")
                flash(f"Saved {changed} change{'s' if changed != 1 else ''}." if changed else "No changes.", "success")
        return redirect(url_for("lab_works.prices"))
    rows = price_items(conn, lab_ids, active_only=not can_edit)
    groups = {}
    for r in rows:
        groups.setdefault((r["lab_id"], r["category"] or "Other"), []).append(r)
    return render_template("staff/lab_works/prices.html", labs=labs, groups=groups, can_edit=can_edit,
                           lab_names={l["id"]: lab_display(l["name"]) for l in labs})


@bp.route("/cases/<int:case_id>/bill", methods=["POST"])
@login_required
def bill_case(case_id):
    """Start a lab invoice to the branch for one lab case (or open the one it's already on)."""
    _need("lab.billing")
    conn = get_db()
    ids = _lab_ids()
    c = conn.one(f"SELECT c.*, p.chart_no, u.name AS dentist FROM lab_cases c JOIN patients p ON p.id = c.patient_id "
                 f"LEFT JOIN users u ON u.id = c.dentist_id WHERE c.id = ? AND c.lab_id IN ({_in(ids)})", [case_id, *ids])
    if not c:
        abort(404)
    if c["invoice_id"]:
        return redirect(url_for("lab_works.invoice", invoice_id=c["invoice_id"]))
    branch_clients(conn, [c["lab_id"]])
    client = conn.one("SELECT * FROM lab_clients WHERE lab_id = ? AND branch_id = ?", (c["lab_id"], c["branch_id"]))
    with conn.transaction():
        iid = conn.insert("lab_invoices", {"lab_id": c["lab_id"], "client_id": client["id"], "clinic_name": client["clinic_name"],
                                           "doctor": c["dentist"] or "", "contact_number": client["contact_number"], "status": "draft",
                                           "due_on": (today() + timedelta(days=30)).isoformat(), "created_by": g.user.id,
                                           "created_at": now_str(), "updated_at": now_str()})
        price = c["lab_fee_cents"] or 0
        desc = c["case_type"] + (f" · {c['teeth']}" if c["teeth"] else "") + (f" · {c['material']}" if c["material"] else "")
        conn.insert("lab_invoice_items", {"invoice_id": iid, "case_id": c["id"], "description": desc[:200], "qty": 1,
                                          "unit_price_cents": price, "discount_cents": 0, "amount_cents": price})
        conn.update("lab_cases", c["id"], {"invoice_id": iid, "updated_at": now_str()})
        _recalc(conn, iid)
        audit.record("lab_invoice_created", "lab_invoice", iid, f"Draft lab invoice for case #{c['id']} ({client['clinic_name']})")
    flash("Draft invoice started for this case. Set the units and price per unit, then add extras (e.g. casts) and any “less” lines.", "success")
    return redirect(url_for("lab_works.invoice", invoice_id=iid))


def _work_line(w) -> str:
    return (w["case_type"] + (f" · {w['teeth']}" if w["teeth"] else "") + (f" · {ARCHES[w['arch']]}" if w["arch"] else "")
            + (f" · {w['material']}" if w["material"] else ""))[:200]


@bp.route("/works/<int:work_id>/bill", methods=["POST"])
@login_required
def bill_work(work_id):
    """Start an invoice to the outside clinic for one work (or open the one it's already on)."""
    _need("lab.billing")
    conn = get_db()
    w = _work(conn, work_id)
    if w["invoice_id"]:
        return redirect(url_for("lab_works.invoice", invoice_id=w["invoice_id"]))
    if w["status"] == "cancelled":
        abort(400)
    client = conn.one("SELECT * FROM lab_clients WHERE id = ?", (w["client_id"],))
    with conn.transaction():
        iid = conn.insert("lab_invoices", {"lab_id": w["lab_id"], "client_id": w["client_id"], "clinic_name": w["clinic_name"],
                                           "doctor": w["doctor"] or (client["doctor"] if client else ""),
                                           "contact_number": w["contact_number"] or (client["contact_number"] if client else ""), "status": "draft",
                                           "due_on": (today() + timedelta(days=30)).isoformat(), "created_by": g.user.id,
                                           "created_at": now_str(), "updated_at": now_str()})
        price = w["price_cents"] or 0
        conn.insert("lab_invoice_items", {"invoice_id": iid, "work_id": w["id"], "description": _work_line(w), "qty": w["units"] or 1,
                                          "unit_price_cents": price, "discount_cents": 0, "amount_cents": price * (w["units"] or 1)})
        conn.update("lab_works", w["id"], {"invoice_id": iid, "updated_at": now_str()})
        _recalc(conn, iid)
        audit.record("lab_invoice_created", "lab_invoice", iid, f"Draft lab invoice for {w['number']} ({w['clinic_name']})")
    flash("Draft invoice started for this work. Check the units and price per unit, then add extras (e.g. casts) and any “less” lines.", "success")
    return redirect(url_for("lab_works.invoice", invoice_id=iid))


@bp.route("/invoices/<int:invoice_id>", methods=["GET", "POST"])
@login_required
def invoice(invoice_id):
    _need("lab.billing")
    conn = get_db()
    inv = _invoice(conn, invoice_id)
    if request.method == "POST":
        action = request.form.get("action")
        draft = inv["status"] == "draft"
        with conn.transaction():
            if action == "add_item" and draft:
                desc = clean(request.form.get("description"), 200)
                qty = to_int(request.form.get("qty")) or 1
                price = parse_money(request.form.get("unit_price"))
                idisc = parse_money(request.form.get("item_discount")) if request.form.get("item_discount") else 0
                less = 1 if request.form.get("is_less") else 0
                case_ids = {r["case_id"] for r in conn.all("SELECT case_id FROM lab_invoice_items WHERE invoice_id = ? AND case_id IS NOT NULL", (inv["id"],))}
                work_ids = {r["work_id"] for r in conn.all("SELECT work_id FROM lab_invoice_items WHERE invoice_id = ? AND work_id IS NOT NULL", (inv["id"],))}
                target = request.form.get("for") or ""
                case_id = to_int(target[1:]) if target.startswith("c") else to_int(request.form.get("case_id"))
                work_id = to_int(target[1:]) if target.startswith("w") else to_int(request.form.get("work_id"))
                case_id = case_id if case_id in case_ids else None
                work_id = work_id if work_id in work_ids and not case_id else None
                if len(desc) < 2 or price is None or price < 0 or qty < 1 or qty > 999 or idisc is None or idisc < 0 or idisc > price * qty:
                    flash("Enter a description, a quantity of 1 or more, a price, and a discount no bigger than the amount.", "error")
                else:
                    amount = price * qty - idisc
                    conn.insert("lab_invoice_items", {"invoice_id": inv["id"], "case_id": case_id, "work_id": work_id, "description": desc, "qty": qty,
                                                      "unit_price_cents": price, "discount_cents": 0 if less else idisc, "is_less": less,
                                                      "amount_cents": -amount if less else amount})
            elif action == "update_item" and draft:
                it = conn.one("SELECT * FROM lab_invoice_items WHERE id = ? AND invoice_id = ?", (to_int(request.form.get("item_id")), inv["id"]))
                price = parse_money(request.form.get("unit_price"))
                idisc = parse_money(request.form.get("item_discount")) if request.form.get("item_discount") else 0
                qty = to_int(request.form.get("qty")) or 1
                if not it or price is None or price < 0 or idisc is None or idisc < 0 or idisc > price * qty or qty < 1 or qty > 999:
                    flash("Check the quantity, price and discount.", "error")
                else:
                    amount = price * qty - idisc
                    desc = clean(request.form.get("description"), 200) or it["description"]
                    conn.execute("UPDATE lab_invoice_items SET description = ?, qty = ?, unit_price_cents = ?, discount_cents = ?, amount_cents = ? WHERE id = ?",
                                 (desc, qty, price, idisc, -amount if it["is_less"] else amount, it["id"]))
            elif action == "remove_item" and draft:
                it = conn.one("SELECT * FROM lab_invoice_items WHERE id = ? AND invoice_id = ?", (to_int(request.form.get("item_id")), inv["id"]))
                if it:
                    conn.execute("DELETE FROM lab_invoice_items WHERE id = ?", (it["id"],))
                    # the case or work is free again only when none of its lines are left on this invoice
                    if it["work_id"] and not conn.scalar("SELECT COUNT(*) FROM lab_invoice_items WHERE invoice_id = ? AND work_id = ?",
                                                         (inv["id"], it["work_id"])):
                        conn.update("lab_works", it["work_id"], {"invoice_id": None, "updated_at": now_str()})
                    if it["case_id"] and not conn.scalar("SELECT COUNT(*) FROM lab_invoice_items WHERE invoice_id = ? AND case_id = ?",
                                                         (inv["id"], it["case_id"])):
                        conn.execute("UPDATE lab_cases SET invoice_id = NULL WHERE id = ?", (it["case_id"],))
            elif action == "details" and draft:
                raw = clean(request.form.get("discount"), 20)
                sub = conn.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM lab_invoice_items WHERE invoice_id = ?", (inv["id"],)) or 0
                if raw.endswith("%"):
                    try:
                        pct = float(raw[:-1])
                        disc = round(sub * pct / 100) if 0 <= pct <= 100 else None
                    except ValueError:
                        disc = None
                else:
                    disc = parse_money(raw) if raw else 0
                due = parse_date(request.form.get("due_on"))
                if disc is None or disc < 0 or disc > sub:
                    flash("Enter a discount like 500 or 10%, no bigger than the subtotal.", "error")
                else:
                    conn.update("lab_invoices", inv["id"], {"discount_cents": disc, "discount_note": clean(request.form.get("discount_note"), 120),
                                                            "notes": clean(request.form.get("notes"), 1000), "due_on": due.isoformat() if due else None,
                                                            "doctor": clean(request.form.get("doctor"), 120),
                                                            "contact_number": clean(request.form.get("contact_number"), 60)})
                    flash("Saved.", "success")
            elif action == "issue" and draft:
                if not conn.scalar("SELECT COUNT(*) FROM lab_invoice_items WHERE invoice_id = ?", (inv["id"],)):
                    flash("Add at least one item first.", "error")
                else:
                    number = _next_number(conn, "lab_invoices", "LI")
                    conn.update("lab_invoices", inv["id"], {"number": number, "status": "issued", "issued_on": today().isoformat()})
                    audit.record("lab_invoice_issued", "lab_invoice", inv["id"], f"Issued lab invoice {number} to {inv['clinic_name']}")
                    flash(f"Issued as {number}.", "success")
            elif action == "void" and inv["status"] == "issued":
                reason = clean(request.form.get("reason"), 300)
                if conn.scalar("SELECT COUNT(*) FROM lab_payments WHERE invoice_id = ? AND status = 'ok'", (inv["id"],)):
                    flash("Void the payments on this invoice first.", "error")
                elif len(reason) < 3:
                    flash("Enter the reason for voiding.", "error")
                else:
                    conn.update("lab_invoices", inv["id"], {"status": "void", "void_reason": reason})
                    conn.execute("UPDATE lab_works SET invoice_id = NULL WHERE invoice_id = ?", (inv["id"],))
                    conn.execute("UPDATE lab_cases SET invoice_id = NULL WHERE invoice_id = ?", (inv["id"],))
                    audit.record("lab_invoice_voided", "lab_invoice", inv["id"], f"Voided {inv['number']}: {reason}")
                    flash("Invoice voided. Its works can be invoiced again.", "success")
            elif action == "delete" and draft:
                conn.execute("UPDATE lab_works SET invoice_id = NULL WHERE invoice_id = ?", (inv["id"],))
                conn.execute("UPDATE lab_cases SET invoice_id = NULL WHERE invoice_id = ?", (inv["id"],))
                conn.execute("DELETE FROM lab_invoice_items WHERE invoice_id = ?", (inv["id"],))
                conn.execute("DELETE FROM lab_invoices WHERE id = ?", (inv["id"],))
                audit.record("lab_invoice_deleted", "lab_invoice", inv["id"], "Deleted a draft lab invoice")
                flash("Draft deleted.", "success")
                return redirect(url_for("lab_works.invoices"))
            elif action == "pay" and inv["status"] == "issued":
                amt = parse_money(request.form.get("amount"))
                method = request.form.get("method")
                rec = parse_date(request.form.get("received_on")) or today()
                balance = inv["total_cents"] - inv["paid_cents"]
                if amt is None or amt <= 0 or amt > balance:
                    flash(f"Enter an amount between ₱0.01 and the balance of ₱{balance / 100:,.2f}.", "error")
                elif method not in METHODS:
                    flash("Choose how it was paid.", "error")
                elif rec > today():
                    flash("The payment date can't be in the future.", "error")
                else:
                    receipt = _next_number(conn, "lab_payments", "AR")
                    pid = conn.insert("lab_payments", {"invoice_id": inv["id"], "receipt_no": receipt, "amount_cents": amt, "method": method,
                                                       "reference": clean(request.form.get("reference"), 80), "received_on": rec.isoformat(),
                                                       "received_by": g.user.id, "status": "ok", "created_at": now_str()})
                    audit.record("lab_payment_recorded", "lab_invoice", inv["id"], f"Payment {receipt} of ₱{amt / 100:,.2f} on {inv['number']}")
                    _recalc(conn, inv["id"])
                    flash(f"Payment recorded. Receipt {receipt}.", "success")
                    return redirect(url_for("lab_works.invoice", invoice_id=inv["id"], receipt=pid))
            elif action == "void_payment":
                p = conn.one("SELECT * FROM lab_payments WHERE id = ? AND invoice_id = ? AND status = 'ok'", (to_int(request.form.get("payment_id")), inv["id"]))
                reason = clean(request.form.get("reason"), 300)
                if p and len(reason) >= 3:
                    conn.execute("UPDATE lab_payments SET status = 'void', void_reason = ? WHERE id = ?", (reason, p["id"]))
                    audit.record("lab_payment_voided", "lab_invoice", inv["id"], f"Voided receipt {p['receipt_no']}: {reason}")
                    flash(f"Receipt {p['receipt_no']} voided.", "success")
                else:
                    flash("Enter the reason for voiding the payment.", "error")
            else:
                abort(400)
            _recalc(conn, inv["id"])
            if action in ("add_item", "update_item", "remove_item"):
                sync_case_prices(conn, inv["id"])
        return redirect(url_for("lab_works.invoice", invoice_id=inv["id"]))
    inv = _invoice(conn, invoice_id)
    items = conn.all("SELECT * FROM lab_invoice_items WHERE invoice_id = ? ORDER BY id", (inv["id"],))
    groups = item_groups(conn, items)
    payments = conn.all("SELECT p.*, u.name AS by_name FROM lab_payments p LEFT JOIN users u ON u.id = p.received_by WHERE p.invoice_id = ? ORDER BY p.id",
                        (inv["id"],))
    return render_template("staff/lab_works/invoice.html", inv=inv, items=items, groups=groups, payments=payments,
                           price_list=price_items(conn, [inv["lab_id"]]), pay=pay_status(inv), labels=PAY_LABELS,
                           methods=METHODS, today=today().isoformat(), new_receipt=to_int(request.args.get("receipt")))


def _lab_header(conn, lab_id):
    lab = conn.one("SELECT * FROM laboratories WHERE id = ?", (lab_id,))
    return {"name": lab_display(lab["name"]), "address": lab["address"], "phone": lab["phone"]}


@bp.route("/invoices/<int:invoice_id>/print")
@login_required
def invoice_print(invoice_id):
    _need("lab.billing")
    conn = get_db()
    inv = _invoice(conn, invoice_id)
    items = conn.all("SELECT * FROM lab_invoice_items WHERE invoice_id = ? ORDER BY id", (inv["id"],))
    return render_template("staff/lab_works/invoice_print.html", inv=inv, items=items, groups=item_groups(conn, items), lab=_lab_header(conn, inv["lab_id"]), pay=pay_status(inv),
                           labels=PAY_LABELS)


@bp.route("/receipts/<int:payment_id>/print")
@login_required
def receipt_print(payment_id):
    _need("lab.billing")
    conn = get_db()
    p = conn.one("SELECT * FROM lab_payments WHERE id = ?", (payment_id,))
    if not p:
        abort(404)
    inv = _invoice(conn, p["invoice_id"])
    by = conn.one("SELECT name FROM users WHERE id = ?", (p["received_by"],))
    return render_template("staff/lab_works/receipt_print.html", p=p, inv=inv, lab=_lab_header(conn, inv["lab_id"]), methods=METHODS,
                           by=by["name"] if by else "", balance=inv["total_cents"] - inv["paid_cents"])


# ---------------------------------------------------------------------------
# Technician commissions (manual), on outside works and branch lab cases
# ---------------------------------------------------------------------------

@bp.route("/commission", methods=["POST"])
@login_required
def commission():
    from ..lab_commission import technicians
    conn = get_db()
    if not (g.user.is_super_admin or g.user.can("lab.commission")):
        abort(403)
    work_id, case_id = to_int(request.form.get("work_id")), to_int(request.form.get("case_id"))
    if work_id:
        item = conn.one("SELECT id, lab_id, number AS ref FROM lab_works WHERE id = ?", (work_id,))
        back = url_for("lab_works.work", work_id=work_id)
    elif case_id:
        item = conn.one("SELECT id, lab_id, '#' || id AS ref FROM lab_cases WHERE id = ?", (case_id,))
        back = url_for("labs.case", case_id=case_id)
    else:
        abort(400)
    if not item or (not g.user.is_super_admin and item["lab_id"] not in _lab_ids()):
        abort(404)
    if request.form.get("action") == "remove":
        c = conn.one("SELECT * FROM lab_commissions WHERE id = ? AND (work_id = ? OR case_id = ?)",
                     (to_int(request.form.get("commission_id")), work_id or 0, case_id or 0))
        if c:
            conn.execute("DELETE FROM lab_commissions WHERE id = ?", (c["id"],))
            audit.record("lab_commission_removed", "lab_commission", c["id"], f"Removed technician commission on {item['ref']}",
                         {"amount_cents": c["amount_cents"], "employee_id": c["employee_id"]})
            flash("Commission removed.", "success")
        return redirect(back)
    emp_id = to_int(request.form.get("employee_id"))
    amt = parse_money(request.form.get("amount"))
    if not any(t["id"] == emp_id for t in technicians(conn)):
        flash("Choose the technician.", "error")
    elif amt is None or amt <= 0:
        flash("Enter the commission amount, like 150 or 1,200.", "error")
    else:
        cid = conn.insert("lab_commissions", {"employee_id": emp_id, "work_id": work_id, "case_id": case_id, "amount_cents": amt,
                                              "note": clean(request.form.get("note"), 200), "created_by": g.user.id, "created_at": now_str()})
        audit.record("lab_commission_added", "lab_commission", cid, f"Technician commission ₱{amt / 100:,.2f} on {item['ref']}",
                     {"employee_id": emp_id})
        flash("Commission added. It counts in payroll when the work is delivered.", "success")
    return redirect(back)


# ---------------------------------------------------------------------------
# Collection report
# ---------------------------------------------------------------------------

@bp.route("/collections")
@login_required
def collections():
    _need("lab.billing")
    conn = get_db()
    ids = _lab_ids()
    end = parse_date(request.args.get("to")) or today()
    start = parse_date(request.args.get("from")) or end.replace(day=1)
    if start > end:
        start, end = end, start
    client = to_int(request.args.get("client"))
    kind = request.args.get("kind") if request.args.get("kind") in KINDS else ""
    where, args = [f"i.lab_id IN ({_in(ids)})", "p.status = 'ok'", "p.received_on BETWEEN ? AND ?"], [*ids, start.isoformat(), end.isoformat()]
    if kind:
        where.append(_kind_sql(kind)[5:])
    if client:
        where.append("i.client_id = ?")
        args.append(client)
    rows = conn.all("SELECT p.*, i.number AS invoice_number, i.clinic_name, i.client_id, u.name AS by_name, "
                    "(SELECT branch_id FROM lab_clients WHERE id = i.client_id) AS branch_id FROM lab_payments p "
                    "JOIN lab_invoices i ON i.id = p.invoice_id LEFT JOIN users u ON u.id = p.received_by "
                    f"WHERE {' AND '.join(where)} ORDER BY p.received_on, p.id", args)
    if request.args.get("format") == "csv":
        buf = io.StringIO()
        wr = csv.writer(buf)
        wr.writerow(["Date", "Receipt", "Invoice", "Dental clinic", "Type", "Method", "Reference", "Amount (PHP)", "Received by"])
        safe = lambda x: ("'" + x) if isinstance(x, str) and x[:1] in ("=", "+", "-", "@") else x  # noqa: E731
        for r in rows:
            wr.writerow([safe(x) for x in (r["received_on"], r["receipt_no"], r["invoice_number"], r["clinic_name"],
                                            "Branch" if r["branch_id"] else "Outside clinic", METHODS.get(r["method"], r["method"]),
                                            r["reference"], r["amount_cents"] / 100, r["by_name"] or "")])
        wr.writerow(["", "", "", "", "", "", "Total", sum(r["amount_cents"] for r in rows) / 100, ""])
        audit.record("lab_collections_exported", "lab_invoice", None, f"Exported lab collections {start} to {end}")
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="lab-collections{"-" + kind if kind else ""}-{start}-to-{end}.csv"', "Cache-Control": "no-store"})
    by_method, by_clinic, by_day = {}, {}, {}
    by_kind = {"outside": 0, "branch": 0}
    for r in rows:
        by_kind["branch" if r["branch_id"] else "outside"] += r["amount_cents"]
        by_method[r["method"]] = by_method.get(r["method"], 0) + r["amount_cents"]
        by_clinic[r["clinic_name"]] = by_clinic.get(r["clinic_name"], 0) + r["amount_cents"]
        by_day[r["received_on"]] = by_day.get(r["received_on"], 0) + r["amount_cents"]
    invoiced = conn.scalar(f"SELECT COALESCE(SUM(total_cents), 0) FROM lab_invoices WHERE lab_id IN ({_in(ids)}) AND status = 'issued' "
                           "AND issued_on BETWEEN ? AND ?" + (" AND client_id = ?" if client else "") + _kind_sql(kind, "lab_invoices"),
                           [*ids, start.isoformat(), end.isoformat()] + ([client] if client else [])) or 0
    # Outstanding balances as of today, with age from the invoice's due date
    open_rows = conn.all(f"SELECT * FROM lab_invoices WHERE lab_id IN ({_in(ids)}) AND status = 'issued' AND total_cents > paid_cents"
                         + (" AND client_id = ?" if client else "") + _kind_sql(kind, "lab_invoices") + " ORDER BY clinic_name, issued_on", [*ids] + ([client] if client else []))
    t = today().isoformat()
    outstanding = {}
    for i in open_rows:
        bal = i["total_cents"] - i["paid_cents"]
        o = outstanding.setdefault(i["clinic_name"], {"client_id": i["client_id"], "current": 0, "overdue": 0, "invoices": 0})
        o["invoices"] += 1
        o["overdue" if i["due_on"] and i["due_on"] < t else "current"] += bal
    clients = conn.all(f"SELECT id, clinic_name FROM lab_clients WHERE lab_id IN ({_in(ids)})"
                       + (" AND branch_id IS NULL" if kind == "outside" else " AND branch_id IS NOT NULL" if kind == "branch" else "")
                       + " ORDER BY clinic_name", ids)
    return render_template("staff/lab_works/collections.html", rows=rows, start=start, end=end, client=client, clients=clients, methods=METHODS,
                           kind=kind, kinds=KINDS, by_kind=by_kind,
                           by_method=sorted(by_method.items(), key=lambda x: -x[1]), by_clinic=sorted(by_clinic.items(), key=lambda x: -x[1]),
                           by_day=sorted(by_day.items()), total=sum(r["amount_cents"] for r in rows), invoiced=invoiced,
                           outstanding=sorted(outstanding.items()), out_total=sum(o["current"] + o["overdue"] for o in outstanding.values()))

"""Prescriptions and certificates (create, edit, delete, print)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..permissions import can_see_clinical
from ..util import clean, now_str, parse_date, to_int, today
from .common import dentists

bp = Blueprint("docs", __name__, url_prefix="/staff")

MAX_RX_LINES = 8
CERT_KINDS = {
    "dental": ("Dental certificate",
               "This is to certify that {patient}, {age}, was seen and treated at Dental Haven {branch} on {date}.\n\n"
               "Procedure done: \n\nThe patient is advised to rest for ___ day(s).\n\n"
               "This certification is issued upon the patient's request for whatever legal purpose it may serve, except medico-legal."),
    "clearance": ("Dental clearance",
                  "This is to certify that {patient}, {age}, has been examined at Dental Haven {branch} on {date} and is "
                  "dentally fit / cleared for: \n\nRemarks: "),
    "fit": ("Fit to work / school",
            "This is to certify that {patient}, {age}, was treated at Dental Haven {branch} on {date} and is fit to return "
            "to work / school on ____________."),
    "other": ("Certificate", "This is to certify that {patient}, {age}, "),
}


def _patient(patient_id):
    conn = get_db()
    if not can_see_clinical(conn, g.user, patient_id):
        abort(403)
    p = conn.one("SELECT p.*, b.name AS branch FROM patients p LEFT JOIN branches b ON b.id = p.preferred_branch_id WHERE p.id = ?",
                 (patient_id,))
    if not p:
        abort(404)
    return p


def _age(birth):
    d = parse_date(birth)
    if not d:
        return "of legal age"
    t = today()
    return f"{t.year - d.year - ((t.month, t.day) < (d.month, d.day))} years old"


def _rx_lines(form):
    lines = []
    for i in range(MAX_RX_LINES):
        med = clean(form.get(f"medicine_{i}"), 200)
        if med:
            lines.append({"medicine": med, "dosage": clean(form.get(f"dosage_{i}"), 120),
                          "quantity": clean(form.get(f"quantity_{i}"), 40), "instructions": clean(form.get(f"instructions_{i}"), 300)})
    return lines


def _prescriber_choices(p):
    ds = dentists()
    if g.user.role == "dentist":
        ds = [d for d in ds if d["id"] == g.user.id]
    return ds


# ---------------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------------

@bp.route("/patients/<int:patient_id>/prescriptions/new", methods=["GET", "POST"])
@require("rx.create")
def rx_new(patient_id):
    return _rx_form(patient_id, None)


@bp.route("/prescriptions/<int:rx_id>/edit", methods=["GET", "POST"])
@require("rx.edit")
def rx_edit(rx_id):
    rx = get_db().one("SELECT * FROM prescriptions WHERE id = ? AND deleted = 0", (rx_id,))
    if not rx:
        abort(404)
    return _rx_form(rx["patient_id"], rx)


def _rx_form(patient_id, rx):
    conn = get_db()
    p = _patient(patient_id)
    choices = _prescriber_choices(p)
    items = conn.all("SELECT * FROM prescription_items WHERE prescription_id = ? ORDER BY seq", (rx["id"],)) if rx else []
    v = {"prescriber_id": rx["prescriber_id"] if rx else (g.user.id if g.user.role == "dentist" else None),
         "prescribed_on": rx["prescribed_on"] if rx else today().isoformat(), "notes": rx["notes"] if rx else "", "items": items}
    errors = []
    if request.method == "POST":
        lines = _rx_lines(request.form)
        v = {"prescriber_id": to_int(request.form.get("prescriber_id")), "prescribed_on": clean(request.form.get("prescribed_on"), 10),
             "notes": clean(request.form.get("notes"), 1000), "items": lines}
        if not any(c["id"] == v["prescriber_id"] for c in choices):
            errors.append("Choose the prescribing dentist.")
        if not parse_date(v["prescribed_on"]):
            errors.append("Enter the date.")
        if not lines:
            errors.append("Add at least one medicine.")
        if not errors:
            with conn.transaction():
                if rx:
                    rx_id = rx["id"]
                    conn.update("prescriptions", rx_id, {"prescriber_id": v["prescriber_id"], "prescribed_on": v["prescribed_on"],
                                                         "notes": v["notes"], "updated_at": now_str()})
                    conn.execute("DELETE FROM prescription_items WHERE prescription_id = ?", (rx_id,))
                    action = "prescription_edited"
                else:
                    rx_id = conn.insert("prescriptions", {"patient_id": patient_id, "branch_id": g.user.active_branch_id or p["preferred_branch_id"],
                                                          "prescriber_id": v["prescriber_id"], "prescribed_on": v["prescribed_on"],
                                                          "notes": v["notes"], "created_by": g.user.id, "created_at": now_str()})
                    action = "prescription_created"
                for i, line in enumerate(lines):
                    conn.insert("prescription_items", {"prescription_id": rx_id, "seq": i, **line})
                audit.record(action, "patient", patient_id, f"{'Edited' if rx else 'Created'} prescription #{rx_id}",
                             {"prescription_id": rx_id, "items": lines})
            flash("Prescription saved.", "success")
            return redirect(url_for("docs.rx_print", rx_id=rx_id))
    return render_template("staff/docs/rx_form.html", p=p, rx=rx, v=v, errors=errors, choices=choices, max_lines=MAX_RX_LINES)


@bp.route("/prescriptions/<int:rx_id>/delete", methods=["POST"])
@require("rx.delete")
def rx_delete(rx_id):
    conn = get_db()
    rx = conn.one("SELECT * FROM prescriptions WHERE id = ? AND deleted = 0", (rx_id,))
    if not rx:
        abort(404)
    _patient(rx["patient_id"])
    conn.execute("UPDATE prescriptions SET deleted = 1, updated_at = ? WHERE id = ?", (now_str(), rx_id))
    audit.record("prescription_deleted", "patient", rx["patient_id"], f"Deleted prescription #{rx_id}")
    flash("Prescription deleted.", "success")
    return redirect(url_for("patients.detail", patient_id=rx["patient_id"], tab="rx"))


@bp.route("/prescriptions/<int:rx_id>/print")
@require("clinical.view")
def rx_print(rx_id):
    conn = get_db()
    rx = conn.one("SELECT r.*, u.name AS prescriber, u.license_no, u.ptr_no, u.s2_no, b.name AS branch, b.address AS branch_address, "
                  "b.phone AS branch_phone FROM prescriptions r LEFT JOIN users u ON u.id = r.prescriber_id "
                  "LEFT JOIN branches b ON b.id = r.branch_id WHERE r.id = ?", (rx_id,))
    if not rx:
        abort(404)
    p = _patient(rx["patient_id"])
    items = conn.all("SELECT * FROM prescription_items WHERE prescription_id = ? ORDER BY seq", (rx_id,))
    audit.record("prescription_printed", "patient", p["id"], f"Opened prescription #{rx_id} for printing")
    return render_template("staff/docs/rx_print.html", rx=rx, p=p, items=items, age=_age(p["birth_date"]))


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

@bp.route("/patients/<int:patient_id>/certificates/new", methods=["GET", "POST"])
@require("cert.create")
def cert_new(patient_id):
    return _cert_form(patient_id, None)


@bp.route("/certificates/<int:cert_id>/edit", methods=["GET", "POST"])
@require("cert.edit")
def cert_edit(cert_id):
    c = get_db().one("SELECT * FROM certificates WHERE id = ? AND deleted = 0", (cert_id,))
    if not c:
        abort(404)
    return _cert_form(c["patient_id"], c)


def _cert_form(patient_id, c):
    conn = get_db()
    p = _patient(patient_id)
    choices = _prescriber_choices(p)
    kind = request.args.get("kind", "dental") if not c else c["kind"]
    if kind not in CERT_KINDS:
        kind = "dental"
    title, template = CERT_KINDS[kind]
    branch = conn.one("SELECT name FROM branches WHERE id = ?", (g.user.active_branch_id or p["preferred_branch_id"],))
    body = template.format(patient=f"{p['first_name']} {p['last_name']}", age=_age(p["birth_date"]),
                           branch=branch["name"] if branch else "", date=today().strftime("%B %d, %Y"))
    v = {"kind": kind, "title": c["title"] if c else title, "body": c["body"] if c else body,
         "issued_on": c["issued_on"] if c else today().isoformat(),
         "issued_by": c["issued_by"] if c else (g.user.id if g.user.role == "dentist" else None)}
    errors = []
    if request.method == "POST":
        v = {"kind": request.form.get("kind") if request.form.get("kind") in CERT_KINDS else kind,
             "title": clean(request.form.get("title"), 150), "body": clean(request.form.get("body"), 6000),
             "issued_on": clean(request.form.get("issued_on"), 10), "issued_by": to_int(request.form.get("issued_by"))}
        if not v["title"] or not v["body"]:
            errors.append("Enter a title and the certificate text.")
        if "____" in v["body"] or "___ " in v["body"]:
            errors.append("Fill in the blanks (____) in the certificate text.")
        if not parse_date(v["issued_on"]):
            errors.append("Enter the date issued.")
        if not any(d["id"] == v["issued_by"] for d in choices):
            errors.append("Choose the dentist signing the certificate.")
        if not errors:
            if c:
                cert_id = c["id"]
                conn.update("certificates", cert_id, {**{k: v[k] for k in ("kind", "title", "body", "issued_on", "issued_by")},
                                                      "updated_at": now_str()})
                audit.record("certificate_edited", "patient", patient_id, f"Edited certificate #{cert_id}",
                             audit.diff(dict(c), v, ("title", "body", "issued_on", "issued_by")))
            else:
                cert_id = conn.insert("certificates", {"patient_id": patient_id, "branch_id": g.user.active_branch_id or p["preferred_branch_id"],
                                                       **{k: v[k] for k in ("kind", "title", "body", "issued_on", "issued_by")},
                                                       "created_by": g.user.id, "created_at": now_str()})
                audit.record("certificate_created", "patient", patient_id, f"Created certificate #{cert_id}: {v['title']}")
            flash("Certificate saved.", "success")
            return redirect(url_for("docs.cert_print", cert_id=cert_id))
    return render_template("staff/docs/cert_form.html", p=p, c=c, v=v, errors=errors, choices=choices, kinds=CERT_KINDS)


@bp.route("/certificates/<int:cert_id>/delete", methods=["POST"])
@require("cert.delete")
def cert_delete(cert_id):
    conn = get_db()
    c = conn.one("SELECT * FROM certificates WHERE id = ? AND deleted = 0", (cert_id,))
    if not c:
        abort(404)
    _patient(c["patient_id"])
    conn.execute("UPDATE certificates SET deleted = 1, updated_at = ? WHERE id = ?", (now_str(), cert_id))
    audit.record("certificate_deleted", "patient", c["patient_id"], f"Deleted certificate #{cert_id}")
    flash("Certificate deleted.", "success")
    return redirect(url_for("patients.detail", patient_id=c["patient_id"], tab="rx"))


@bp.route("/certificates/<int:cert_id>/print")
@require("clinical.view")
def cert_print(cert_id):
    conn = get_db()
    c = conn.one("SELECT c.*, u.name AS dentist, u.license_no, u.ptr_no, b.name AS branch, b.address AS branch_address, "
                 "b.phone AS branch_phone FROM certificates c LEFT JOIN users u ON u.id = c.issued_by "
                 "LEFT JOIN branches b ON b.id = c.branch_id WHERE c.id = ?", (cert_id,))
    if not c:
        abort(404)
    p = _patient(c["patient_id"])
    audit.record("certificate_printed", "patient", p["id"], f"Opened certificate #{cert_id} for printing")
    return render_template("staff/docs/cert_print.html", c=c, p=p)

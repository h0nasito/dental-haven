"""Patient profiles, medical/dental history, clinical notes, procedures, treatment plans and documents."""
from __future__ import annotations

import re

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..permissions import can_see_clinical, can_see_patient, patient_scope
from ..uploads import document_path, save_document
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import branches_for_user, dentists, paginate, services

bp = Blueprint("patients", __name__, url_prefix="/staff/patients")

PROFILE_FIELDS = ["first_name", "middle_name", "last_name", "occupation", "civil_status", "emergency_contact", "emergency_phone", "birth_date", "sex", "phone", "email", "address", "preferred_branch_id",
                  "consent_privacy", "consent_marketing", "contact_sms", "contact_email", "contact_messenger",
                  "opt_out_all", "preferred_channel", "admin_notes"]
HISTORY_FIELDS = ["medical_conditions", "allergies", "medications", "dental_history", "other_notes"]
DOC_CATEGORIES = {
    "xray": ("X-ray / imaging", True), "lab": ("Lab / prosthesis record", True), "referral": ("Referral letter", True),
    "clinical_photo": ("Clinical photo", True), "consent_form": ("Signed consent form", False),
    "id": ("ID / HMO card", False), "other": ("Other", True),
}
PLAN_STATUSES = ["draft", "presented", "accepted", "in_progress", "completed", "declined"]
ITEM_STATUSES = ["pending", "scheduled", "done", "declined"]
CONTACT_FIELDS = ["phone", "email", "address", "emergency_contact", "emergency_phone"]
PHONE_RE = re.compile(r"^[0-9+()\-\s]{7,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def next_chart_no(conn) -> str:
    n = (conn.scalar("SELECT MAX(id) FROM patients") or 0) + 1
    while conn.one("SELECT id FROM patients WHERE chart_no = ?", (f"DH-{n:06d}",)):
        n += 1
    return f"DH-{n:06d}"


def _load(patient_id):
    conn = get_db()
    if not can_see_patient(conn, g.user, patient_id):
        # don't reveal whether the record exists
        abort(404 if not conn.one("SELECT id FROM patients WHERE id = ?", (patient_id,)) else 403)
    return conn.one("SELECT p.*, b.name AS preferred_branch FROM patients p LEFT JOIN branches b ON b.id = p.preferred_branch_id "
                    "WHERE p.id = ?", (patient_id,))


def _require_clinical(patient_id, edit=False, perm=None):
    if not can_see_clinical(get_db(), g.user, patient_id):
        abort(403)
    if edit and not g.user.can(perm or "clinical.edit"):
        abort(403)


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------

@bp.route("/", methods=["GET", "POST"])
@require("patients.view")
def index():
    conn = get_db()
    frag, params = patient_scope(g.user, "p")
    q = clean(request.form.get("q"), 80) if request.method == "POST" else ""
    where, args = [frag, "p.active = 1"], list(params)
    if q:
        like = f"%{q.lower()}%"
        where.append("(lower(p.first_name || ' ' || p.last_name) LIKE ? OR lower(p.last_name || ', ' || p.first_name) LIKE ? "
                     "OR p.phone LIKE ? OR lower(p.chart_no) LIKE ? OR lower(p.email) LIKE ? OR p.legacy_id = ? "
                     "OR lower(p.first_name || ' ' || p.middle_name || ' ' || p.last_name) LIKE ?)")
        args += [like, like, like, like, like, q, like]
    total = conn.scalar(f"SELECT COUNT(*) FROM patients p WHERE {' AND '.join(where)}", args)
    pg = paginate(total, 30)
    rows = conn.all(
        "SELECT p.*, b.name AS branch, (SELECT MAX(start_at) FROM appointments a WHERE a.patient_id = p.id AND a.status = 'completed') AS last_visit, "
        "(SELECT MIN(start_at) FROM appointments a WHERE a.patient_id = p.id AND a.status IN ('requested','confirmed') AND a.start_at >= ?) AS next_visit "
        f"FROM patients p LEFT JOIN branches b ON b.id = p.preferred_branch_id WHERE {' AND '.join(where)} "
        "ORDER BY p.last_name, p.first_name LIMIT ? OFFSET ?", [today().isoformat(), *args, pg["limit"], pg["offset"]])
    return render_template("staff/patients/index.html", rows=rows, pg=pg, q=q)


# ---------------------------------------------------------------------------
# Create / edit profile
# ---------------------------------------------------------------------------

def _profile_from_form(form):
    return {
        "first_name": clean(form.get("first_name"), 80), "last_name": clean(form.get("last_name"), 80),
        "middle_name": clean(form.get("middle_name"), 80), "occupation": clean(form.get("occupation"), 120),
        "civil_status": clean(form.get("civil_status"), 40), "emergency_contact": clean(form.get("emergency_contact"), 120),
        "emergency_phone": clean(form.get("emergency_phone"), 25),
        "birth_date": clean(form.get("birth_date"), 10) or None, "sex": clean(form.get("sex"), 20),
        "phone": clean(form.get("phone"), 25), "email": clean(form.get("email"), 200).lower(),
        "address": clean(form.get("address"), 300), "preferred_branch_id": to_int(form.get("preferred_branch_id")),
        "consent_privacy": 1 if form.get("consent_privacy") else 0,
        "consent_marketing": 1 if form.get("consent_marketing") else 0,
        "contact_sms": 1 if form.get("contact_sms") else 0, "contact_email": 1 if form.get("contact_email") else 0,
        "contact_messenger": 1 if form.get("contact_messenger") else 0, "opt_out_all": 1 if form.get("opt_out_all") else 0,
        "preferred_channel": form.get("preferred_channel") if form.get("preferred_channel") in ("sms", "email", "messenger", "call") else "",
        "admin_notes": clean(form.get("admin_notes"), 1000),
    }


def _validate_profile(v):
    errors = {}
    if not v["first_name"]:
        errors["first_name"] = "Enter a first name."
    if not v["last_name"]:
        errors["last_name"] = "Enter a last name."
    if v["birth_date"]:
        d = parse_date(v["birth_date"])
        if not d or d > today() or d.year < 1900:
            errors["birth_date"] = "Enter a valid date of birth."
    if v["phone"] and not PHONE_RE.match(v["phone"]):
        errors["phone"] = "Check the mobile number."
    if v["email"] and not EMAIL_RE.match(v["email"]):
        errors["email"] = "Check the email address."
    if not v["preferred_branch_id"] or not g.user.in_branch(v["preferred_branch_id"]):
        errors["preferred_branch_id"] = "Choose one of your branches."
    if v["contact_sms"] and not v["phone"]:
        errors["contact_sms"] = "Add a mobile number to allow SMS."
    if v["contact_email"] and not v["email"]:
        errors["contact_email"] = "Add an email to allow email."
    return errors


@bp.route("/new", methods=["GET", "POST"])
@require("patients.manage")
def new():
    conn = get_db()
    v = {f: "" for f in PROFILE_FIELDS}
    v.update({"preferred_branch_id": g.user.active_branch_id or (g.user.branch_ids[0] if g.user.branch_ids else None),
              "consent_privacy": 0, "contact_sms": 0, "contact_email": 0, "contact_messenger": 0, "opt_out_all": 0,
              "consent_marketing": 0})
    errors = {}
    if request.method == "POST":
        v = _profile_from_form(request.form)
        errors = _validate_profile(v)
        if not errors:
            dup = conn.one("SELECT id FROM patients WHERE lower(first_name) = lower(?) AND lower(last_name) = lower(?) "
                           "AND (birth_date = ? OR (phone != '' AND phone = ?))",
                           (v["first_name"], v["last_name"], v["birth_date"] or "-", v["phone"] or "-"))
            if dup and not request.form.get("confirm_duplicate"):
                errors["_form"] = ["A patient with the same name and birth date or phone already exists. Check the list "
                                   "first, or tick 'This is a different person' to continue."]
                errors["_dup"] = True
        if not errors:
            data = dict(v)
            data.update({"chart_no": next_chart_no(conn), "source": "staff", "created_at": now_str(),
                         "created_by": g.user.id, "updated_at": now_str(),
                         "consent_privacy_at": now_str() if v["consent_privacy"] else None})
            with conn.transaction():
                pid = conn.insert("patients", data)
                conn.execute("INSERT INTO patient_history (patient_id, updated_at, updated_by) VALUES (?, ?, ?)",
                             (pid, now_str(), g.user.id))
                audit.record("patient_created", "patient", pid, f"Registered {data['chart_no']}", branch_id=v["preferred_branch_id"])
            flash("Patient registered.", "success")
            if request.args.get("then") == "book" and g.user.can("appointments.manage"):
                return redirect(url_for("sched.appointment_new", patient_id=pid))
            return redirect(url_for("patients.detail", patient_id=pid))
    return render_template("staff/patients/form.html", v=v, errors=errors, p=None, branches=branches_for_user(g.user))


@bp.route("/<int:patient_id>/edit", methods=["GET", "POST"])
@require("patients.manage")
def edit(patient_id):
    conn = get_db()
    p = _load(patient_id)
    v = dict(p)
    errors = {}
    if request.method == "POST":
        v = _profile_from_form(request.form)
        if not g.user.can("patients.contact"):
            for k in CONTACT_FIELDS:  # fields weren't shown, so keep what's stored
                v[k] = p[k]
        errors = _validate_profile(v)
        if not errors:
            changes = audit.diff(dict(p), v, PROFILE_FIELDS)
            if changes:
                upd = dict(v)
                upd["updated_at"] = now_str()
                if v["consent_privacy"] and not p["consent_privacy"]:
                    upd["consent_privacy_at"] = now_str()
                conn.update("patients", patient_id, upd)
                audit.record("patient_updated", "patient", patient_id, "Updated profile: " + ", ".join(changes), changes,
                             v["preferred_branch_id"])
                if "opt_out_all" in changes and v["opt_out_all"]:
                    conn.execute("UPDATE reminders SET status='skipped_opt_out', result_note='Patient opted out' "
                                 "WHERE patient_id = ? AND status = 'pending'", (patient_id,))
            flash("Profile saved.", "success")
            return redirect(url_for("patients.detail", patient_id=patient_id))
    return render_template("staff/patients/form.html", v=v, errors=errors, p=p, branches=branches_for_user(g.user))


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@bp.route("/<int:patient_id>")
@require("patients.view")
def detail(patient_id):
    conn = get_db()
    p = _load(patient_id)
    tab = request.args.get("tab", "overview")
    clinical = can_see_clinical(conn, g.user, patient_id)
    if tab == "clinical" and not clinical:
        abort(403)
    ctx = {"p": p, "tab": tab, "clinical": clinical}
    appt_where = "a.patient_id = ?"
    appt_params = [patient_id]
    if g.user.role == "dentist":
        pass  # dentists see the visit list for assigned patients
    elif not g.user.is_super_admin:
        marks = ",".join("?" for _ in g.user.branch_ids) or "NULL"
        appt_where += f" AND a.branch_id IN ({marks})"
        appt_params += g.user.branch_ids
    ctx["appointments"] = conn.all(
        "SELECT a.*, s.name AS service, u.name AS dentist, b.name AS branch FROM appointments a JOIN services s ON s.id = a.service_id "
        f"LEFT JOIN users u ON u.id = a.dentist_id JOIN branches b ON b.id = a.branch_id WHERE {appt_where} ORDER BY a.start_at DESC LIMIT 50",
        appt_params)
    ctx["followups"] = conn.all("SELECT f.*, u.name AS assignee FROM follow_ups f LEFT JOIN users u ON u.id = f.assignee_id "
                                "WHERE f.patient_id = ? ORDER BY f.status, f.due_at LIMIT 30", (patient_id,)) \
        if g.user.can("followups.view") else []
    if g.user.can("billing.view"):
        ctx["invoices"] = conn.all(
            "SELECT i.*, b.name AS branch, (SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END),0) "
            "FROM payments WHERE invoice_id = i.id AND status = 'valid') AS paid FROM invoices i JOIN branches b ON b.id = i.branch_id "
            "WHERE i.patient_id = ? ORDER BY i.created_at DESC", (patient_id,))
        ctx["balance"] = sum((i["total_cents"] - i["paid"]) for i in ctx["invoices"] if i["status"] == "issued")
        from ..billing import credit_balance
        ctx["credit"] = credit_balance(conn, patient_id)
        ctx["credit_rows"] = conn.all("SELECT c.*, u.name AS by_name FROM patient_credits c LEFT JOIN users u ON u.id = c.created_by "
                                      "WHERE c.patient_id = ? ORDER BY c.id DESC LIMIT 30", (patient_id,))
        ctx["my_branches"] = branches_for_user(g.user)
        ctx["legacy_bills"] = conn.all("SELECT * FROM legacy_bills WHERE patient_id = ? ORDER BY bill_date DESC, id DESC LIMIT 100", (patient_id,))
        ctx["legacy_total"] = conn.one("SELECT COUNT(*) AS n, COALESCE(SUM(total_cents), 0) AS total FROM legacy_bills WHERE patient_id = ?", (patient_id,))
    ctx["assigned"] = conn.all("SELECT u.id, u.name FROM patient_assignments pa JOIN users u ON u.id = pa.dentist_id "
                               "WHERE pa.patient_id = ? ORDER BY u.name", (patient_id,))
    if clinical:
        ctx["history"] = conn.one("SELECT h.*, u.name AS updated_by_name FROM patient_history h LEFT JOIN users u ON u.id = h.updated_by "
                                  "WHERE h.patient_id = ?", (patient_id,)) or {}
        ctx["notes"] = conn.all("SELECT n.*, u.name AS author, a.start_at AS appt_at FROM clinical_notes n JOIN users u ON u.id = n.author_id "
                                "LEFT JOIN appointments a ON a.id = n.appointment_id WHERE n.patient_id = ? ORDER BY n.created_at DESC",
                                (patient_id,))
        ctx["procedures"] = conn.all("SELECT pr.*, u.name AS dentist, s.name AS service FROM procedures pr LEFT JOIN users u ON u.id = pr.performed_by "
                                     "LEFT JOIN services s ON s.id = pr.service_id WHERE pr.patient_id = ? ORDER BY COALESCE(pr.performed_at, pr.created_at) DESC",
                                     (patient_id,))
        plans = conn.all("SELECT t.*, u.name AS dentist FROM treatment_plans t LEFT JOIN users u ON u.id = t.dentist_id "
                         "WHERE t.patient_id = ? ORDER BY t.created_at DESC", (patient_id,))
        for plan in plans:
            plan["items"] = conn.all("SELECT i.*, s.name AS service FROM treatment_plan_items i LEFT JOIN services s ON s.id = i.service_id "
                                     "WHERE i.plan_id = ? ORDER BY i.seq, i.id", (plan["id"],))
        ctx["plans"] = plans
    if clinical and tab == "chart":
        from .chart import ADULT, CHILD, CONDITIONS, SURFACES, chart_state
        entries, latest = chart_state(conn, patient_id)
        dentition = "child" if request.args.get("dentition") == "child" else "adult"
        sel = request.args.get("tooth")
        ctx.update(chart_rows=CHILD if dentition == "child" else ADULT, chart_latest=latest, chart_entries=entries,
                   conditions=CONDITIONS, surfaces=SURFACES, dentition=dentition, sel_tooth=sel,
                   sel_entries=[e for e in entries if e["tooth"] == sel] if sel else [], today_iso=today().isoformat())
    if g.user.can("lab.view") or g.user.is_super_admin:
        ctx["lab_cases"] = conn.all("SELECT c.*, l.name AS lab FROM lab_cases c JOIN laboratories l ON l.id = c.lab_id "
                                    "WHERE c.patient_id = ? ORDER BY c.id DESC LIMIT 10", (patient_id,))
    if clinical and tab == "rx":
        ctx["prescriptions"] = conn.all(
            "SELECT r.*, u.name AS prescriber FROM prescriptions r LEFT JOIN users u ON u.id = r.prescriber_id "
            "WHERE r.patient_id = ? AND r.deleted = 0 ORDER BY r.prescribed_on DESC, r.id DESC", (patient_id,))
        for r in ctx["prescriptions"]:
            r["meds"] = ", ".join(i["medicine"] for i in conn.all(
                "SELECT medicine FROM prescription_items WHERE prescription_id = ? ORDER BY seq", (r["id"],)))
        ctx["certificates"] = conn.all("SELECT c.*, u.name AS dentist FROM certificates c LEFT JOIN users u ON u.id = c.issued_by "
                                       "WHERE c.patient_id = ? AND c.deleted = 0 ORDER BY c.issued_on DESC, c.id DESC", (patient_id,))
    doc_where = "d.patient_id = ?" + ("" if clinical else " AND d.clinical = 0")
    ctx["documents"] = conn.all(f"SELECT d.*, u.name AS uploader FROM patient_documents d LEFT JOIN users u ON u.id = d.uploaded_by "
                                f"WHERE {doc_where} ORDER BY d.uploaded_at DESC", (patient_id,))
    if tab == "changes":
        if not (clinical or g.user.is_super_admin):
            abort(403)
        ctx["changes"] = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                                  "WHERE a.entity_type = 'patient' AND a.entity_id = ? ORDER BY a.id DESC LIMIT 200", (patient_id,))
    ctx.update(services=services(), doc_categories=DOC_CATEGORIES, plan_statuses=PLAN_STATUSES, item_statuses=ITEM_STATUSES,
               all_dentists=dentists(), recent_appts=[a for a in ctx["appointments"] if a["status"] in ("checked_in", "completed")][:10])
    return render_template("staff/patients/detail.html", **ctx)


# ---------------------------------------------------------------------------
# Clinical updates
# ---------------------------------------------------------------------------

@bp.route("/<int:patient_id>/history", methods=["POST"])
@require("clinical.edit")
def history(patient_id):
    conn = get_db()
    _load(patient_id)
    _require_clinical(patient_id, edit=True)
    before = conn.one("SELECT * FROM patient_history WHERE patient_id = ?", (patient_id,))
    v = {f: clean(request.form.get(f), 4000) for f in HISTORY_FIELDS}
    alert = clean(request.form.get("alert_flag"), 120)
    with conn.transaction():
        if before:
            conn.execute("UPDATE patient_history SET " + ", ".join(f"{f} = ?" for f in HISTORY_FIELDS) +
                         ", updated_at = ?, updated_by = ? WHERE patient_id = ?", [*v.values(), now_str(), g.user.id, patient_id])
        else:
            conn.execute("INSERT INTO patient_history (patient_id, " + ", ".join(HISTORY_FIELDS) + ", updated_at, updated_by) VALUES (?, "
                         + ", ".join("?" for _ in HISTORY_FIELDS) + ", ?, ?)", [patient_id, *v.values(), now_str(), g.user.id])
        p = conn.one("SELECT alert_flag FROM patients WHERE id = ?", (patient_id,))
        changes = audit.diff(dict(before) if before else {}, v, HISTORY_FIELDS)
        if alert != p["alert_flag"]:
            conn.execute("UPDATE patients SET alert_flag = ?, updated_at = ? WHERE id = ?", (alert, now_str(), patient_id))
            changes["alert_flag"] = [p["alert_flag"], alert]
        if changes:
            audit.record("history_updated", "patient", patient_id, "Updated medical/dental history: " + ", ".join(changes), changes)
    flash("History saved.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="clinical"))


@bp.route("/<int:patient_id>/notes", methods=["POST"])
@require("progress.add")
def add_note(patient_id):
    conn = get_db()
    _load(patient_id)
    _require_clinical(patient_id, edit=True, perm="progress.add")
    body = clean(request.form.get("body"), 8000)
    appt_id = to_int(request.form.get("appointment_id"))
    if appt_id and not conn.one("SELECT id FROM appointments WHERE id = ? AND patient_id = ?", (appt_id, patient_id)):
        appt_id = None
    amends = to_int(request.form.get("amends"))
    if not body:
        flash("Write the note first.", "error")
    else:
        nid = conn.insert("clinical_notes", {"patient_id": patient_id, "appointment_id": appt_id, "author_id": g.user.id,
                                             "body": body, "created_at": now_str(), "amended": 1 if amends else 0})
        audit.record("clinical_note_added", "patient", patient_id, "Added clinical note" + (f" (amends note #{amends})" if amends else ""),
                     {"note_id": nid})
        flash("Clinical note added. Notes can't be edited; add an amendment to correct one.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="clinical"))


@bp.route("/<int:patient_id>/procedures", methods=["POST"])
@require("progress.add")
def add_procedure(patient_id):
    conn = get_db()
    p = _load(patient_id)
    _require_clinical(patient_id, edit=True, perm="progress.add")
    desc = clean(request.form.get("description"), 300)
    status = request.form.get("status", "completed")
    appt_id = to_int(request.form.get("appointment_id"))
    appt = conn.one("SELECT * FROM appointments WHERE id = ? AND patient_id = ?", (appt_id, patient_id)) if appt_id else None
    performed = parse_date(request.form.get("performed_at"))
    if not desc or status not in ("planned", "completed"):
        flash("Describe the procedure.", "error")
    else:
        prid = conn.insert("procedures", {
            "patient_id": patient_id, "appointment_id": appt["id"] if appt else None,
            "service_id": to_int(request.form.get("service_id")), "branch_id": appt["branch_id"] if appt else p["preferred_branch_id"],
            "tooth": clean(request.form.get("tooth"), 40), "description": desc, "status": status,
            "performed_by": g.user.id if status == "completed" else None,
            "performed_at": (performed or today()).isoformat() if status == "completed" else None, "created_at": now_str()})
        audit.record("procedure_added", "patient", patient_id, f"Recorded procedure: {desc[:60]}", {"procedure_id": prid})
        flash("Procedure recorded.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="clinical"))


PLAN_ACTION_PERMS = {"create": "plans.add", "add_item": "plans.edit", "item_status": "plans.edit", "plan_status": "plans.edit",
                     "delete": "plans.delete", "generate": "plans.generate"}


@bp.route("/<int:patient_id>/plans", methods=["POST"])
@require("patients.view")
def plans(patient_id):
    conn = get_db()
    _load(patient_id)
    action = request.form.get("action")
    if action not in PLAN_ACTION_PERMS:
        abort(400)
    _require_clinical(patient_id, edit=True, perm=PLAN_ACTION_PERMS[action])
    if action == "create":
        title = clean(request.form.get("title"), 150)
        if not title:
            flash("Give the plan a title.", "error")
        else:
            plan_id = conn.insert("treatment_plans", {"patient_id": patient_id, "dentist_id": g.user.id if g.user.role == "dentist" else to_int(request.form.get("dentist_id")),
                                                      "title": title, "notes": clean(request.form.get("notes"), 2000),
                                                      "status": "draft", "created_at": now_str(), "updated_at": now_str()})
            audit.record("plan_created", "patient", patient_id, f"Created treatment plan: {title}", {"plan_id": plan_id})
            flash("Treatment plan created. Add the planned items below.", "success")
    else:
        plan_id = to_int(request.form.get("plan_id"))
        plan = conn.one("SELECT * FROM treatment_plans WHERE id = ? AND patient_id = ?", (plan_id, patient_id))
        if not plan:
            abort(404)
        if action == "add_item":
            desc = clean(request.form.get("description"), 300)
            est = parse_money(request.form.get("estimate"))
            if not desc:
                flash("Describe the planned item.", "error")
            else:
                seq = (conn.scalar("SELECT MAX(seq) FROM treatment_plan_items WHERE plan_id = ?", (plan_id,)) or 0) + 1
                conn.insert("treatment_plan_items", {"plan_id": plan_id, "service_id": to_int(request.form.get("service_id")),
                                                     "tooth": clean(request.form.get("tooth"), 40), "description": desc,
                                                     "estimate_cents": est, "status": "pending", "seq": seq})
                conn.execute("UPDATE treatment_plans SET updated_at = ? WHERE id = ?", (now_str(), plan_id))
                audit.record("plan_item_added", "patient", patient_id, f"Plan '{plan['title']}': added {desc[:60]}")
        elif action == "item_status":
            item_id = to_int(request.form.get("item_id"))
            st = request.form.get("status")
            item = conn.one("SELECT * FROM treatment_plan_items WHERE id = ? AND plan_id = ?", (item_id, plan_id))
            if item and st in ITEM_STATUSES:
                conn.execute("UPDATE treatment_plan_items SET status = ? WHERE id = ?", (st, item_id))
                audit.record("plan_item_status", "patient", patient_id, f"Plan item '{item['description'][:50]}' → {st}")
        elif action == "plan_status":
            st = request.form.get("status")
            if st in PLAN_STATUSES:
                conn.execute("UPDATE treatment_plans SET status = ?, updated_at = ? WHERE id = ?", (st, now_str(), plan_id))
                audit.record("plan_status", "patient", patient_id, f"Plan '{plan['title']}' → {st}")
        elif action == "delete":
            items = conn.all("SELECT * FROM treatment_plan_items WHERE plan_id = ?", (plan_id,))
            with conn.transaction():
                conn.execute("DELETE FROM treatment_plan_items WHERE plan_id = ?", (plan_id,))
                conn.execute("DELETE FROM treatment_plans WHERE id = ?", (plan_id,))
                audit.record("plan_deleted", "patient", patient_id, f"Deleted treatment plan '{plan['title']}'",
                             {"plan": dict(plan), "items": items})
            flash("Treatment plan deleted. A copy is kept in the audit trail.", "success")
        elif action == "generate":
            # MyMedsPH "Generate Progress Note": record a planned item as done in the progress notes.
            item_id = to_int(request.form.get("item_id"))
            item = conn.one("SELECT * FROM treatment_plan_items WHERE id = ? AND plan_id = ?", (item_id, plan_id))
            if item and item["status"] != "done":
                with conn.transaction():
                    pat = conn.one("SELECT preferred_branch_id FROM patients WHERE id = ?", (patient_id,))
                    prid = conn.insert("procedures", {"patient_id": patient_id, "service_id": item["service_id"],
                                                      "branch_id": pat["preferred_branch_id"], "tooth": item["tooth"],
                                                      "description": item["description"], "status": "completed",
                                                      "performed_by": g.user.id, "performed_at": today().isoformat(), "created_at": now_str()})
                    conn.execute("UPDATE treatment_plan_items SET status = 'done' WHERE id = ?", (item_id,))
                    audit.record("progress_generated", "patient", patient_id, f"Progress note from plan item: {item['description'][:60]}",
                                 {"procedure_id": prid, "plan_item_id": item_id})
                flash("Progress note added and the plan item marked done.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="clinical") + "#plans")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@bp.route("/<int:patient_id>/documents", methods=["POST"])
@require("documents.upload")
def upload(patient_id):
    conn = get_db()
    _load(patient_id)
    category = request.form.get("category", "other")
    if category not in DOC_CATEGORIES:
        abort(400)
    is_clinical = DOC_CATEGORIES[category][1]
    if is_clinical and not can_see_clinical(conn, g.user, patient_id):
        abort(403)
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a file to upload.", "error")
        return redirect(url_for("patients.detail", patient_id=patient_id, tab="documents"))
    stored, mime, size, original, err = save_document(file)
    if err:
        flash(err, "error")
    else:
        did = conn.insert("patient_documents", {"patient_id": patient_id, "category": category, "clinical": 1 if is_clinical else 0,
                                                "original_name": original, "stored_name": stored, "mime": mime,
                                                "size_bytes": size, "uploaded_by": g.user.id, "uploaded_at": now_str()})
        audit.record("document_uploaded", "patient", patient_id, f"Uploaded {DOC_CATEGORIES[category][0]}", {"document_id": did})
        flash("Document uploaded.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="documents"))


@bp.route("/<int:patient_id>/documents/<int:doc_id>")
@require("patients.view")
def document(patient_id, doc_id):
    conn = get_db()
    _load(patient_id)
    d = conn.one("SELECT * FROM patient_documents WHERE id = ? AND patient_id = ?", (doc_id, patient_id))
    if not d:
        abort(404)
    if d["clinical"] and not can_see_clinical(conn, g.user, patient_id):
        abort(403)
    audit.record("document_viewed", "patient", patient_id, f"Opened document #{doc_id}")
    resp = send_file(document_path(d["stored_name"]), mimetype=d["mime"], as_attachment=request.args.get("download") == "1",
                     download_name=d["original_name"], max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return resp


# ---------------------------------------------------------------------------
# Dentist assignment (controls dentist access to clinical records)
# ---------------------------------------------------------------------------

@bp.route("/<int:patient_id>/assign", methods=["POST"])
@require("users.manage")
def assign(patient_id):
    conn = get_db()
    _load(patient_id)
    dentist_id = to_int(request.form.get("dentist_id"))
    if not conn.one("SELECT id FROM users WHERE id = ? AND role = 'dentist'", (dentist_id,)):
        abort(400)
    if request.form.get("action") == "remove":
        conn.execute("DELETE FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (patient_id, dentist_id))
        audit.record("dentist_unassigned", "patient", patient_id, "Removed dentist access", {"dentist_id": dentist_id})
    else:
        if not conn.one("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (patient_id, dentist_id)):
            conn.execute("INSERT INTO patient_assignments (patient_id, dentist_id, created_at, created_by) VALUES (?, ?, ?, ?)",
                         (patient_id, dentist_id, now_str(), g.user.id))
            audit.record("dentist_assigned", "patient", patient_id, "Granted dentist access", {"dentist_id": dentist_id})
    flash("Dentist access updated.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id))


# ---------------------------------------------------------------------------
# Progress note actions, attachment delete, patient delete
# ---------------------------------------------------------------------------

@bp.route("/<int:patient_id>/procedures/<int:proc_id>", methods=["POST"])
@require("progress.actions")
def procedure_action(patient_id, proc_id):
    conn = get_db()
    _load(patient_id)
    _require_clinical(patient_id, edit=True, perm="progress.actions")
    pr = conn.one("SELECT * FROM procedures WHERE id = ? AND patient_id = ?", (proc_id, patient_id))
    if not pr:
        abort(404)
    if request.form.get("action") == "delete":
        conn.execute("DELETE FROM procedures WHERE id = ?", (proc_id,))
        audit.record("progress_deleted", "patient", patient_id, f"Deleted progress note: {pr['description'][:60]}", {"entry": dict(pr)})
        flash("Progress note deleted. A copy is kept in the audit trail.", "success")
    else:
        vals = {"description": clean(request.form.get("description"), 1000) or pr["description"],
                "tooth": clean(request.form.get("tooth"), 40),
                "performed_at": (parse_date(request.form.get("performed_at")) or parse_date(pr["performed_at"]) or today()).isoformat()}
        conn.update("procedures", proc_id, vals)
        audit.record("progress_edited", "patient", patient_id, "Edited progress note", audit.diff(dict(pr), vals, vals.keys()))
        flash("Progress note updated.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="clinical"))


@bp.route("/<int:patient_id>/documents/<int:doc_id>/delete", methods=["POST"])
@require("documents.delete")
def document_delete(patient_id, doc_id):
    conn = get_db()
    _load(patient_id)
    d = conn.one("SELECT * FROM patient_documents WHERE id = ? AND patient_id = ?", (doc_id, patient_id))
    if not d:
        abort(404)
    if d["clinical"] and not can_see_clinical(conn, g.user, patient_id):
        abort(403)
    conn.execute("DELETE FROM patient_documents WHERE id = ?", (doc_id,))
    try:
        document_path(d["stored_name"]).unlink(missing_ok=True)
    except ValueError:
        pass
    audit.record("document_deleted", "patient", patient_id, f"Deleted attachment {d['original_name']}", {"document": dict(d)})
    flash("Attachment deleted.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="documents"))


@bp.route("/<int:patient_id>/delete", methods=["POST"])
@require("patients.delete")
def delete_patient(patient_id):
    """Removes the patient from all lists. Records are kept (archived) for legal retention and can be restored by a super admin."""
    conn = get_db()
    p = _load(patient_id)
    reason = clean(request.form.get("reason"), 300)
    if not reason:
        flash("Give a reason for deleting this patient.", "error")
        return redirect(url_for("patients.detail", patient_id=patient_id))
    conn.execute("UPDATE patients SET active = 0, updated_at = ? WHERE id = ?", (now_str(), patient_id))
    conn.execute("UPDATE reminders SET status = 'cancelled', result_note = 'Patient deleted' WHERE patient_id = ? AND status = 'pending'", (patient_id,))
    audit.record("patient_deleted", "patient", patient_id, f"Deleted patient {p['chart_no']}", {"reason": reason})
    flash("Patient deleted from the lists. Their records are archived, and a super admin can restore them.", "success")
    return redirect(url_for("patients.index"))


@bp.route("/<int:patient_id>/restore", methods=["POST"])
@require("users.manage")
def restore_patient(patient_id):
    conn = get_db()
    p = _load(patient_id)
    conn.execute("UPDATE patients SET active = 1, updated_at = ? WHERE id = ?", (now_str(), patient_id))
    audit.record("patient_restored", "patient", patient_id, f"Restored patient {p['chart_no']}")
    flash("Patient restored.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id))

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
    show = request.args.get("show", "")
    can_delete = g.user.can("patients.delete")
    if show not in ("incomplete", "deleted") or (show == "deleted" and not can_delete):
        show = ""
    per = to_int(request.args.get("per")) if request.args.get("per") in ("30", "100", "200") else 30
    where, args = [frag, "p.active = 0" if show == "deleted" else "p.active = 1"], list(params)
    if show == "incomplete":
        # first or last name without a single letter, e.g. ",,", "-", "...", "'@@@"
        where.append("(NOT lower(p.first_name) GLOB '*[a-z]*' OR NOT lower(p.last_name) GLOB '*[a-z]*')")
    if q:
        like = f"%{q.lower()}%"
        where.append("(lower(p.first_name || ' ' || p.last_name) LIKE ? OR lower(p.last_name || ', ' || p.first_name) LIKE ? "
                     "OR p.phone LIKE ? OR lower(p.chart_no) LIKE ? OR lower(p.email) LIKE ? OR p.legacy_id = ? "
                     "OR lower(p.first_name || ' ' || p.middle_name || ' ' || p.last_name) LIKE ?)")
        args += [like, like, like, like, like, q, like]
    total = conn.scalar(f"SELECT COUNT(*) FROM patients p WHERE {' AND '.join(where)}", args)
    pg = paginate(total, per)
    rows = conn.all(
        "SELECT p.*, b.name AS branch, du.name AS deleted_by_name, "
        "(SELECT MAX(start_at) FROM appointments a WHERE a.patient_id = p.id AND a.status = 'completed') AS last_visit, "
        "(SELECT MIN(start_at) FROM appointments a WHERE a.patient_id = p.id AND a.status IN ('requested','confirmed') AND a.start_at >= ?) AS next_visit "
        f"FROM patients p LEFT JOIN branches b ON b.id = p.preferred_branch_id LEFT JOIN users du ON du.id = p.deleted_by "
        f"WHERE {' AND '.join(where)} "
        + ("ORDER BY p.deleted_at DESC, p.id DESC" if show == "deleted" else "ORDER BY p.last_name, p.first_name")
        + " LIMIT ? OFFSET ?", [today().isoformat(), *args, pg["limit"], pg["offset"]])
    return render_template("staff/patients/index.html", rows=rows, pg=pg, q=q, show=show, per=per, can_delete=can_delete)


@bp.route("/bulk", methods=["POST"])
@require("patients.view")
def bulk():
    """Delete (archive) or restore several patients at once, e.g. to clean up junk records after an import."""
    conn = get_db()
    action = request.form.get("action")
    back = request.form.get("next") or url_for("patients.index")
    if not back.startswith("/staff/patients"):
        back = url_for("patients.index")
    if action == "delete" and not g.user.can("patients.delete"):
        abort(403)
    if action == "restore" and not g.user.can("users.manage"):
        abort(403)
    if action not in ("delete", "restore"):
        abort(400)
    ids = sorted({i for i in (to_int(x) for x in request.form.getlist("ids")) if i})[:500]
    if not ids:
        flash("Tick at least one patient first.", "error")
        return redirect(back)
    reason = clean(request.form.get("reason"), 300)
    if action == "delete" and not reason:
        flash("Give a reason for deleting these patients (e.g. “Junk records from the MyMedsPH import”).", "error")
        return redirect(back)
    frag, params = patient_scope(g.user, "p")
    marks = ",".join("?" * len(ids))
    rows = conn.all(f"SELECT p.id, p.chart_no FROM patients p WHERE p.id IN ({marks}) AND p.active = ? AND {frag}",
                    [*ids, 1 if action == "delete" else 0, *params])
    with conn.transaction():
        for r in rows:
            if action == "delete":
                conn.execute("UPDATE patients SET active = 0, deleted_at = ?, deleted_by = ?, deleted_reason = ?, updated_at = ? WHERE id = ?",
                             (now_str(), g.user.id, reason, now_str(), r["id"]))
                conn.execute("UPDATE reminders SET status = 'cancelled', result_note = 'Patient deleted' WHERE patient_id = ? AND status = 'pending'",
                             (r["id"],))
                audit.record("patient_deleted", "patient", r["id"], f"Deleted patient {r['chart_no']}", {"reason": reason, "bulk": True})
            else:
                conn.execute("UPDATE patients SET active = 1, deleted_at = NULL, deleted_by = NULL, deleted_reason = '', updated_at = ? WHERE id = ?",
                             (now_str(), r["id"]))
                audit.record("patient_restored", "patient", r["id"], f"Restored patient {r['chart_no']}", {"bulk": True})
    n = len(rows)
    flash((f"Deleted {n} patient(s). Their records are archived; a super admin can restore them under Deleted patients."
           if action == "delete" else f"Restored {n} patient(s)."), "success")
    return redirect(back)


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

def _age(birth):
    from ..util import parse_date
    b = parse_date(birth) if birth else None
    if not b:
        return None
    t = today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def progress_groups(conn, patient_id, procedures, notes):
    """Progress notes grouped like a visit log: one row per date + dentist, with the procedures done (priced from the
    invoice line with the same dentist, date and service or description), other billed lines, and clinical notes."""
    groups = {}

    def grp(day, dentist, branch=""):
        key = (day or "", dentist or "")
        gr = groups.setdefault(key, {"date": day, "dentist": dentist, "branches": set(), "lines": [], "notes": [], "invoices": {}, "procs": []})
        if branch:
            gr["branches"].add(branch)
        return gr

    items = conn.all("SELECT ii.*, COALESCE(ii.done_on, substr(i.issued_at, 1, 10), substr(i.created_at, 1, 10)) AS day, i.number, i.id AS inv_id, i.status AS inv_status, u.name AS dentist, b.name AS branch FROM invoice_items ii "
                     "JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN users u ON u.id = ii.dentist_id JOIN branches b ON b.id = i.branch_id "
                     "WHERE i.patient_id = ? AND i.status != 'void'", (patient_id,))
    pool = {}
    for it in items:
        it = dict(it)
        pool.setdefault((it["day"] or "", it["dentist"] or ""), []).append(it)
    branch_names = {b["id"]: b["name"] for b in conn.all("SELECT id, name FROM branches")}
    for pr in procedures:
        if pr["status"] != "completed":
            continue
        day = (pr["performed_at"] or pr["created_at"])[:10]
        gr = grp(day, pr["dentist"], branch_names.get(pr["branch_id"], ""))
        price, inv = None, None
        for it in pool.get((day, pr["dentist"] or ""), []):
            same = (pr["service_id"] and it["service_id"] == pr["service_id"]) or it["description"].strip().lower() == pr["description"].strip().lower()
            if same and not it.get("_used"):
                it["_used"] = True
                price, inv = it["amount_cents"], it
                break
        if inv:
            gr["invoices"][inv["inv_id"]] = inv["number"] or "Draft invoice"
            gr["branches"].add(inv["branch"])
        gr["lines"].append({"text": pr["description"], "tooth": pr["tooth"], "price": price, "proc": pr})
        gr["procs"].append(pr)
    for (day, dentist), its in pool.items():
        for it in its:
            if it.get("_used"):
                continue
            gr = grp(day, dentist, it["branch"])
            gr["lines"].append({"text": it["description"], "tooth": "", "price": it["amount_cents"], "proc": None})
            gr["invoices"][it["inv_id"]] = it["number"] or "Draft invoice"
    from_visit = {r["note_id"]: (r["visit_date"], r["dentist"]) for r in conn.all(
        "SELECT v.note_id, v.visit_date, u.name AS dentist FROM visit_notes v LEFT JOIN users u ON u.id = v.dentist_id "
        "WHERE v.patient_id = ? AND v.note_id IS NOT NULL", (patient_id,))}
    for n in notes:
        if n["id"] in from_visit:
            day, who = from_visit[n["id"]]
        else:
            day, who = (n["appt_at"] or n["created_at"])[:10], n["author"]
        grp(day, who)["notes"].append(n)
    docs, by_visit = {}, {}
    for d in conn.all("SELECT substr(uploaded_at, 1, 10) AS day, visit_note_id, COUNT(*) AS n FROM patient_documents WHERE patient_id = ? "
                      "GROUP BY day, visit_note_id", (patient_id,)):
        if d["visit_note_id"]:
            by_visit[d["visit_note_id"]] = by_visit.get(d["visit_note_id"], 0) + d["n"]
        else:
            docs[d["day"]] = docs.get(d["day"], 0) + d["n"]
    for vn in conn.all("SELECT v.id, v.visit_date, v.recall_date, v.recall_reason, v.signature_name, v.invoice_id, u.name AS dentist, "
                       "b.name AS branch FROM visit_notes v LEFT JOIN users u ON u.id = v.dentist_id LEFT JOIN branches b ON b.id = v.branch_id "
                       "WHERE v.patient_id = ? AND v.status = 'saved'", (patient_id,)):
        gr = grp(vn["visit_date"], vn["dentist"], vn["branch"] or "")
        gr.setdefault("visits", []).append(vn)
    out = sorted(groups.values(), key=lambda x: (x["date"] or "", x["dentist"] or ""), reverse=True)
    for gr in out:
        gr["attachments"] = docs.get(gr["date"], 0) + sum(by_visit.get(v["id"], 0) for v in gr.get("visits", []))
        gr["branch"] = ", ".join(sorted(b for b in gr["branches"] if b))
    return out


@bp.route("/<int:patient_id>")
@require("patients.view")
def detail(patient_id):
    conn = get_db()
    p = _load(patient_id)
    tab = request.args.get("tab", "profile")
    tab = {"overview": "profile", "clinical": "notes"}.get(tab, tab)
    if tab not in ("profile", "notes", "plans", "chart", "billing", "rx", "certs", "documents", "remarks", "diagnosis", "lab", "changes"):
        tab = "profile"
    clinical = can_see_clinical(conn, g.user, patient_id)
    if tab in ("notes", "plans", "chart", "rx", "certs", "diagnosis") and not clinical:
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
    if g.user.can("quotes.view"):
        ctx["quotes"] = conn.all("SELECT q.*, u.name AS dentist, b.name AS branch FROM quotations q JOIN branches b ON b.id = q.branch_id "
                                 "LEFT JOIN users u ON u.id = q.dentist_id WHERE q.patient_id = ? ORDER BY q.id DESC LIMIT 20", (patient_id,))
    if g.user.can("billing.view"):
        ctx["invoices"] = conn.all(
            "SELECT i.*, b.name AS branch, (SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END),0) "
            "FROM payments WHERE invoice_id = i.id AND status = 'valid') AS paid, u.name AS created_by_name FROM invoices i "
            "JOIN branches b ON b.id = i.branch_id LEFT JOIN users u ON u.id = i.created_by "
            "WHERE i.patient_id = ? ORDER BY COALESCE(i.issued_at, substr(i.created_at, 1, 10)) DESC, i.id DESC", (patient_id,))
        if tab == "billing":
            from ..billing import commission_dentists, invoice_commission_info
            ctx["comm_dentists"] = commission_dentists(conn)
            for inv in ctx["invoices"]:
                inv["comm_info"] = invoice_commission_info(conn, inv)
                inv["lines"] = ", ".join(it["description"] + (f"(#{it['tooth']})" if it["tooth"] else "")
                                         for it in conn.all("SELECT description, tooth FROM invoice_items WHERE invoice_id = ? ORDER BY id", (inv["id"],)))
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
    if clinical and tab == "notes":
        import json
        ctx["pn_groups"] = progress_groups(conn, patient_id, ctx["procedures"], ctx["notes"])
        from ..fee_schedule import picker_options
        ctx["price_options"] = picker_options(conn) or conn.all(
            "SELECT pi.name, pi.service_id, pi.price_from_cents AS price, pi.unit, '' AS category, 1 AS per_count FROM price_items pi "
            "WHERE pi.sample = 0 UNION ALL SELECT s.name, s.id, s.default_price_cents, '', '', 1 FROM services s WHERE s.active = 1 ORDER BY 1")
        ctx["drafts"] = conn.all("SELECT v.*, u.name AS by_name FROM visit_notes v LEFT JOIN users u ON u.id = v.created_by "
                                 "WHERE v.patient_id = ? AND v.status = 'draft' ORDER BY v.id DESC", (patient_id,))
        for d in ctx["drafts"]:
            d["lines"] = json.loads(d["lines_json"] or "[]")
        want = to_int(request.args.get("draft"))
        ctx["draft"] = next((d for d in ctx["drafts"] if d["id"] == want), None)
        ctx["note_branches"] = branches_for_user(g.user)
        ctx["default_branch"] = g.user.active_branch_id if g.user.active_branch_id else (
            p["preferred_branch_id"] if p["preferred_branch_id"] and g.user.in_branch(p["preferred_branch_id"]) else
            (ctx["note_branches"][0]["id"] if ctx["note_branches"] else None))
    if clinical and tab in ("rx", "certs"):
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
    if tab == "remarks":
        ctx["remarks"] = conn.all("SELECT r.*, u.name AS author FROM patient_remarks r LEFT JOIN users u ON u.id = r.author_id "
                                  "WHERE r.patient_id = ? AND r.deleted = 0 ORDER BY r.id DESC", (patient_id,))
    if clinical and tab == "diagnosis":
        ctx["diagnoses"] = conn.all("SELECT d.*, u.name AS dentist FROM patient_diagnoses d LEFT JOIN users u ON u.id = d.dentist_id "
                                    "WHERE d.patient_id = ? ORDER BY d.status, d.diagnosed_on DESC, d.id DESC", (patient_id,))
    if tab == "changes":
        if not (clinical or g.user.is_super_admin):
            abort(403)
        ctx["changes"] = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                                  "WHERE a.entity_type = 'patient' AND a.entity_id = ? ORDER BY a.id DESC LIMIT 200", (patient_id,))
    done = [a for a in ctx["appointments"] if a["status"] in ("checked_in", "completed")]
    ctx["last_visit"] = done[0] if done else None
    ctx["age"] = _age(p["birth_date"])
    ctx["today_iso"] = ctx.get("today_iso") or today().isoformat()
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


@bp.route("/<int:patient_id>/remarks", methods=["POST"])
@require("patients.view")
def remarks(patient_id):
    """Front-desk remarks (e.g. 'prefers text messages', 'bring HMO card'). Not for clinical findings."""
    conn = get_db()
    _load(patient_id)
    if request.form.get("action") == "delete":
        rid = to_int(request.form.get("remark_id"))
        r = conn.one("SELECT * FROM patient_remarks WHERE id = ? AND patient_id = ? AND deleted = 0", (rid, patient_id))
        if not r or not (r["author_id"] == g.user.id or g.user.can("patients.manage")):
            abort(403)
        conn.execute("UPDATE patient_remarks SET deleted = 1 WHERE id = ?", (rid,))
        audit.record("patient_remark_deleted", "patient", patient_id, "Removed a remark", {"remark_id": rid})
        flash("Remark removed.", "success")
    else:
        body = clean(request.form.get("body"), 1000)
        if not body:
            flash("Write the remark first.", "error")
        else:
            rid = conn.insert("patient_remarks", {"patient_id": patient_id, "body": body, "author_id": g.user.id, "created_at": now_str()})
            audit.record("patient_remark_added", "patient", patient_id, "Added a remark", {"remark_id": rid})
            flash("Remark added.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="remarks"))


@bp.route("/<int:patient_id>/diagnoses", methods=["POST"])
@require("progress.add")
def diagnoses(patient_id):
    conn = get_db()
    _load(patient_id)
    _require_clinical(patient_id, edit=True, perm="progress.add")
    action = request.form.get("action", "add")
    if action in ("resolve", "reopen"):
        did = to_int(request.form.get("diagnosis_id"))
        if not conn.one("SELECT id FROM patient_diagnoses WHERE id = ? AND patient_id = ?", (did, patient_id)):
            abort(404)
        st = "resolved" if action == "resolve" else "active"
        conn.execute("UPDATE patient_diagnoses SET status = ?, updated_at = ? WHERE id = ?", (st, now_str(), did))
        audit.record("diagnosis_updated", "patient", patient_id, f"Diagnosis marked {st}", {"diagnosis_id": did})
        flash(f"Diagnosis marked {st}.", "success")
    else:
        diag = clean(request.form.get("diagnosis"), 200)
        day = parse_date(request.form.get("diagnosed_on")) or today()
        dentist_id = to_int(request.form.get("dentist_id")) or (g.user.id if g.user.role == "dentist" else None)
        if not diag:
            flash("Enter the diagnosis.", "error")
        elif day > today():
            flash("The date can't be in the future.", "error")
        else:
            did = conn.insert("patient_diagnoses", {"patient_id": patient_id, "diagnosed_on": day.isoformat(),
                                                    "tooth": clean(request.form.get("tooth"), 40), "diagnosis": diag,
                                                    "notes": clean(request.form.get("notes"), 2000), "dentist_id": dentist_id,
                                                    "created_by": g.user.id, "created_at": now_str()})
            audit.record("diagnosis_added", "patient", patient_id, "Added a diagnosis", {"diagnosis_id": did})
            flash("Diagnosis added.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="diagnosis"))


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
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="plans"))


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
    conn.execute("UPDATE patients SET active = 0, deleted_at = ?, deleted_by = ?, deleted_reason = ?, updated_at = ? WHERE id = ?",
                 (now_str(), g.user.id, reason, now_str(), patient_id))
    conn.execute("UPDATE reminders SET status = 'cancelled', result_note = 'Patient deleted' WHERE patient_id = ? AND status = 'pending'", (patient_id,))
    audit.record("patient_deleted", "patient", patient_id, f"Deleted patient {p['chart_no']}", {"reason": reason})
    flash("Patient deleted from the lists. Their records are archived, and a super admin can restore them.", "success")
    return redirect(url_for("patients.index"))


@bp.route("/<int:patient_id>/restore", methods=["POST"])
@require("users.manage")
def restore_patient(patient_id):
    conn = get_db()
    p = _load(patient_id)
    conn.execute("UPDATE patients SET active = 1, deleted_at = NULL, deleted_by = NULL, deleted_reason = '', updated_at = ? WHERE id = ?",
                 (now_str(), patient_id))
    audit.record("patient_restored", "patient", patient_id, f"Restored patient {p['chart_no']}")
    flash("Patient restored.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id))


# ---------------------------------------------------------------------------
# New progress note (one visit): services per tooth, notes, attachments, recall, optional bill, patient signature
# ---------------------------------------------------------------------------
TOOTH_SPLIT = re.compile(r"[,\s;/]+")


def _teeth(text: str) -> list[str]:
    return [t for t in TOOTH_SPLIT.split(text or "") if t]


def _pct_bp(text) -> int | None:
    """'10' or '12.5' (%) -> basis points; blank -> 0; invalid -> None."""
    t = (text or "").strip().rstrip("%")
    if not t:
        return 0
    try:
        v = round(float(t) * 100)
    except ValueError:
        return None
    return v if 0 <= v <= 10000 else None


def _visit_form():
    """Read the form into a plain dict (also what a draft stores)."""
    f = request.form
    lines = []
    for sid, desc, tooth, qty, unit, disc in zip(f.getlist("line_service_id"), f.getlist("line_desc"), f.getlist("line_tooth"),
                                                 f.getlist("line_qty"), f.getlist("line_price"), f.getlist("line_disc")):
        if not (desc or "").strip() and not (unit or "").strip():
            continue
        lines.append({"service_id": to_int(sid), "desc": clean(desc, 200), "tooth": clean(tooth, 60), "qty": clean(qty, 4),
                      "price": clean(unit, 20), "disc": clean(disc, 8)})
    return {"visit_date": clean(f.get("visit_date"), 10), "recall_date": clean(f.get("recall_date"), 10),
            "recall_reason": clean(f.get("recall_reason"), 200), "body": clean(f.get("body"), 8000),
            "dentist_id": to_int(f.get("dentist_id")), "branch_id": to_int(f.get("branch_id")),
            "bill_disc": clean(f.get("bill_disc"), 8), "create_bill": 1 if f.get("create_bill") else 0, "lines": lines}


def _store_draft(conn, patient_id, v, draft_id=None):
    import json
    row = {"patient_id": patient_id, "branch_id": v["branch_id"], "dentist_id": v["dentist_id"],
           "visit_date": v["visit_date"] or today().isoformat(), "recall_date": v["recall_date"] or None,
           "recall_reason": v["recall_reason"], "body": v["body"], "lines_json": json.dumps(v["lines"]),
           "bill_discount_bp": _pct_bp(v["bill_disc"]) or 0, "create_bill": v["create_bill"], "status": "draft",
           "updated_at": now_str()}
    if draft_id:
        conn.update("visit_notes", draft_id, row)
        return draft_id
    return conn.insert("visit_notes", {**row, "created_by": g.user.id, "created_at": now_str()})


@bp.route("/<int:patient_id>/visit-note", methods=["POST"])
@require("progress.add")
def visit_note(patient_id):
    from ..billing import compute_totals, line_amount, next_invoice_number
    from ..uploads import save_signature
    conn = get_db()
    p = _load(patient_id)
    _require_clinical(patient_id, edit=True, perm="progress.add")
    v = _visit_form()
    draft_id = to_int(request.form.get("draft_id"))
    if draft_id and not conn.one("SELECT id FROM visit_notes WHERE id = ? AND patient_id = ? AND status = 'draft'", (draft_id, patient_id)):
        abort(404)

    def back_to_draft(msg, kind="error"):
        did = _store_draft(conn, patient_id, v, draft_id)
        flash(msg, kind)
        return redirect(url_for("patients.detail", patient_id=patient_id, tab="notes", draft=did) + "#dlg-pn")

    if request.form.get("action") == "draft":
        did = _store_draft(conn, patient_id, v, draft_id)
        audit.record("visit_note_draft", "patient", patient_id, "Saved a progress note draft", {"visit_note_id": did})
        flash("Draft saved. Open it from Progress Notes to continue.", "success")
        return redirect(url_for("patients.detail", patient_id=patient_id, tab="notes"))

    # ---- validate
    visit = parse_date(v["visit_date"])
    if not visit or visit > today():
        return back_to_draft("Enter the visit date (not in the future).")
    recall = parse_date(v["recall_date"]) if v["recall_date"] else None
    if v["recall_date"] and (not recall or recall <= visit):
        return back_to_draft("The recall date must be after the visit date.")
    dentist_id = g.user.id if g.user.role == "dentist" else v["dentist_id"]
    if not dentist_id or not conn.one("SELECT id FROM users WHERE id = ? AND role = 'dentist'", (dentist_id,)):
        return back_to_draft("Choose the dentist who did the work.")
    branch_id = v["branch_id"]
    if not branch_id or not g.user.in_branch(branch_id):
        return back_to_draft("Choose one of your branches.")
    from ..fee_schedule import picker_options
    per_count = {o["name"].upper(): o["per_count"] for o in picker_options(conn)}
    lines = []
    for ln in v["lines"]:
        if not ln["desc"]:
            return back_to_draft("Each service line needs a service or procedure.")
        unit = parse_money(ln["price"]) if ln["price"] else 0
        qty = to_int(ln["qty"]) or (max(1, len(_teeth(ln["tooth"]))) if per_count.get(ln["desc"].upper(), True) else 1)
        disc_bp = _pct_bp(ln["disc"])
        if unit is None or not 1 <= qty <= 32 or disc_bp is None:
            return back_to_draft(f"Check the price, quantity and discount % on “{ln['desc']}”.")
        sub = qty * unit
        lines.append({**ln, "unit": unit, "qty": qty, "sub": sub, "disc_cents": round(sub * disc_bp / 10000)})
    if not lines and not v["body"]:
        return back_to_draft("Add at least one service, or write the notes.")
    bill_bp = _pct_bp(v["bill_disc"])
    if bill_bp is None:
        return back_to_draft("Enter the bill discount as a percent, e.g. 10.")
    make_bill = bool(v["create_bill"]) and g.user.can("billing.manage") and any(l["unit"] > 0 for l in lines)
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if files and not g.user.can("documents.upload"):
        abort(403)
    sig_name = ""
    if request.form.get("signature"):
        sig_name, err = save_signature(request.form["signature"])
        if err:
            return back_to_draft(err)
    saved_docs = []
    for f in files[:10]:
        stored, mime, size, original, err = save_document(f)
        if err:
            return back_to_draft(f"{f.filename}: {err}")
        saved_docs.append((stored, mime, size, original))

    # ---- save everything together
    import json
    with conn.transaction(immediate=True):
        row = {"patient_id": patient_id, "branch_id": branch_id, "dentist_id": dentist_id, "visit_date": visit.isoformat(),
               "recall_date": recall.isoformat() if recall else None, "recall_reason": v["recall_reason"], "body": v["body"],
               "lines_json": json.dumps(v["lines"]), "bill_discount_bp": bill_bp, "create_bill": 1 if make_bill else 0,
               "status": "saved", "signature_name": sig_name, "updated_at": now_str()}
        if draft_id:
            conn.update("visit_notes", draft_id, row)
            vid = draft_id
        else:
            vid = conn.insert("visit_notes", {**row, "created_by": g.user.id, "created_at": now_str()})
        for ln in lines:
            conn.insert("procedures", {"patient_id": patient_id, "service_id": ln["service_id"], "branch_id": branch_id,
                                       "tooth": ln["tooth"], "description": ln["desc"], "status": "completed", "performed_by": dentist_id,
                                       "performed_at": visit.isoformat(), "created_at": now_str(), "visit_note_id": vid})
        upd = {}
        if v["body"]:
            upd["note_id"] = conn.insert("clinical_notes", {"patient_id": patient_id, "author_id": g.user.id, "body": v["body"],
                                                            "created_at": now_str()})
        if recall:
            upd["followup_id"] = conn.insert("follow_ups", {
                "branch_id": branch_id, "patient_id": patient_id, "kind": "recall",
                "title": "Recall" + (f": {v['recall_reason']}" if v["recall_reason"] else ""), "due_at": recall.isoformat() + " 09:00",
                "status": "open", "notes": "From progress note", "created_at": now_str(), "created_by": g.user.id})
        for stored, mime, size, original in saved_docs:
            conn.insert("patient_documents", {"patient_id": patient_id, "category": "clinical_photo", "clinical": 1, "original_name": original,
                                              "stored_name": stored, "mime": mime, "size_bytes": size, "uploaded_by": g.user.id,
                                              "uploaded_at": now_str(), "visit_note_id": vid})
        if make_bill:
            inv = conn.insert("invoices", {"branch_id": branch_id, "patient_id": patient_id, "status": "draft", "created_by": g.user.id,
                                           "created_at": now_str(), "notes": "Progress note"})
            for ln in lines:
                conn.insert("invoice_items", {"invoice_id": inv, "service_id": ln["service_id"], "description": ln["desc"], "qty": ln["qty"],
                                              "unit_price_cents": ln["unit"], "discount_cents": ln["disc_cents"],
                                              "amount_cents": line_amount(ln["qty"], ln["unit"], ln["disc_cents"]), "tooth": ln["tooth"],
                                              "dentist_id": dentist_id, "done_on": visit.isoformat()})
            items = conn.all("SELECT * FROM invoice_items WHERE invoice_id = ?", (inv,))
            sub = sum(i["amount_cents"] for i in items)
            conn.update("invoices", inv, compute_totals(items, round(sub * bill_bp / 10000), conn))
            number = next_invoice_number(conn, branch_id)
            conn.execute("UPDATE invoices SET status = 'issued', number = ?, issued_at = ? WHERE id = ?", (number, today().isoformat(), inv))
            upd["invoice_id"] = inv
            audit.record("invoice_issued", "invoice", inv, f"Issued {number} from a progress note", branch_id=branch_id)
        if upd:
            conn.update("visit_notes", vid, upd)
        audit.record("visit_note_saved", "patient", patient_id,
                     f"Progress note for {visit.isoformat()}: {len(lines)} service(s)" + (", bill created" if make_bill else "")
                     + (", signed by patient" if sig_name else ""), {"visit_note_id": vid}, branch_id)
    flash("Progress note saved" + (" and the bill was created. Add the payment from Bills & Payment." if make_bill else "."), "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="notes"))


@bp.route("/<int:patient_id>/visit-notes/<int:vid>/delete", methods=["POST"])
@require("progress.add")
def visit_note_delete(patient_id, vid):
    conn = get_db()
    _load(patient_id)
    _require_clinical(patient_id)
    d = conn.one("SELECT * FROM visit_notes WHERE id = ? AND patient_id = ? AND status = 'draft'", (vid, patient_id))
    if not d:
        abort(404)
    if d["created_by"] != g.user.id and not g.user.can("progress.actions"):
        abort(403)
    conn.execute("DELETE FROM visit_notes WHERE id = ?", (vid,))
    audit.record("visit_note_draft_deleted", "patient", patient_id, "Deleted a progress note draft", {"visit_note_id": vid})
    flash("Draft deleted.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="notes"))


@bp.route("/<int:patient_id>/visit-notes/<int:vid>/signature")
@require("patients.view")
def visit_note_signature(patient_id, vid):
    conn = get_db()
    _load(patient_id)
    _require_clinical(patient_id)
    d = conn.one("SELECT signature_name FROM visit_notes WHERE id = ? AND patient_id = ?", (vid, patient_id))
    if not d or not d["signature_name"]:
        abort(404)
    resp = send_file(document_path(d["signature_name"]), mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

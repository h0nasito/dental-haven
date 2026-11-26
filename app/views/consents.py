"""Patient consent forms: sign on screen, view / print, void; and the form wording (admin edits, a dentist approves)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import require
from ..consent import PLACEHOLDERS, fill
from ..db import get_db
from ..permissions import can_see_clinical, can_see_patient
from ..util import clean, now_str, parse_date, today
from .common import dentists

bp = Blueprint("consents", __name__, url_prefix="/staff")


def can_view(conn, patient_id: int) -> bool:
    return can_see_patient(conn, g.user, patient_id) and (g.user.can("consent.take") or can_see_clinical(conn, g.user, patient_id))


def _patient(patient_id):
    conn = get_db()
    if not can_view(conn, patient_id):
        abort(403)
    p = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    if not p:
        abort(404)
    return p


def _age_years(birth):
    d = parse_date(birth)
    if not d:
        return None
    t = today()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


def may_approve(user) -> bool:
    """Only a dentist (or a super admin) approves the wording patients sign."""
    return user.is_super_admin or user.role == "dentist"


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

@bp.route("/patients/<int:patient_id>/consents/new", methods=["GET", "POST"])
@require("consent.take")
def new(patient_id):
    from ..uploads import save_signature
    conn = get_db()
    p = _patient(patient_id)
    t = conn.one("SELECT * FROM consent_templates WHERE id = ? AND active = 1", (request.values.get("form", type=int) or 0,))
    if not t:
        abort(404)
    if not t["approved_at"]:
        flash("This consent form isn't approved by a dentist yet, so patients can't sign it. "
              "Ask a dentist to approve it under Administration → Consent forms.", "error")
        return redirect(url_for("patients.detail", patient_id=patient_id, tab="consents"))
    branch_id = g.user.active_branch_id or p["preferred_branch_id"]
    branch = conn.one("SELECT name FROM branches WHERE id = ?", (branch_id,)) if branch_id else None
    choices = dentists(g.user.scope_branch_ids) or dentists()
    age = _age_years(p["birth_date"])
    minor = age is not None and age < 18
    v = {"dentist_id": g.user.id if g.user.role == "dentist" else None, "procedure": "", "teeth": "",
         "signed_by_name": "" if minor else f"{p['first_name']} {p['last_name']}", "signed_by_relation": "", "understood": False}
    errors = []
    if request.method == "POST":
        f = request.form
        v = {"dentist_id": f.get("dentist_id", type=int), "procedure": clean(f.get("procedure"), 600), "teeth": clean(f.get("teeth"), 120),
             "signed_by_name": clean(f.get("signed_by_name"), 150), "signed_by_relation": clean(f.get("signed_by_relation"), 60),
             "understood": f.get("understood") == "1"}
        if not any(d["id"] == v["dentist_id"] for d in choices):
            errors.append("Choose the dentist who explained the treatment.")
        if "{procedure}" in t["body"] and not v["procedure"]:
            errors.append("Write the treatment or procedure.")
        if "{address}" in t["body"] and not (p["address"] or "").strip():
            errors.append("The patient's address is empty. Add it on the patient's profile first; this form needs it.")
        if not v["signed_by_name"]:
            errors.append("Write the name of the person signing.")
        if minor and not v["signed_by_relation"]:
            errors.append("The patient is under 18: a parent or guardian signs. Write their relationship to the patient.")
        if not v["understood"]:
            errors.append("The patient (or guardian) must tick that they read and understood the form.")
        if not (f.get("signature") or "").strip():
            errors.append("The patient (or guardian) must sign.")
        sig = None
        if not errors:
            sig, err = save_signature(f["signature"])
            if err:
                errors.append(err)
        if not errors:
            dentist = next(d for d in choices if d["id"] == v["dentist_id"])
            body = fill(t["body"], _values(p, age, branch, dentist["name"], v))
            cid = conn.insert("patient_consents", {
                "patient_id": patient_id, "template_id": t["id"], "branch_id": branch_id, "dentist_id": v["dentist_id"],
                "title": t["title"], "body": body, "procedure_text": v["procedure"] or None, "teeth": v["teeth"] or None,
                "signed_by_name": v["signed_by_name"], "signed_by_relation": v["signed_by_relation"] or None,
                "signature_stored": sig, "signed_at": now_str(), "witness_id": g.user.id, "status": "valid", "created_at": now_str()})
            audit.record("consent_signed", "patient", patient_id, f"Consent form signed: {t['title']} (#{cid})", {"consent_id": cid}, branch_id)
            flash("Consent form signed and saved.", "success")
            return redirect(url_for("consents.view", consent_id=cid))
    preview = _live_preview(t["body"], _values(p, age, branch, next((d["name"] for d in choices if d["id"] == v["dentist_id"]), ""), v))
    return render_template("staff/consents/sign.html", p=p, t=t, v=v, errors=errors, choices=choices, preview=preview,
                           minor=minor, age=age, asks_procedure="{procedure}" in t["body"], asks_teeth="{teeth}" in t["body"])


def _live_preview(body, values):
    """The form text for the patient to read, with the dentist, treatment and teeth updating as the staff types them."""
    from markupsafe import Markup, escape
    out = str(escape(body))
    for k in PLACEHOLDERS:
        val = values.get(k) or ""
        if k in ("dentist", "procedure", "teeth"):
            out = out.replace("{" + k + "}", f'<span data-fill="{k}" class="consent-fill">{escape(val) or "…"}</span>')
        else:
            out = out.replace("{" + k + "}", str(escape(val or "—")))
    return Markup(out)


def _values(p, age, branch, dentist_name, v):
    return {"patient": f"{p['first_name']} {p['last_name']}", "age": f"{age} years old" if age is not None else "of legal age",
            "address": p["address"] or "",
            "date": today().strftime("%B %d, %Y"), "branch": branch["name"] if branch else "", "dentist": dentist_name,
            "procedure": v.get("procedure"), "teeth": v.get("teeth")}


def _load(consent_id):
    conn = get_db()
    c = conn.one("SELECT c.*, u.name AS dentist, u.license_no, w.name AS witness, b.name AS branch, b.address AS branch_address, "
                 "b.phone AS branch_phone, vb.name AS voided_by_name FROM patient_consents c LEFT JOIN users u ON u.id = c.dentist_id "
                 "LEFT JOIN users w ON w.id = c.witness_id LEFT JOIN branches b ON b.id = c.branch_id "
                 "LEFT JOIN users vb ON vb.id = c.voided_by WHERE c.id = ?", (consent_id,))
    if not c:
        abort(404)
    return c, _patient(c["patient_id"])


@bp.route("/consents/<int:consent_id>")
@require("patients.view")
def view(consent_id):
    c, p = _load(consent_id)
    audit.record("consent_viewed", "patient", p["id"], f"Opened consent form #{consent_id}")
    return render_template("staff/consents/view.html", c=c, p=p)


@bp.route("/consents/<int:consent_id>/signature")
@require("patients.view")
def signature(consent_id):
    from ..uploads import document_path
    c, _p = _load(consent_id)
    resp = send_file(document_path(c["signature_stored"]), mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/consents/<int:consent_id>/void", methods=["POST"])
@require("consent.void")
def void(consent_id):
    conn = get_db()
    c, p = _load(consent_id)
    reason = clean(request.form.get("reason"), 300)
    if c["status"] != "valid":
        flash("This consent form is already void.", "error")
    elif not reason:
        flash("Give the reason for voiding.", "error")
    else:
        conn.execute("UPDATE patient_consents SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                     (reason, g.user.id, now_str(), consent_id))
        audit.record("consent_voided", "patient", p["id"], f"Voided consent form #{consent_id}: {reason}", {"consent_id": consent_id})
        flash("Consent form voided. It stays in the record, marked void.", "success")
    return redirect(url_for("consents.view", consent_id=consent_id))


# ---------------------------------------------------------------------------
# Form wording (Administration → Consent forms)
# ---------------------------------------------------------------------------

@bp.route("/admin/consent-forms")
@require("consent.templates", "consent.take", any_of=True)
def forms():
    conn = get_db()
    rows = conn.all("SELECT t.*, a.name AS approved_by_name, e.name AS updated_by_name, "
                    "(SELECT COUNT(*) FROM patient_consents c WHERE c.template_id = t.id AND c.status = 'valid') AS signed "
                    "FROM consent_templates t LEFT JOIN users a ON a.id = t.approved_by LEFT JOIN users e ON e.id = t.updated_by "
                    "ORDER BY t.active DESC, t.sort_order, t.id")
    return render_template("staff/consents/forms.html", rows=rows, may_approve=may_approve(g.user),
                           may_edit=g.user.can("consent.templates"))


@bp.route("/admin/consent-forms/new", methods=["GET", "POST"])
@require("consent.templates")
def form_new():
    return _form_edit(None)


@bp.route("/admin/consent-forms/<int:form_id>", methods=["GET", "POST"])
@require("consent.templates", "consent.take", any_of=True)
def form_edit(form_id):
    t = get_db().one("SELECT t.*, a.name AS approved_by_name FROM consent_templates t LEFT JOIN users a ON a.id = t.approved_by "
                     "WHERE t.id = ?", (form_id,))
    if not t:
        abort(404)
    return _form_edit(t)


def _form_edit(t):
    conn = get_db()
    can_edit = g.user.can("consent.templates")
    v = {"title": t["title"] if t else "", "body": t["body"] if t else "", "active": t["active"] if t else 1}
    errors = []
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "approve":
            if not (t and may_approve(g.user)):
                abort(403)
            conn.execute("UPDATE consent_templates SET approved_by = ?, approved_at = ? WHERE id = ?", (g.user.id, now_str(), t["id"]))
            audit.record("consent_form_approved", "consent_template", t["id"], f"Approved consent form “{t['title']}” for patients to sign")
            flash("Approved. Patients can now sign this form.", "success")
            return redirect(url_for("consents.forms"))
        if not can_edit:
            abort(403)
        v = {"title": clean(request.form.get("title"), 150), "body": (request.form.get("body") or "").strip()[:12000],
             "active": 1 if request.form.get("active") else 0}
        if not v["title"] or not v["body"]:
            errors.append("Enter the title and the wording.")
        if not errors:
            if t:
                changed = v["title"] != t["title"] or v["body"] != t["body"]
                upd = {**v, "updated_by": g.user.id, "updated_at": now_str()}
                if changed:
                    upd.update(approved_by=None, approved_at=None)
                conn.update("consent_templates", t["id"], upd)
                audit.record("consent_form_edited", "consent_template", t["id"], f"Edited consent form “{v['title']}”"
                             + (" (needs a dentist's approval again)" if changed else ""))
                fid = t["id"]
            else:
                import secrets
                fid = conn.insert("consent_templates", {**v, "code": "custom-" + secrets.token_hex(4), "updated_by": g.user.id,
                                                        "updated_at": now_str(), "created_at": now_str(),
                                                        "sort_order": (conn.scalar("SELECT MAX(sort_order) FROM consent_templates") or 0) + 1})
                audit.record("consent_form_created", "consent_template", fid, f"Added consent form “{v['title']}”")
            flash("Saved. A dentist has to approve the new wording before patients can sign it." if not (t and v["body"] == t["body"]
                  and v["title"] == t["title"] and t["approved_at"]) else "Saved.", "success")
            return redirect(url_for("consents.form_edit", form_id=fid))
    return render_template("staff/consents/form_edit.html", t=t, v=v, errors=errors, can_edit=can_edit,
                           may_approve=may_approve(g.user), placeholders=PLACEHOLDERS)

"""New-patient kiosk on a clinic tablet.

Staff log in on the tablet and tap "Start kiosk" (choosing the branch). From then on the tablet shows only the
registration form: every other page sends it back to the form, the form is emptied after each patient, and leaving
kiosk mode needs the staff member's password. A submitted form becomes a pending registration that reception reviews
(checking for an existing record) before a patient record with a chart number is created.
"""
from __future__ import annotations

import json
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, session, url_for

from .. import audit
from ..auth import login_required, require, verify_password
from ..db import get_db
from ..notices import notify
from ..util import clean, now_str, parse_date, to_int, today
from .common import branches_for_user

bp = Blueprint("kiosk", __name__)
KIOSK_KEY = "kiosk_branch"
# pages the tablet may still load while in kiosk mode
KIOSK_ENDPOINTS = {"kiosk.form", "kiosk.done", "kiosk.exit", "kiosk.ping", "static"}

CONDITIONS = ["High blood pressure", "Diabetes", "Heart disease", "Asthma", "Bleeding problems / on blood thinners", "Hepatitis",
              "Kidney disease", "Thyroid problems", "Epilepsy / seizures", "Cancer / radiation treatment", "HIV", "Tuberculosis"]
ALLERGIES = ["Penicillin / antibiotics", "Local anesthetic", "Latex", "Aspirin / pain relievers"]
TEXT_FIELDS = {  # name: max length
    "first_name": 80, "middle_name": 80, "last_name": 80, "birth_date": 10, "sex": 10, "civil_status": 20, "occupation": 80,
    "phone": 30, "email": 120, "address": 250, "emergency_contact": 120, "emergency_relation": 40, "emergency_phone": 30,
    "guardian_name": 120, "guardian_relation": 40, "conditions_other": 300, "allergies_other": 300, "medications": 400,
    "pregnant": 10, "last_visit": 80, "reason": 400,
}


@bp.before_app_request
def _kiosk_lock():
    """While a tablet is in kiosk mode it can only show the registration form."""
    if session.get(KIOSK_KEY) and request.endpoint not in KIOSK_ENDPOINTS:
        if not getattr(g, "user", None):
            session.pop(KIOSK_KEY, None)        # the staff login ended: kiosk mode ends with it
            return None
        return redirect(url_for("kiosk.form"))
    return None


@bp.after_app_request
def _kiosk_no_store(resp):
    """The next patient must not see the previous one's answers with the Back button."""
    if request.path.startswith("/kiosk") or session.get(KIOSK_KEY):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _age(bd: date | None) -> int | None:
    if not bd:
        return None
    t = today()
    return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))


@bp.route("/staff/kiosk/start", methods=["POST"])
@require("patients.manage")
def start():
    bid = to_int(request.form.get("branch_id"))
    if not bid or not g.user.in_branch(bid):
        flash("Choose one of your branches for the kiosk.", "error")
        return redirect(url_for("kiosk.registrations"))
    session[KIOSK_KEY] = bid
    audit.record("kiosk_started", "branch", bid, "New-patient kiosk started on a tablet", branch_id=bid)
    return redirect(url_for("kiosk.form"))


@bp.route("/kiosk", methods=["GET", "POST"])
@login_required
def form():
    bid = session.get(KIOSK_KEY)
    if not bid:
        return redirect(url_for("kiosk.registrations"))
    conn = get_db()
    branch = conn.one("SELECT id, name FROM branches WHERE id = ?", (bid,))
    v = {k: "" for k in TEXT_FIELDS}
    v.update({"conditions": [], "allergies": [], "consent_privacy": "", "consent_marketing": ""})
    errors: dict[str, str] = {}
    if request.method == "POST":
        f = request.form
        for k, n in TEXT_FIELDS.items():
            v[k] = clean(f.get(k), n)
        v["first_name"], v["middle_name"], v["last_name"] = (v["first_name"].title(), v["middle_name"].title(), v["last_name"].title())
        v["conditions"] = [c for c in f.getlist("conditions") if c in CONDITIONS]
        v["allergies"] = [a for a in f.getlist("allergies") if a in ALLERGIES]
        v["consent_privacy"] = "1" if f.get("consent_privacy") else ""
        v["consent_marketing"] = "1" if f.get("consent_marketing") else ""
        from .patients import EMAIL_RE, PHONE_RE
        if not v["first_name"]:
            errors["first_name"] = "Please enter your first name."
        if not v["last_name"]:
            errors["last_name"] = "Please enter your last name."
        bd = parse_date(v["birth_date"])
        if not bd or bd > today() or bd.year < 1900:
            errors["birth_date"] = "Please enter your date of birth."
        if not v["phone"] or not PHONE_RE.match(v["phone"]):
            errors["phone"] = "Please enter your mobile number, e.g. 0917 123 4567."
        if v["email"] and not EMAIL_RE.match(v["email"]):
            errors["email"] = "Please check your email address."
        if v["emergency_phone"] and not PHONE_RE.match(v["emergency_phone"]):
            errors["emergency_phone"] = "Please check this mobile number."
        minor = (_age(bd) or 99) < 18
        if minor and not v["guardian_name"]:
            errors["guardian_name"] = "For patients under 18, please enter the parent or guardian's name."
        if not v["consent_privacy"]:
            errors["consent_privacy"] = "Please read and agree to the privacy notice to continue."
        sig = f.get("signature") or ""
        if not sig:
            errors["signature"] = "Please sign in the box." if not minor else "The parent or guardian signs in the box."
        if not errors:
            from ..uploads import save_private_image, save_signature
            stored_sig, err = save_signature(sig)
            if err:
                errors["signature"] = err
            photo_name = ""
            ph = request.files.get("photo")
            if not errors and ph and ph.filename:
                photo_name, err = save_private_image(ph, "patient_photos")
                if err:
                    errors["photo"] = err
                    photo_name = ""
            if not errors:
                data = {k: v[k] for k in TEXT_FIELDS} | {"conditions": v["conditions"], "allergies": v["allergies"],
                                                          "consent_privacy": 1, "consent_marketing": 1 if v["consent_marketing"] else 0,
                                                          "minor": minor}
                rid = conn.insert("kiosk_registrations", {"branch_id": bid, "first_name": v["first_name"], "last_name": v["last_name"],
                                                          "data_json": json.dumps(data), "signature_name": stored_sig or "",
                                                          "photo_name": photo_name or "", "started_by": g.user.id, "created_at": now_str()})
                staff = [r["user_id"] for r in conn.all("SELECT DISTINCT ub.user_id FROM user_branches ub JOIN users u ON u.id = ub.user_id "
                                                         "WHERE ub.branch_id = ? AND u.active = 1 AND u.role != 'dentist'", (bid,))]
                notify(conn, staff, "kiosk_registration", "New patient registration at the kiosk",
                       f"{branch['name']}: please review it", url_for("kiosk.registration", reg_id=rid))
                audit.record("kiosk_registration", "kiosk_registration", rid, "New patient registration from the kiosk", branch_id=bid)
                return redirect(url_for("kiosk.done"))
    from .public import content
    pn = content("privacy_notice")
    return render_template("kiosk/form.html", v=v, errors=errors, branch=branch, conditions=CONDITIONS, allergy_list=ALLERGIES,
                           privacy=pn)


@bp.route("/kiosk/done")
@login_required
def done():
    if not session.get(KIOSK_KEY):
        return redirect(url_for("kiosk.registrations"))
    return render_template("kiosk/done.html")


@bp.route("/kiosk/ping", methods=["POST"])
@login_required
def ping():
    """Keeps the staff login on the tablet alive while it waits for the next patient."""
    return ("", 204)


@bp.route("/kiosk/exit", methods=["GET", "POST"], endpoint="exit")
@login_required
def exit_kiosk():
    if not session.get(KIOSK_KEY):
        return redirect(url_for("kiosk.registrations"))
    error = ""
    if request.method == "POST":
        conn = get_db()
        row = conn.one("SELECT password_hash FROM users WHERE id = ?", (g.user.id,))
        if row and verify_password(row["password_hash"], request.form.get("password") or ""):
            bid = session.pop(KIOSK_KEY, None)
            audit.record("kiosk_stopped", "branch", bid, "New-patient kiosk stopped", branch_id=bid)
            flash("Kiosk mode ended.", "success")
            return redirect(url_for("kiosk.registrations"))
        error = "That password isn't right."
        audit.record("kiosk_exit_failed", "branch", session.get(KIOSK_KEY), "Wrong password to leave kiosk mode")
    return render_template("kiosk/exit.html", error=error)


# ---------------------------------------------------------------- staff review

def _scope_ids():
    return g.user.branch_ids if not g.user.is_super_admin else [r["id"] for r in get_db().all("SELECT id FROM branches")]


@bp.route("/staff/registrations")
@require("patients.manage")
def registrations():
    conn = get_db()
    ids = _scope_ids()
    marks = ",".join("?" * len(ids)) or "NULL"
    view = request.args.get("view") or "pending"
    st = "pending" if view == "pending" else None
    rows = conn.all("SELECT r.*, b.name AS branch, p.chart_no FROM kiosk_registrations r JOIN branches b ON b.id = r.branch_id "
                    f"LEFT JOIN patients p ON p.id = r.patient_id WHERE r.branch_id IN ({marks}) "
                    + ("AND r.status = 'pending' " if st else "AND r.status != 'pending' ")
                    + "ORDER BY r.id DESC LIMIT 200", ids)
    pending = conn.scalar(f"SELECT COUNT(*) FROM kiosk_registrations WHERE status = 'pending' AND branch_id IN ({marks})", ids)
    return render_template("staff/registrations/index.html", rows=rows, view=view, pending=pending, branches=branches_for_user(g.user))


def _load_reg(reg_id):
    r = get_db().one("SELECT r.*, b.name AS branch FROM kiosk_registrations r JOIN branches b ON b.id = r.branch_id WHERE r.id = ?", (reg_id,))
    if not r or (not g.user.is_super_admin and r["branch_id"] not in g.user.branch_ids):
        abort(404)
    return r


@bp.route("/staff/registrations/<int:reg_id>/file/<kind>")
@require("patients.manage")
def reg_file(reg_id, kind):
    from ..uploads import document_path
    r = _load_reg(reg_id)
    name = r["signature_name"] if kind == "signature" else r["photo_name"] if kind == "photo" else ""
    if not name:
        abort(404)
    resp = send_file(document_path(name), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/staff/registrations/<int:reg_id>", methods=["GET", "POST"])
@require("patients.manage")
def registration(reg_id):
    conn = get_db()
    r = _load_reg(reg_id)
    d = json.loads(r["data_json"] or "{}")
    dups = conn.all("SELECT id, chart_no, first_name, last_name, birth_date, phone FROM patients WHERE deleted_at IS NULL AND "
                    "((lower(first_name) = lower(?) AND lower(last_name) = lower(?)) OR (phone != '' AND phone = ?) "
                    "OR (birth_date = ? AND lower(last_name) = lower(?))) LIMIT 10",
                    (r["first_name"], r["last_name"], d.get("phone") or "-", d.get("birth_date") or "-", r["last_name"]))
    if request.method == "POST" and r["status"] == "pending":
        action = request.form.get("action")
        if action == "accept":
            pid = _create_patient(conn, r, d)
            flash("Patient record created from the kiosk registration.", "success")
            return redirect(url_for("patients.detail", patient_id=pid))
        if action == "link":
            pid = to_int(request.form.get("patient_id"))
            if not pid or pid not in {x["id"] for x in dups}:
                flash("Choose the existing patient this registration belongs to.", "error")
                return redirect(url_for("kiosk.registration", reg_id=reg_id))
            _link_patient(conn, r, d, pid)
            flash("Linked to the existing patient: empty fields were filled in, and the signed consent and photo were added.", "success")
            return redirect(url_for("patients.detail", patient_id=pid))
        if action == "reject":
            reason = clean(request.form.get("reason"), 200) or "Not needed"
            _discard_files(r)
            conn.execute("UPDATE kiosk_registrations SET status = 'rejected', reviewed_by = ?, reviewed_at = ?, review_note = ?, "
                         "data_json = '{}', signature_name = '', photo_name = '' WHERE id = ?", (g.user.id, now_str(), reason, reg_id))
            audit.record("kiosk_registration_rejected", "kiosk_registration", reg_id, f"Kiosk registration discarded: {reason}",
                         branch_id=r["branch_id"])
            flash("Registration discarded and its details deleted.", "success")
            return redirect(url_for("kiosk.registrations"))
    return render_template("staff/registrations/detail.html", r=r, d=d, dups=dups, age=_age(parse_date(d.get("birth_date"))))


def _discard_files(r):
    from ..uploads import document_path
    for n in (r["signature_name"], r["photo_name"]):
        if n:
            try:
                document_path(n).unlink(missing_ok=True)
            except ValueError:
                pass


def _history_text(d) -> dict:
    cond = ", ".join([*d.get("conditions", []), *([d["conditions_other"]] if d.get("conditions_other") else [])])
    alg = ", ".join([*d.get("allergies", []), *([d["allergies_other"]] if d.get("allergies_other") else [])])
    dental = "; ".join(x for x in [f"Last dental visit: {d['last_visit']}" if d.get("last_visit") else "",
                                    f"Reason for visit: {d['reason']}" if d.get("reason") else ""] if x)
    other = "; ".join(x for x in [f"Pregnant / nursing: {d['pregnant']}" if d.get("pregnant") else "",
                                   f"Parent/guardian: {d['guardian_name']} ({d.get('guardian_relation') or 'guardian'})" if d.get("guardian_name") else ""] if x)
    return {"medical_conditions": cond, "allergies": alg, "medications": d.get("medications") or "", "dental_history": dental, "other_notes": other}


def _insert_history(conn, pid, h: dict):
    conn.execute("INSERT INTO patient_history (patient_id, medical_conditions, allergies, medications, dental_history, other_notes, "
                 "updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (pid, h["medical_conditions"], h["allergies"], h["medications"], h["dental_history"], h["other_notes"], now_str(), g.user.id))


def _attach_consent(conn, r, pid):
    if r["signature_name"]:
        from ..uploads import document_path
        try:
            size = document_path(r["signature_name"]).stat().st_size
        except (OSError, ValueError):
            size = 0
        conn.insert("patient_documents", {"patient_id": pid, "category": "consent_form", "clinical": 0,
                                          "original_name": f"Kiosk registration and privacy consent signature {r['created_at'][:10]}.png",
                                          "stored_name": r["signature_name"], "mime": "image/png", "size_bytes": size,
                                          "uploaded_by": r["started_by"], "uploaded_at": r["created_at"]})


def _emergency(d) -> str:
    rel = f" ({d['emergency_relation']})" if d.get("emergency_relation") else ""
    return (d.get("emergency_contact") or "") + (rel if d.get("emergency_contact") else "")


def _create_patient(conn, r, d) -> int:
    from .patients import next_chart_no
    with conn.transaction():
        pid = conn.insert("patients", {
            "chart_no": next_chart_no(conn), "first_name": r["first_name"], "middle_name": d.get("middle_name") or "",
            "last_name": r["last_name"], "birth_date": d.get("birth_date") or None, "sex": d.get("sex") or "",
            "civil_status": d.get("civil_status") or "", "occupation": d.get("occupation") or "", "phone": d.get("phone") or "",
            "email": d.get("email") or "", "address": d.get("address") or "", "emergency_contact": _emergency(d),
            "emergency_phone": d.get("emergency_phone") or "", "preferred_branch_id": r["branch_id"], "photo": r["photo_name"] or None,
            "consent_privacy": 1, "consent_privacy_at": r["created_at"], "consent_marketing": d.get("consent_marketing") or 0,
            "source": "kiosk", "created_at": now_str(), "created_by": g.user.id, "updated_at": now_str()})
        _insert_history(conn, pid, _history_text(d))
        _attach_consent(conn, r, pid)
        conn.execute("UPDATE kiosk_registrations SET status = 'accepted', patient_id = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                     (pid, g.user.id, now_str(), r["id"]))
        audit.record("patient_created", "patient", pid, "Registered from the kiosk", branch_id=r["branch_id"])
    return pid


def _link_patient(conn, r, d, pid):
    p = conn.one("SELECT * FROM patients WHERE id = ?", (pid,))
    fill = {"middle_name": d.get("middle_name"), "birth_date": d.get("birth_date"), "sex": d.get("sex"), "civil_status": d.get("civil_status"),
            "occupation": d.get("occupation"), "phone": d.get("phone"), "email": d.get("email"), "address": d.get("address"),
            "emergency_contact": _emergency(d), "emergency_phone": d.get("emergency_phone")}
    upd = {k: val for k, val in fill.items() if val and not p[k]}
    if r["photo_name"] and not p["photo"]:
        upd["photo"] = r["photo_name"]
    if not p["consent_privacy"]:
        upd.update({"consent_privacy": 1, "consent_privacy_at": r["created_at"]})
    with conn.transaction():
        if upd:
            conn.update("patients", pid, {**upd, "updated_at": now_str()})
        h = conn.one("SELECT * FROM patient_history WHERE patient_id = ?", (pid,))
        new = _history_text(d)
        if h:
            hupd = {k: val for k, val in new.items() if val and not h[k]}
            if hupd:   # only fields that were empty; column names come from _history_text, not from the form
                conn.execute("UPDATE patient_history SET " + ", ".join(f"{k} = ?" for k in hupd) + ", updated_at = ?, updated_by = ? "
                             "WHERE patient_id = ?", [*hupd.values(), now_str(), g.user.id, pid])
        else:
            _insert_history(conn, pid, new)
        _attach_consent(conn, r, pid)
        conn.execute("UPDATE kiosk_registrations SET status = 'accepted', patient_id = ?, reviewed_by = ?, reviewed_at = ?, review_note = ? "
                     "WHERE id = ?", (pid, g.user.id, now_str(), "Linked to an existing patient", r["id"]))
        audit.record("patient_updated", "patient", pid, "Kiosk registration linked: empty fields filled in", {"fields": sorted(upd)},
                     r["branch_id"])

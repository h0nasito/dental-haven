"""Laboratory cases (e.g. crowns, dentures) sent from the branches to a lab such as DSDL.

Who sees what:
- Users assigned to a laboratory ("Authorized laboratories" on their user account) see every case sent to that lab.
- Clinic users with "View lab cases" see cases from their own branches; with "View lab cases of all branches" too they
  see every branch's cases and the lab workload, but can update only their own branches' cases.
- Super admins see everything.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit, settings
from ..auth import login_required, require
from ..db import get_db
from ..notices import lab_staff, notify
from ..permissions import can_see_patient, patient_scope
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import branches_for_user, dentists

bp = Blueprint("labs", __name__, url_prefix="/staff/lab")

CASE_TYPES = ["Crown (PFM)", "Crown (zirconia / all-ceramic)", "Crown (metal)", "Bridge", "Veneer", "Inlay / onlay",
              "Complete denture", "Partial denture (acrylic)", "Partial denture (flexible)", "Cast partial denture", "Denture repair / reline",
              "Implant crown / abutment", "Retainer", "Night guard / splint", "Temporary crown", "Other"]
from ..lab_status import LATE, OPEN, STATUSES, sql_list  # noqa: E402


def _my_labs():
    return [r["lab_id"] for r in get_db().all("SELECT lab_id FROM user_labs WHERE user_id = ?", (g.user.id,))]


def _scope(alias="c"):
    if g.user.is_super_admin:
        return "1 = 1", []
    parts, params = [], []
    labs = _my_labs()
    if labs:
        parts.append(f"{alias}.lab_id IN ({','.join('?' for _ in labs)})")
        params += labs
    if g.user.can("lab.view") and g.user.can("lab.all_branches"):
        return "1 = 1", []
    if g.user.can("lab.view") and g.user.scope_branch_ids:
        ids = g.user.scope_branch_ids
        parts.append(f"{alias}.branch_id IN ({','.join('?' for _ in ids)})")
        params += ids
    if not parts:
        return "1 = 0", []
    return "(" + " OR ".join(parts) + ")", params


def target_dates(form, sent=None) -> tuple[dict, list[str]]:
    """Trial fitting and final installation target dates from a form. No trial fitting = direct to installation."""
    no_try = 1 if form.get("no_try_in") else 0
    try_in = None if no_try else parse_date(form.get("try_in_on"))
    install = parse_date(form.get("install_on"))
    errors = []
    if form.get("try_in_on") and not no_try and not try_in or form.get("install_on") and not install:
        errors.append("Check the target dates.")
    if try_in and install and try_in > install:
        errors.append("The trial fitting can't be after the final installation (it can be the same day).")
    if sent and any(d and d < sent for d in (try_in, install)):
        errors.append("Target dates can't be before the date sent.")
    return {"try_in_on": try_in.isoformat() if try_in else None, "install_on": install.isoformat() if install else None,
            "no_try_in": no_try}, errors


MAX_CASE_PHOTOS = 12


def save_case_photos(conn, case_id: int, files) -> tuple[int, list[str]]:
    """Save reference photos for a lab case (private storage). Returns (saved, errors)."""
    from ..uploads import save_private_photo as save_private_image
    have = conn.scalar("SELECT COUNT(*) FROM lab_case_photos WHERE case_id = ?", (case_id,)) or 0
    saved, errors = 0, []
    for f in [x for x in files if x and x.filename]:
        if have + saved >= MAX_CASE_PHOTOS:
            errors.append(f"Up to {MAX_CASE_PHOTOS} photos per case.")
            break
        name, err = save_private_image(f, "labcases")
        if err:
            errors.append(f"{f.filename}: {err}")
            continue
        conn.insert("lab_case_photos", {"case_id": case_id, "stored_name": name, "caption": "", "uploaded_by": g.user.id, "created_at": now_str()})
        saved += 1
    return saved, errors


def _can_access():
    return g.user.is_super_admin or g.user.can("lab.view") or bool(_my_labs())


def _load(case_id):
    conn = get_db()
    frag, params = _scope("c")
    c = conn.one("SELECT c.*, l.name AS lab, b.name AS branch, p.first_name, p.last_name, p.chart_no, u.name AS dentist "
                 "FROM lab_cases c JOIN laboratories l ON l.id = c.lab_id JOIN branches b ON b.id = c.branch_id "
                 "JOIN patients p ON p.id = c.patient_id LEFT JOIN users u ON u.id = c.dentist_id "
                 f"WHERE c.id = ? AND {frag}", [case_id, *params])
    if not c:
        abort(404)
    return c


@bp.route("/")
@login_required
def index():
    if not _can_access():
        abort(403)
    conn = get_db()
    frag, params = _scope("c")
    status = request.args.get("status", "open")
    where, args = [frag], list(params)
    all_view = g.user.is_super_admin or (g.user.can("lab.view") and g.user.can("lab.all_branches"))
    branch_list = conn.all("SELECT id, name FROM branches WHERE active = 1 ORDER BY name") if all_view else []
    branch = to_int(request.args.get("branch"))
    if branch and any(b["id"] == branch for b in branch_list):
        where.append("c.branch_id = ?")
        args.append(branch)
        frag, params = frag + " AND c.branch_id = ?", [*params, branch]
    else:
        branch = None
    if status == "open":
        where.append(f"c.status IN {sql_list(OPEN)}")
    elif status in STATUSES:
        where.append("c.status = ?")
        args.append(status)
    rows = conn.all("SELECT c.*, l.name AS lab, b.name AS branch, p.first_name, p.last_name, p.chart_no, u.name AS dentist "
                    "FROM lab_cases c JOIN laboratories l ON l.id = c.lab_id JOIN branches b ON b.id = c.branch_id "
                    "JOIN patients p ON p.id = c.patient_id LEFT JOIN users u ON u.id = c.dentist_id "
                    f"WHERE {' AND '.join(where)} ORDER BY CASE WHEN c.due_on IS NULL THEN 1 ELSE 0 END, c.due_on, c.id DESC LIMIT 300", args)
    counts = {r["status"]: r["n"] for r in conn.all(f"SELECT c.status, COUNT(*) AS n FROM lab_cases c WHERE {frag} GROUP BY c.status", params)}
    t = today()
    workload_cols = [k for k in OPEN if k != "ready"] + ["ready"]
    sums = ", ".join(f"SUM(c.status = '{k}') AS {k}" for k in workload_cols)
    workload = conn.all(
        f"SELECT l.name AS lab, {sums}, "
        f"SUM(c.status IN {sql_list(LATE)} AND c.due_on < ?) AS overdue, "
        f"SUM(c.status IN {sql_list(LATE)} AND c.due_on BETWEEN ? AND ?) AS due_week, COUNT(*) AS total "
        "FROM lab_cases c JOIN laboratories l ON l.id = c.lab_id "
        f"WHERE {frag} AND c.status IN {sql_list(OPEN)} GROUP BY l.id ORDER BY l.name",
        [t.isoformat(), t.isoformat(), (t + timedelta(days=7)).isoformat(), *params])
    # Only the stages that have cases right now, so the table stays readable.
    workload_cols = [k for k in workload_cols if any(w[k] for w in workload)]
    return render_template("staff/labs/index.html", rows=rows, status=status, statuses=STATUSES, counts=counts,
                           today=t.isoformat(), lab_user=bool(_my_labs()), workload=workload, workload_cols=workload_cols, all_view=all_view,
                           branch_list=branch_list, branch=branch)


@bp.route("/new", methods=["GET", "POST"])
@require("lab.manage")
def new():
    conn = get_db()
    labs = conn.all("SELECT * FROM laboratories WHERE active = 1 ORDER BY name")
    patient_id = to_int(request.values.get("patient_id"))
    patient = None
    results = None
    if patient_id:
        if not can_see_patient(conn, g.user, patient_id):
            abort(403)
        patient = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    errors = []
    v = {"lab_id": labs[0]["id"] if labs else None, "branch_id": g.user.active_branch_id or (patient["preferred_branch_id"] if patient else None),
         "dentist_id": g.user.id if g.user.role == "dentist" else None, "case_type": CASE_TYPES[0], "teeth": "", "shade": "",
         "material": "", "instructions": "", "sent_on": today().isoformat(), "due_on": "", "lab_fee": ""}
    if request.method == "POST" and request.form.get("action") == "search":
        q = clean(request.form.get("q"), 80).lower()
        frag, params = patient_scope(g.user, "p")
        like = f"%{q}%"
        results = conn.all(f"SELECT p.id, p.chart_no, p.first_name, p.last_name FROM patients p WHERE {frag} AND p.active = 1 AND "
                           "(lower(p.first_name || ' ' || p.last_name) LIKE ? OR lower(p.chart_no) LIKE ?) ORDER BY p.last_name LIMIT 20",
                           [*params, like, like]) if len(q) >= 2 else []
    elif request.method == "POST" and patient:
        v = {k: clean(request.form.get(k), 1000) for k in v}
        lab_id, branch_id, dentist_id = to_int(v["lab_id"]), to_int(v["branch_id"]), to_int(v["dentist_id"])
        if not any(l["id"] == lab_id for l in labs):
            errors.append("Choose a laboratory.")
        if not branch_id or not g.user.in_branch(branch_id):
            errors.append("Choose one of your branches.")
        if v["case_type"] not in CASE_TYPES:
            errors.append("Choose the case type.")
        sent, due = parse_date(v["sent_on"]), parse_date(v["due_on"]) if v["due_on"] else None
        if not sent:
            errors.append("Enter the date sent.")
        if due and sent and due < sent:
            errors.append("The due date can't be before the date sent.")
        fee = parse_money(v["lab_fee"]) if v["lab_fee"] else None
        if v["lab_fee"] and fee is None:
            errors.append("Enter the lab fee like 3500 or 3500.00.")
        targets, terr = target_dates(request.form, sent)
        errors += terr
        v.update({k: request.form.get(k, "") for k in ("try_in_on", "install_on")}, no_try_in=targets["no_try_in"])
        if not errors:
            with conn.transaction():
                cid = conn.insert("lab_cases", {"lab_id": lab_id, "branch_id": branch_id, "patient_id": patient["id"], "dentist_id": dentist_id,
                                                "case_type": v["case_type"], "teeth": v["teeth"][:60], "shade": v["shade"][:30],
                                                "material": v["material"][:80], "instructions": v["instructions"], "status": "sent",
                                                "sent_on": sent.isoformat(), "due_on": due.isoformat() if due else None, "lab_fee_cents": fee,
                                                **targets,
                                                "created_by": g.user.id, "created_at": now_str(), "updated_at": now_str()})
                conn.insert("lab_case_events", {"case_id": cid, "user_id": g.user.id, "status": "sent", "note": "Case created", "created_at": now_str()})
                n_photos, photo_errors = save_case_photos(conn, cid, request.files.getlist("photos"))
                for e_ in photo_errors:
                    flash(e_, "error")
                audit.record("lab_case_created", "patient", patient["id"], f"Lab case #{cid}: {v['case_type']}", {"lab_case_id": cid}, branch_id)
                branch = conn.one("SELECT name FROM branches WHERE id = ?", (branch_id,))
                notify(conn, lab_staff(conn, lab_id), "lab_case_new", f"New lab case #{cid}: {v['case_type']}",
                       f"From {branch['name'] if branch else 'a branch'}" + (f", due {due.isoformat()}" if due else ""), f"/staff/lab/{cid}",
                       exclude=g.user.id)
            flash("Lab case created.", "success")
            return redirect(url_for("labs.case", case_id=cid))
    return render_template("staff/labs/new.html", labs=labs, patient=patient, results=results, v=v, errors=errors, case_types=CASE_TYPES,
                           branches=branches_for_user(g.user), dentists=dentists(g.user.branch_ids))


@bp.route("/<int:case_id>", methods=["GET", "POST"])
@login_required
def case(case_id):
    if not _can_access():
        abort(403)
    conn = get_db()
    c = _load(case_id)
    lab_user = c["lab_id"] in _my_labs()
    # Other branches' cases are view only: updates stay with the branch that sent the case (and the lab).
    can_update = (g.user.can("lab.manage") and g.user.in_branch(c["branch_id"])) or lab_user or g.user.is_super_admin
    if request.method == "POST":
        if not can_update:
            abort(403)
        st = request.form.get("status")
        note = clean(request.form.get("note"), 500)
        if st not in STATUSES:
            abort(400)
        upd = {"status": st, "updated_at": now_str()}
        if st == "delivered":
            upd["completed_on"] = today().isoformat()
        due = parse_date(request.form.get("due_on"))
        if due:
            upd["due_on"] = due.isoformat()
        fee = parse_money(request.form.get("lab_fee")) if request.form.get("lab_fee") else None
        if fee is not None:
            upd["lab_fee_cents"] = fee
        if "install_on" in request.form:
            targets, terr = target_dates(request.form, parse_date(c["sent_on"]))
            if terr:
                for e_ in terr:
                    flash(e_, "error")
                return redirect(url_for("labs.case", case_id=case_id))
            if (targets["try_in_on"], targets["install_on"], targets["no_try_in"]) != (c["try_in_on"], c["install_on"], c["no_try_in"]):
                upd.update(targets)
                fmt = lambda d: d or "not set"  # noqa: E731
                tnote = ("Targets: direct to installation" if targets["no_try_in"] else f"Targets: trial fitting {fmt(targets['try_in_on'])}") + \
                        f", installation {fmt(targets['install_on'])}"
                note = f"{note}; {tnote}" if note else tnote
        conn.update("lab_cases", case_id, upd)
        conn.insert("lab_case_events", {"case_id": case_id, "user_id": g.user.id, "status": st, "note": note, "created_at": now_str()})
        if st != c["status"]:
            watchers = set(lab_staff(conn, c["lab_id"])) | {c["created_by"], c["dentist_id"]}
            notify(conn, watchers, "lab_case_status", f"Lab case #{case_id} is now {STATUSES[st]}", f"{c['case_type']} · {c['branch']}",
                   f"/staff/lab/{case_id}", exclude=g.user.id)
        audit.record("lab_case_updated", "patient", c["patient_id"], f"Lab case #{case_id} → {STATUSES[st]}", {"note": note}, c["branch_id"])
        flash("Lab case updated.", "success")
        return redirect(url_for("labs.case", case_id=case_id))
    events = conn.all("SELECT e.*, u.name AS by_name FROM lab_case_events e LEFT JOIN users u ON u.id = e.user_id WHERE e.case_id = ? ORDER BY e.id DESC",
                      (case_id,))
    fittings = conn.all("SELECT f.*, d.name AS dentist_name, u.name AS by_name FROM lab_case_fittings f LEFT JOIN users d ON d.id = f.dentist_id "
                        "LEFT JOIN users u ON u.id = f.created_by WHERE f.case_id = ? ORDER BY f.id DESC", (case_id,))
    from ..lab_commission import entries, technicians
    lab_invoice = conn.one("SELECT number, status, total_cents, paid_cents FROM lab_invoices WHERE id = ?", (c["invoice_id"],)) if c["invoice_id"] else None
    photos = conn.all("SELECT ph.*, u.name AS by_name FROM lab_case_photos ph LEFT JOIN users u ON u.id = ph.uploaded_by WHERE ph.case_id = ? ORDER BY ph.id",
                      (case_id,))
    return render_template("staff/labs/case.html", c=c, events=events, statuses=STATUSES, can_update=can_update, lab_invoice=lab_invoice, photos=photos, max_photos=MAX_CASE_PHOTOS,
                           can_bill=g.user.is_super_admin or (lab_user and g.user.can("lab.billing")),
                           comm_entries=entries(conn, case_id=c["id"]), comm_techs=technicians(conn),
                           patient_link=can_see_patient(conn, g.user, c["patient_id"]), fittings=fittings,
                           can_fit=_can_record_fitting(conn, c), fit_results=FIT_RESULTS, fit_checks=FIT_CHECKS,
                           agreement=agreement_text(conn, c), today=today().isoformat(),
                           fit_dentists=dentists([c["branch_id"]]))


@bp.route("/<int:case_id>/photos", methods=["POST"])
@login_required
def case_photos(case_id):
    """Add reference photos to a case, or remove one (the uploader, lab managers and super admins)."""
    if not _can_access():
        abort(403)
    conn = get_db()
    c = _load(case_id)
    if request.form.get("action") == "remove":
        ph = conn.one("SELECT * FROM lab_case_photos WHERE id = ? AND case_id = ?", (to_int(request.form.get("photo_id")), case_id))
        if not ph:
            abort(404)
        if not (g.user.is_super_admin or ph["uploaded_by"] == g.user.id or g.user.can("lab.manage")):
            abort(403)
        conn.execute("DELETE FROM lab_case_photos WHERE id = ?", (ph["id"],))
        audit.record("lab_case_photo_removed", "patient", c["patient_id"], f"Removed a photo from lab case #{case_id}", branch_id=c["branch_id"])
        flash("Photo removed.", "success")
    else:
        saved, errors = save_case_photos(conn, case_id, request.files.getlist("photos"))
        for e_ in errors:
            flash(e_, "error")
        if saved:
            caption = clean(request.form.get("caption"), 200)
            if caption:
                conn.execute("UPDATE lab_case_photos SET caption = ? WHERE id IN (SELECT id FROM lab_case_photos WHERE case_id = ? ORDER BY id DESC LIMIT ?)",
                             (caption, case_id, saved))
            conn.insert("lab_case_events", {"case_id": case_id, "user_id": g.user.id, "status": c["status"],
                                            "note": f"Added {saved} photo{'s' if saved != 1 else ''}", "created_at": now_str()})
            audit.record("lab_case_photo_added", "patient", c["patient_id"], f"Added {saved} photo(s) to lab case #{case_id}", branch_id=c["branch_id"])
            flash(f"{saved} photo{'s' if saved != 1 else ''} added.", "success")
    return redirect(url_for("labs.case", case_id=case_id) + "#photos")


@bp.route("/<int:case_id>/photos/<int:photo_id>")
@login_required
def case_photo(case_id, photo_id):
    from ..uploads import document_path
    if not _can_access():
        abort(403)
    _load(case_id)   # same access as the case itself (branch staff and the lab)
    ph = get_db().one("SELECT * FROM lab_case_photos WHERE id = ? AND case_id = ?", (photo_id, case_id))
    if not ph:
        abort(404)
    resp = send_file(document_path(ph["stored_name"]), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ---------------------------------------------------------------------------
# Trial fitting (try-in) agreement: the patient and the dentist sign that the case may go on to final processing.
# ---------------------------------------------------------------------------
FIT_RESULTS = {"approved": "Approved: proceed with final processing", "adjust": "Adjustments needed first (not approved yet)",
               "remake": "Remake needed"}
FIT_CHECKS = ["Fit", "Shape", "Color / shade", "Bite", "Comfort"]
RELATIONS = {"patient": "Patient", "parent": "Parent", "guardian": "Guardian", "representative": "Authorized representative"}


def agreement_text(conn, c) -> str:
    text = settings.get("lab.fitting_agreement", conn) or settings.DEFAULTS["lab.fitting_agreement"]
    for key in ("case_type", "teeth", "shade"):
        text = text.replace("{" + key + "}", (c[key] or "—"))
    return text


def _can_record_fitting(conn, c) -> bool:
    """Branch side only (the patient is at the clinic): dentists, lab managers of the branch, super admins."""
    if not can_see_patient(conn, g.user, c["patient_id"]):
        return False
    if g.user.is_super_admin:
        return True
    return g.user.in_branch(c["branch_id"]) and (g.user.role == "dentist" or g.user.can("lab.manage"))


@bp.route("/<int:case_id>/fitting", methods=["POST"])
@login_required
def fitting(case_id):
    from ..uploads import save_signature
    if not _can_access():
        abort(403)
    conn = get_db()
    c = _load(case_id)
    if not _can_record_fitting(conn, c):
        abort(403)
    f = request.form
    result = f.get("result")
    fitted_on = parse_date(f.get("fitted_on")) or today()
    checks = [x for x in f.getlist("checks") if x in FIT_CHECKS]
    notes = clean(f.get("notes"), 2000)
    agreement = clean(f.get("agreement"), 4000) or agreement_text(conn, c)
    relation = f.get("signer_relation") if f.get("signer_relation") in RELATIONS else "patient"
    signer = clean(f.get("signer_name"), 120) or f"{c['first_name']} {c['last_name']}"
    dentist_id = to_int(f.get("dentist_id")) or c["dentist_id"] or (g.user.id if g.user.role == "dentist" else None)
    not_signed = clean(f.get("not_signed_reason"), 300)
    errors = []
    if result not in FIT_RESULTS:
        errors.append("Choose the result of the trial fitting.")
    if fitted_on > today():
        errors.append("The fitting date can't be in the future.")
    if result == "adjust" and not notes:
        errors.append("Write what needs to be adjusted.")
    pat_sig = dent_sig = None
    if (f.get("patient_signature") or "").strip():
        pat_sig, err = save_signature(f["patient_signature"])
        if err:
            errors.append(err)
    elif not not_signed:
        errors.append("Ask the patient (or their parent / guardian) to sign, or write why they can't.")
    if (f.get("dentist_signature") or "").strip():
        dent_sig, err = save_signature(f["dentist_signature"])
        if err:
            errors.append(err.replace("the patient", "the dentist"))
    elif result == "approved":
        errors.append("The dentist signs too, to agree that the case may proceed.")
    if not dentist_id:
        errors.append("Choose the dentist.")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("labs.case", case_id=case_id) + "#fitting")
    body = "; ".join(x for x in (("Checked: " + ", ".join(checks)) if checks else "", notes) if x)
    with conn.transaction():
        fid = conn.insert("lab_case_fittings", {
            "case_id": case_id, "fitted_on": fitted_on.isoformat(), "result": result, "notes": body, "agreement_text": agreement,
            "signer_name": signer, "signer_relation": relation, "patient_signature": pat_sig,
            "not_signed_reason": "" if pat_sig else not_signed, "dentist_id": dentist_id, "dentist_signature": dent_sig,
            "created_by": g.user.id, "created_at": now_str()})
        # Back from the try-in: the case returns to the lab (Accepted) unless it must be remade.
        new_status = "remake" if result == "remake" else "accepted" if c["status"] == "try_in" else c["status"]
        if new_status != c["status"]:
            conn.update("lab_cases", case_id, {"status": new_status, "updated_at": now_str()})
        label = {"approved": "Trial fitting approved by the patient and the dentist: proceed with final processing",
                 "adjust": "Trial fitting: adjustments needed before final processing",
                 "remake": "Trial fitting: remake needed"}[result]
        conn.insert("lab_case_events", {"case_id": case_id, "user_id": g.user.id, "status": new_status,
                                        "note": label + (f" ({notes})" if notes and result != "approved" else ""), "created_at": now_str()})
        watchers = set(lab_staff(conn, c["lab_id"])) | {c["created_by"], c["dentist_id"]}
        notify(conn, watchers, "lab_case_fitting", f"Lab case #{case_id}: " + {"approved": "trial fitting approved, proceed",
                                                                                "adjust": "adjust after trial fitting",
                                                                                "remake": "remake after trial fitting"}[result],
               f"{c['case_type']} · {c['branch']}", f"/staff/lab/{case_id}", exclude=g.user.id)
        audit.record("lab_fitting_recorded", "patient", c["patient_id"], f"Lab case #{case_id}: trial fitting {result}",
                     {"fitting_id": fid, "signed": bool(pat_sig)}, c["branch_id"])
    flash("Trial fitting saved." + (" The lab has been told to proceed." if result == "approved" else ""), "success")
    return redirect(url_for("labs.case", case_id=case_id) + "#fitting")


def _fitting_for(fid):
    conn = get_db()
    ft = conn.one("SELECT * FROM lab_case_fittings WHERE id = ?", (fid,))
    if not ft:
        abort(404)
    c = _load(ft["case_id"])
    if not can_see_patient(conn, g.user, c["patient_id"]):
        abort(403)  # e.g. lab-only accounts: they see that it was signed, not the signatures
    return ft, c


@bp.route("/fitting/<int:fid>/signature/<who>")
@login_required
def fitting_signature(fid, who):
    from ..uploads import document_path
    ft, _c = _fitting_for(fid)
    name = ft["patient_signature"] if who == "patient" else ft["dentist_signature"] if who == "dentist" else None
    if not name:
        abort(404)
    resp = send_file(document_path(name), mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/fitting/<int:fid>/print")
@login_required
def fitting_print(fid):
    ft, c = _fitting_for(fid)
    conn = get_db()
    dentist = conn.one("SELECT name, license_no FROM users WHERE id = ?", (ft["dentist_id"],)) if ft["dentist_id"] else None
    branch = conn.one("SELECT * FROM branches WHERE id = ?", (c["branch_id"],))
    return render_template("staff/labs/fitting_print.html", f=ft, c=c, dentist=dentist, branch=branch, results=FIT_RESULTS,
                           relations=RELATIONS)

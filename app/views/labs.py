"""Laboratory cases (e.g. crowns, dentures) sent from the branches to a lab such as DSDL.

Who sees what:
- Users assigned to a laboratory ("Authorized laboratories" on their user account) see every case sent to that lab.
- Clinic users with "View lab cases" see cases from their own branches.
- Super admins see everything.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import login_required, require
from ..db import get_db
from ..permissions import can_see_patient, patient_scope
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import branches_for_user, dentists

bp = Blueprint("labs", __name__, url_prefix="/staff/lab")

CASE_TYPES = ["Crown (PFM)", "Crown (zirconia / all-ceramic)", "Crown (metal)", "Bridge", "Veneer", "Inlay / onlay",
              "Complete denture", "Partial denture (acrylic)", "Partial denture (flexible)", "Cast partial denture", "Denture repair / reline",
              "Implant crown / abutment", "Retainer", "Night guard / splint", "Temporary crown", "Other"]
STATUSES = {"sent": "Sent to lab", "received": "Received by lab", "in_progress": "In progress", "ready": "Ready for pick-up",
            "delivered": "Delivered to clinic", "remake": "Remake needed", "cancelled": "Cancelled"}
OPEN = ("sent", "received", "in_progress", "ready", "remake")


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
    if g.user.can("lab.view") and g.user.scope_branch_ids:
        ids = g.user.scope_branch_ids
        parts.append(f"{alias}.branch_id IN ({','.join('?' for _ in ids)})")
        params += ids
    if not parts:
        return "1 = 0", []
    return "(" + " OR ".join(parts) + ")", params


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
    if status == "open":
        where.append("c.status IN ('sent','received','in_progress','ready','remake')")
    elif status in STATUSES:
        where.append("c.status = ?")
        args.append(status)
    rows = conn.all("SELECT c.*, l.name AS lab, b.name AS branch, p.first_name, p.last_name, p.chart_no, u.name AS dentist "
                    "FROM lab_cases c JOIN laboratories l ON l.id = c.lab_id JOIN branches b ON b.id = c.branch_id "
                    "JOIN patients p ON p.id = c.patient_id LEFT JOIN users u ON u.id = c.dentist_id "
                    f"WHERE {' AND '.join(where)} ORDER BY CASE WHEN c.due_on IS NULL THEN 1 ELSE 0 END, c.due_on, c.id DESC LIMIT 300", args)
    counts = {r["status"]: r["n"] for r in conn.all(f"SELECT c.status, COUNT(*) AS n FROM lab_cases c WHERE {frag} GROUP BY c.status", params)}
    return render_template("staff/labs/index.html", rows=rows, status=status, statuses=STATUSES, counts=counts,
                           today=today().isoformat(), lab_user=bool(_my_labs()))


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
        if not errors:
            with conn.transaction():
                cid = conn.insert("lab_cases", {"lab_id": lab_id, "branch_id": branch_id, "patient_id": patient["id"], "dentist_id": dentist_id,
                                                "case_type": v["case_type"], "teeth": v["teeth"][:60], "shade": v["shade"][:30],
                                                "material": v["material"][:80], "instructions": v["instructions"], "status": "sent",
                                                "sent_on": sent.isoformat(), "due_on": due.isoformat() if due else None, "lab_fee_cents": fee,
                                                "created_by": g.user.id, "created_at": now_str(), "updated_at": now_str()})
                conn.insert("lab_case_events", {"case_id": cid, "user_id": g.user.id, "status": "sent", "note": "Case created", "created_at": now_str()})
                audit.record("lab_case_created", "patient", patient["id"], f"Lab case #{cid}: {v['case_type']}", {"lab_case_id": cid}, branch_id)
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
    can_update = g.user.can("lab.manage") or lab_user or g.user.is_super_admin
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
        conn.update("lab_cases", case_id, upd)
        conn.insert("lab_case_events", {"case_id": case_id, "user_id": g.user.id, "status": st, "note": note, "created_at": now_str()})
        audit.record("lab_case_updated", "patient", c["patient_id"], f"Lab case #{case_id} → {STATUSES[st]}", {"note": note}, c["branch_id"])
        flash("Lab case updated.", "success")
        return redirect(url_for("labs.case", case_id=case_id))
    events = conn.all("SELECT e.*, u.name AS by_name FROM lab_case_events e LEFT JOIN users u ON u.id = e.user_id WHERE e.case_id = ? ORDER BY e.id DESC",
                      (case_id,))
    return render_template("staff/labs/case.html", c=c, events=events, statuses=STATUSES, can_update=can_update,
                           patient_link=can_see_patient(conn, g.user, c["patient_id"]))

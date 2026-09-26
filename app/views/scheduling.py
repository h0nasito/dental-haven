"""Appointments, calendars and online booking requests."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, dentist_mail
from ..auth import require
from ..db import get_db
from ..messaging import cancel_appointment_reminders, schedule_appointment_reminders
from ..permissions import branch_filter, can_see_patient, patient_scope
from ..scheduling import (SOURCES, STATUSES, TRANSITIONS, ensure_assignment, free_resource, service_duration,
                          validate_slot)
from ..util import clean, fmt_dt, now, now_str, parse_date, parse_dt, to_int, today, week_start
from .common import branches_for_user, dentists, paginate, services

bp = Blueprint("sched", __name__, url_prefix="/staff")

APPT_SELECT = (
    "SELECT a.*, p.first_name, p.last_name, p.chart_no, p.alert_flag, p.phone AS patient_phone, s.name AS service, "
    "u.name AS dentist, b.name AS branch, r.name AS resource FROM appointments a "
    "JOIN patients p ON p.id = a.patient_id JOIN services s ON s.id = a.service_id "
    "JOIN branches b ON b.id = a.branch_id LEFT JOIN users u ON u.id = a.dentist_id "
    "LEFT JOIN resources r ON r.id = a.resource_id"
)


def _appt_scope(user, alias="a"):
    if user.own_schedule_only:
        return f"{alias}.dentist_id = ?", [user.id]
    return branch_filter(user, f"{alias}.branch_id")


def _load_appt(appt_id):
    conn = get_db()
    a = conn.one(APPT_SELECT + " WHERE a.id = ?", (appt_id,))
    if not a:
        abort(404)
    u = g.user
    if u.own_schedule_only:
        if a["dentist_id"] != u.id:
            abort(403)
    elif not u.in_branch(a["branch_id"]):
        abort(403)
    return a


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

@bp.route("/calendar")
@require("appointments.view")
def calendar():
    conn = get_db()
    user = g.user
    view = request.args.get("view", "day")
    day = parse_date(request.args.get("date")) or today()
    dentist_id = to_int(request.args.get("dentist"))
    if user.own_schedule_only:
        dentist_id = user.id
    scope, params = _appt_scope(user)
    if view == "week":
        start = week_start(day)
        end = start + timedelta(days=7)
    else:
        start, end = day, day + timedelta(days=1)
    where = [scope, "a.start_at >= ?", "a.start_at < ?"]
    args = [*params, start.isoformat(), end.isoformat()]
    if dentist_id:
        where.append("a.dentist_id = ?")
        args.append(dentist_id)
    if not request.args.get("show_cancelled"):
        where.append("a.status NOT IN ('cancelled')")
    appts = conn.all(APPT_SELECT + f" WHERE {' AND '.join(where)} ORDER BY a.start_at", args)
    dentist_list = dentists(user.scope_branch_ids)
    columns, hours = [], (8, 19)
    if view == "day":
        # columns: one per dentist with appointments or schedule; plus "Unassigned"
        ids = [d["id"] for d in dentist_list] if not dentist_id else [dentist_id]
        names = {d["id"]: d["name"] for d in dentists()}
        for did in ids:
            columns.append({"id": did, "name": names.get(did, "Dentist"), "appts": [a for a in appts if a["dentist_id"] == did]})
        unassigned = [a for a in appts if not a["dentist_id"]]
        if unassigned and not dentist_id:
            columns.append({"id": None, "name": "No dentist yet", "appts": unassigned})
        if user.scope_branch_ids:
            marks = ",".join("?" for _ in user.scope_branch_ids)
            bh = conn.one(f"SELECT MIN(open_time) AS o, MAX(close_time) AS c FROM branch_hours WHERE closed = 0 AND weekday = ? "
                          f"AND branch_id IN ({marks})", [day.weekday(), *user.scope_branch_ids])
            if bh and bh["o"]:
                hours = (int(bh["o"][:2]), min(22, int(bh["c"][:2]) + (1 if bh["c"][3:] != "00" else 0)))
        for c in columns:
            for a in c["appts"]:
                s, e = parse_dt(a["start_at"]), parse_dt(a["end_at"])
                a["top"] = ((s.hour - hours[0]) * 60 + s.minute)
                a["height"] = max(22, int((e - s).total_seconds() // 60) - 2)
    days = []
    if view == "week":
        for i in range(7):
            d = start + timedelta(days=i)
            days.append({"date": d, "appts": [a for a in appts if a["start_at"][:10] == d.isoformat()]})
    return render_template("staff/sched/calendar.html", view=view, day=day, appts=appts, columns=columns,
                           hours=hours, days=days, dentists=dentist_list, dentist_id=dentist_id,
                           prev=(day - timedelta(days=7 if view == "week" else 1)).isoformat(),
                           next=(day + timedelta(days=7 if view == "week" else 1)).isoformat())


@bp.route("/appointments")
@require("appointments.view")
def appointments():
    conn = get_db()
    user = g.user
    scope, params = _appt_scope(user)
    d_from = parse_date(request.args.get("from")) or today()
    d_to = parse_date(request.args.get("to")) or (d_from + timedelta(days=13))
    where = [scope, "a.start_at >= ?", "a.start_at < ?"]
    args = [*params, d_from.isoformat(), (d_to + timedelta(days=1)).isoformat()]
    status = request.args.get("status")
    if status in STATUSES:
        where.append("a.status = ?")
        args.append(status)
    dentist_id = to_int(request.args.get("dentist"))
    if dentist_id and not user.own_schedule_only:
        where.append("a.dentist_id = ?")
        args.append(dentist_id)
    source = request.args.get("source")
    if source in SOURCES:
        where.append("a.source = ?")
        args.append(source)
    total = conn.scalar(f"SELECT COUNT(*) FROM appointments a WHERE {' AND '.join(where)}", args)
    pg = paginate(total, 50)
    rows = conn.all(APPT_SELECT + f" WHERE {' AND '.join(where)} ORDER BY a.start_at LIMIT ? OFFSET ?",
                    [*args, pg["limit"], pg["offset"]])
    return render_template("staff/sched/appointments.html", rows=rows, pg=pg, d_from=d_from, d_to=d_to,
                           dentists=dentists(user.scope_branch_ids), status=status, dentist_id=dentist_id, source=source)


# ---------------------------------------------------------------------------
# Create / view / update appointments
# ---------------------------------------------------------------------------

def _search_patients(conn, q):
    frag, params = patient_scope(g.user, "p")
    like = f"%{q.lower()}%"
    return conn.all(
        f"SELECT p.id, p.chart_no, p.first_name, p.last_name, p.birth_date, p.phone FROM patients p WHERE {frag} AND p.active = 1 "
        "AND (lower(p.first_name || ' ' || p.last_name) LIKE ? OR lower(p.last_name || ', ' || p.first_name) LIKE ? "
        "OR p.phone LIKE ? OR lower(p.chart_no) LIKE ? OR p.legacy_id = ?) ORDER BY p.last_name, p.first_name LIMIT 20",
        [*params, like, like, like, like, q])


@bp.route("/appointments/new", methods=["GET", "POST"])
@require("appointments.manage")
def appointment_new():
    conn = get_db()
    user = g.user
    patient_id = to_int(request.values.get("patient_id"))
    patient = None
    results = None
    if patient_id:
        if not can_see_patient(conn, user, patient_id):
            abort(403)
        patient = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    branches = branches_for_user(user)
    default_branch = user.active_branch_id or (patient["preferred_branch_id"] if patient and patient["preferred_branch_id"] in user.branch_ids else None) \
        or (branches[0]["id"] if branches else None)
    v = {"branch_id": default_branch, "service_id": None, "dentist_id": None, "resource_id": None,
         "date": request.args.get("date") or today().isoformat(), "time": request.args.get("time", "09:00"),
         "duration": "", "status": "confirmed", "source": "staff", "internal_notes": ""}
    errors = {}
    if request.method == "POST" and request.form.get("action") == "search":
        q = clean(request.form.get("q"), 80)
        results = _search_patients(conn, q) if len(q) >= 2 else []
    elif request.method == "POST" and patient:
        v = {
            "branch_id": to_int(request.form.get("branch_id")), "service_id": to_int(request.form.get("service_id")),
            "dentist_id": to_int(request.form.get("dentist_id")), "resource_id": to_int(request.form.get("resource_id")),
            "date": clean(request.form.get("date"), 10), "time": clean(request.form.get("time"), 5),
            "duration": clean(request.form.get("duration"), 4), "status": request.form.get("status", "confirmed"),
            "source": request.form.get("source", "staff"), "internal_notes": clean(request.form.get("internal_notes"), 2000),
        }
        errors = _validate_and_save(conn, patient, v)
        if isinstance(errors, int):
            if v["status"] == "confirmed":
                dentist_mail.notify(conn, errors, "confirmed", v["dentist_id"])
            flash("Appointment saved.", "success")
            return redirect(url_for("sched.appointment", appt_id=errors))
    return render_template("staff/sched/appointment_form.html", patient=patient, results=results, v=v, errors=errors,
                           branches=branches, services=services(), dentists=dentists(user.branch_ids),
                           resources=_resources(conn, user.branch_ids), sources=SOURCES)


def _resources(conn, branch_ids):
    if not branch_ids:
        return []
    marks = ",".join("?" for _ in branch_ids)
    return conn.all(f"SELECT r.*, b.name AS branch FROM resources r JOIN branches b ON b.id = r.branch_id "
                    f"WHERE r.active = 1 AND r.branch_id IN ({marks}) ORDER BY b.sort_order, r.name", branch_ids)


def _validate_and_save(conn, patient, v, appt=None):
    """Create (appt=None) or reschedule an appointment. Returns the appointment id or an errors dict."""
    errors = {}
    user = g.user
    if not v["branch_id"] or not user.in_branch(v["branch_id"]):
        errors["branch_id"] = "Choose one of your branches."
    svc = conn.one("SELECT * FROM services WHERE id = ? AND active = 1", (v["service_id"],)) if v["service_id"] else None
    if not svc:
        errors["service_id"] = "Choose a service."
    if v["dentist_id"] and not conn.one("SELECT 1 AS x FROM users u JOIN user_branches ub ON ub.user_id = u.id "
                                        "WHERE u.id = ? AND u.role='dentist' AND u.active=1 AND ub.branch_id = ?",
                                        (v["dentist_id"], v["branch_id"] or 0)):
        errors["dentist_id"] = "That dentist doesn't work at this branch."
    if v["resource_id"] and not conn.one("SELECT id FROM resources WHERE id = ? AND branch_id = ? AND active = 1",
                                         (v["resource_id"], v["branch_id"] or 0)):
        errors["resource_id"] = "That room isn't at this branch."
    start = parse_dt(f"{v['date']} {v['time']}")
    if not start:
        errors["date"] = "Enter a valid date and time."
    if v.get("status") not in ("confirmed", "requested"):
        v["status"] = "confirmed"
    if v.get("source") not in SOURCES:
        v["source"] = "staff"
    if errors:
        return errors
    minutes = to_int(v["duration"]) or service_duration(conn, v["service_id"], v["branch_id"], v["dentist_id"])
    if not 5 <= minutes <= 480:
        return {"duration": "Duration must be between 5 and 480 minutes."}
    end = start + timedelta(minutes=minutes)
    exclude = appt["id"] if appt else None
    with conn.transaction(immediate=True):
        resource_id = v["resource_id"]
        if not resource_id:
            resource_id, has_res = free_resource(conn, v["branch_id"], fmt_dt(start), fmt_dt(end), exclude_id=exclude)
            if has_res and not resource_id:
                return {"_form": ["All rooms at this branch are booked at that time."]}
        problems = validate_slot(conn, branch_id=v["branch_id"], start=start, end=end, dentist_id=v["dentist_id"],
                                 resource_id=resource_id, exclude_id=exclude)
        if problems:
            return {"_form": problems}
        if appt is None:
            appt_id = conn.insert("appointments", {
                "patient_id": patient["id"], "branch_id": v["branch_id"], "service_id": v["service_id"],
                "dentist_id": v["dentist_id"], "resource_id": resource_id, "start_at": fmt_dt(start), "end_at": fmt_dt(end),
                "status": v["status"], "source": v["source"], "internal_notes": v["internal_notes"],
                "created_by": user.id, "created_at": now_str(),
            })
            audit.record("appointment_created", "appointment", appt_id,
                         f"Booked {svc['name']} {fmt_dt(start)} ({v['status']})", {"source": v["source"]}, v["branch_id"])
        else:
            appt_id = appt["id"]
            before = {k: appt[k] for k in ("branch_id", "service_id", "dentist_id", "resource_id", "start_at", "end_at")}
            after = {"branch_id": v["branch_id"], "service_id": v["service_id"], "dentist_id": v["dentist_id"],
                     "resource_id": resource_id, "start_at": fmt_dt(start), "end_at": fmt_dt(end)}
            conn.update("appointments", appt_id, {**after, "updated_at": now_str()})
            audit.record("appointment_rescheduled", "appointment", appt_id, f"Rescheduled to {fmt_dt(start)}",
                         audit.diff(before, after, after.keys()), v["branch_id"])
            cancel_appointment_reminders(conn, appt_id, "Rescheduled", regenerate=True)
        ensure_assignment(conn, patient["id"], v["dentist_id"], user.id)
        schedule_appointment_reminders(conn, appt_id)
    return appt_id


@bp.route("/appointments/<int:appt_id>")
@require("appointments.view")
def appointment(appt_id):
    conn = get_db()
    a = _load_appt(appt_id)
    history = conn.all("SELECT al.*, u.name AS actor FROM audit_log al LEFT JOIN users u ON u.id = al.actor_id "
                       "WHERE entity_type = 'appointment' AND entity_id = ? ORDER BY al.id DESC", (appt_id,))
    reminders = conn.all("SELECT * FROM reminders WHERE appointment_id = ? ORDER BY scheduled_for", (appt_id,))
    dentist_emails = conn.all("SELECT e.*, u.name AS dentist FROM dentist_emails e JOIN users u ON u.id = e.user_id "
                              "WHERE e.appointment_id = ? ORDER BY e.id DESC", (appt_id,))
    invoices = conn.all("SELECT * FROM invoices WHERE appointment_id = ?", (appt_id,)) if g.user.can("billing.view") else []
    return render_template("staff/sched/appointment.html", a=a, history=history, reminders=reminders, invoices=invoices, dentist_emails=dentist_emails,
                           email_events=dentist_mail.EVENTS, email_status=dentist_mail.STATUS_LABELS,
                           transitions=TRANSITIONS.get(a["status"], set()), services=services(),
                           dentists=dentists([a["branch_id"]]), resources=_resources(conn, [a["branch_id"]]),
                           branches=branches_for_user(g.user))


@bp.route("/appointments/<int:appt_id>/status", methods=["POST"])
@require("appointments.view")
def appointment_status(appt_id):
    conn = get_db()
    a = _load_appt(appt_id)
    new = request.form.get("status")
    if new not in TRANSITIONS.get(a["status"], set()):
        flash("That status change isn't allowed.", "error")
        return redirect(url_for("sched.appointment", appt_id=appt_id))
    needed = "appointments.complete" if new in ("checked_in", "completed", "no_show") else "appointments.manage"
    if not g.user.can(needed):
        abort(403)
    reason = clean(request.form.get("reason"), 500)
    if new == "cancelled" and not reason:
        flash("Give a reason for the cancellation.", "error")
        return redirect(url_for("sched.appointment", appt_id=appt_id))
    values = {"status": new, "updated_at": now_str()}
    if new == "checked_in":
        values["checked_in_at"] = now_str()
    if new == "completed":
        values["completed_at"] = now_str()
    if new == "cancelled":
        values["cancel_reason"] = reason
    with conn.transaction(immediate=True):
        if new == "confirmed":
            problems = validate_slot(conn, branch_id=a["branch_id"], start=parse_dt(a["start_at"]), end=parse_dt(a["end_at"]),
                                     dentist_id=a["dentist_id"], resource_id=a["resource_id"], exclude_id=appt_id, allow_past=True)
            if problems:
                flash("Can't confirm: " + " ".join(problems), "error")
                return redirect(url_for("sched.appointment", appt_id=appt_id))
        conn.update("appointments", appt_id, values)
        audit.record("appointment_status", "appointment", appt_id, f"{STATUSES[a['status']]} → {STATUSES[new]}",
                     {"reason": reason} if reason else {}, a["branch_id"])
        if new == "confirmed":
            schedule_appointment_reminders(conn, appt_id)
        if new in ("cancelled", "no_show", "completed"):
            cancel_appointment_reminders(conn, appt_id, STATUSES[new])
        if new == "no_show" and g.user.can("followups.manage"):
            fid = conn.insert("follow_ups", {
                "branch_id": a["branch_id"], "patient_id": a["patient_id"], "appointment_id": appt_id, "kind": "no_show",
                "title": "Missed appointment — call to rebook", "due_at": fmt_dt(now() + timedelta(hours=2)),
                "status": "open", "created_at": now_str(), "created_by": g.user.id})
            audit.record("followup_created", "follow_up", fid, "Auto: no-show follow-up", branch_id=a["branch_id"])
        if new == "completed" and request.form.get("followup_days") and g.user.can("followups.manage"):
            days = to_int(request.form.get("followup_days"), 0)
            if 0 < days <= 730:
                fid = conn.insert("follow_ups", {
                    "branch_id": a["branch_id"], "patient_id": a["patient_id"], "appointment_id": appt_id,
                    "kind": "post_treatment", "title": clean(request.form.get("followup_title"), 150) or f"Post-treatment check: {a['service']}",
                    "due_at": fmt_dt((now() + timedelta(days=days)).replace(hour=10, minute=0)), "status": "open",
                    "assignee_id": None, "created_at": now_str(), "created_by": g.user.id})
                audit.record("followup_created", "follow_up", fid, f"Follow-up in {days} days after treatment", branch_id=a["branch_id"])
    if new == "confirmed":
        dentist_mail.notify(conn, appt_id, "confirmed", a["dentist_id"])
    elif new == "cancelled" and a["status"] == "confirmed":
        dentist_mail.notify(conn, appt_id, "cancelled", a["dentist_id"])
    flash(f"Appointment marked {STATUSES[new].lower()}.", "success")
    return redirect(url_for("sched.appointment", appt_id=appt_id))


@bp.route("/appointments/<int:appt_id>/reschedule", methods=["POST"])
@require("appointments.manage")
def appointment_reschedule(appt_id):
    conn = get_db()
    a = _load_appt(appt_id)
    if a["status"] not in ("requested", "confirmed"):
        flash("Only requested or confirmed appointments can be rescheduled.", "error")
        return redirect(url_for("sched.appointment", appt_id=appt_id))
    v = {
        "branch_id": to_int(request.form.get("branch_id")) or a["branch_id"],
        "service_id": to_int(request.form.get("service_id")) or a["service_id"],
        "dentist_id": to_int(request.form.get("dentist_id")), "resource_id": to_int(request.form.get("resource_id")),
        "date": clean(request.form.get("date"), 10), "time": clean(request.form.get("time"), 5),
        "duration": clean(request.form.get("duration"), 4), "status": a["status"], "source": a["source"], "internal_notes": "",
    }
    patient = conn.one("SELECT * FROM patients WHERE id = ?", (a["patient_id"],))
    result = _validate_and_save(conn, patient, v, appt=a)
    if isinstance(result, int):
        if a["status"] == "confirmed":
            b = _load_appt(appt_id)
            if a["dentist_id"] != b["dentist_id"]:
                dentist_mail.notify(conn, appt_id, "reassigned", a["dentist_id"])
                dentist_mail.notify(conn, appt_id, "confirmed", b["dentist_id"])
            elif any(a[k] != b[k] for k in ("start_at", "end_at", "branch_id", "service_id")):
                dentist_mail.notify(conn, appt_id, "rescheduled", b["dentist_id"], previous=dentist_mail.describe_slot(a))
        flash("Appointment rescheduled. Reminders were updated for the new time.", "success")
    else:
        msgs = result.get("_form") or list(result.values())
        flash("Couldn't reschedule: " + " ".join(m if isinstance(m, str) else " ".join(m) for m in msgs), "error")
    return redirect(url_for("sched.appointment", appt_id=appt_id))


@bp.route("/appointments/<int:appt_id>/notes", methods=["POST"])
@require("appointments.manage")
def appointment_notes(appt_id):
    conn = get_db()
    a = _load_appt(appt_id)
    notes = clean(request.form.get("internal_notes"), 2000)
    conn.update("appointments", appt_id, {"internal_notes": notes, "updated_at": now_str()})
    audit.record("appointment_notes", "appointment", appt_id, "Updated internal notes", branch_id=a["branch_id"])
    flash("Notes saved.", "success")
    return redirect(url_for("sched.appointment", appt_id=appt_id))


# ---------------------------------------------------------------------------
# Online booking requests
# ---------------------------------------------------------------------------

@bp.route("/requests")
@require("bookings.view", "bookings.manage", any_of=True)
def requests():
    conn = get_db()
    status = request.args.get("status", "pending")
    rf, rp = branch_filter(g.user, "r.branch_id")
    rows = conn.all(
        "SELECT r.*, b.name AS branch, s.name AS service, u.name AS dentist FROM booking_requests r "
        "JOIN branches b ON b.id = r.branch_id JOIN services s ON s.id = r.service_id LEFT JOIN users u ON u.id = r.dentist_id "
        f"WHERE r.status = ? AND {rf} ORDER BY " + ("r.preferred_start" if status == "pending" else "r.created_at DESC") + " LIMIT 200",
        [status, *rp])
    return render_template("staff/sched/requests.html", rows=rows, status=status)


def _load_request(req_id):
    conn = get_db()
    r = conn.one("SELECT r.*, b.name AS branch, s.name AS service, u.name AS dentist FROM booking_requests r "
                 "JOIN branches b ON b.id = r.branch_id JOIN services s ON s.id = r.service_id "
                 "LEFT JOIN users u ON u.id = r.dentist_id WHERE r.id = ?", (req_id,))
    if not r:
        abort(404)
    if not g.user.in_branch(r["branch_id"]):
        abort(403)
    return r


@bp.route("/requests/<int:req_id>", methods=["GET", "POST"])
@require("bookings.view", "bookings.manage", any_of=True)
def request_detail(req_id):
    conn = get_db()
    r = _load_request(req_id)
    digits = "".join(c for c in r["phone"] if c.isdigit())[-10:]
    frag, params = patient_scope(g.user, "p")
    matches = conn.all(
        f"SELECT p.* FROM patients p WHERE {frag} AND p.active = 1 AND ("
        "replace(replace(replace(p.phone,' ',''),'-',''),'+63','0') LIKE ? OR (p.email != '' AND lower(p.email) = lower(?)) "
        "OR lower(p.first_name || ' ' || p.last_name) = lower(?)) LIMIT 10",
        [*params, f"%{digits}" if digits else "__none__", r["email"] or "__none__", r["full_name"]])
    errors = {}
    pref = parse_dt(r["preferred_start"])
    v = {"branch_id": r["branch_id"], "service_id": r["service_id"], "dentist_id": r["dentist_id"], "resource_id": None,
         "date": pref.date().isoformat(), "time": pref.strftime("%H:%M"), "duration": "", "status": "confirmed",
         "source": "website", "internal_notes": r["message"]}
    if request.method == "POST" and not g.user.can("bookings.manage"):
        abort(403)
    if request.method == "POST" and r["status"] == "pending":
        action = request.form.get("action")
        if action == "decline":
            reason = clean(request.form.get("decline_reason"), 500)
            if not reason:
                flash("Give a reason (kept internal).", "error")
            else:
                conn.execute("UPDATE booking_requests SET status='declined', decline_reason=?, handled_by=?, handled_at=? WHERE id=?",
                             (reason, g.user.id, now_str(), req_id))
                audit.record("booking_declined", "booking_request", req_id, f"Declined {r['ref_code']}", {"reason": reason}, r["branch_id"])
                flash("Request declined. Remember to let the patient know and offer another time.", "success")
                return redirect(url_for("sched.requests"))
        elif action == "confirm":
            v.update({
                "branch_id": to_int(request.form.get("branch_id")) or r["branch_id"],
                "service_id": to_int(request.form.get("service_id")) or r["service_id"],
                "dentist_id": to_int(request.form.get("dentist_id")), "resource_id": to_int(request.form.get("resource_id")),
                "date": clean(request.form.get("date"), 10), "time": clean(request.form.get("time"), 5),
                "duration": clean(request.form.get("duration"), 4), "internal_notes": clean(request.form.get("internal_notes"), 2000),
            })
            pid = to_int(request.form.get("patient_id"))
            try:
              with conn.transaction(immediate=True):
                  if pid:
                      if not can_see_patient(conn, g.user, pid):
                          abort(403)
                      patient = conn.one("SELECT * FROM patients WHERE id = ?", (pid,))
                  else:
                      if not g.user.can("patients.manage"):
                          abort(403)
                      from .patients import next_chart_no
                      first, _, last = r["full_name"].strip().partition(" ")
                      pid = conn.insert("patients", {
                          "chart_no": next_chart_no(conn), "first_name": first, "last_name": last or "-", "phone": r["phone"],
                          "email": r["email"], "preferred_branch_id": r["branch_id"], "consent_privacy": r["consent_privacy"],
                          "consent_privacy_at": r["created_at"], "contact_sms": r["consent_contact"],
                          "contact_email": 1 if (r["consent_contact"] and r["email"]) else 0, "source": "website",
                          "created_at": now_str(), "created_by": g.user.id})
                      audit.record("patient_created", "patient", pid, "Registered from online request", branch_id=r["branch_id"])
                      patient = conn.one("SELECT * FROM patients WHERE id = ?", (pid,))
                  result = _validate_and_save(conn, patient, v)
                  if isinstance(result, int):
                      conn.execute("UPDATE booking_requests SET status='confirmed', appointment_id=?, patient_id=?, handled_by=?, "
                                   "handled_at=? WHERE id=?", (result, pid, g.user.id, now_str(), req_id))
                      conn.execute("UPDATE appointments SET booking_request_id = ? WHERE id = ?", (req_id, result))
                      audit.record("booking_confirmed", "booking_request", req_id, f"Confirmed {r['ref_code']}", branch_id=r["branch_id"])
                  else:
                      errors = result
                      raise _Rollback()
            except _Rollback:
                pass
            else:
                dentist_mail.notify(conn, result, "confirmed", v["dentist_id"])
                flash("Request confirmed and appointment booked. Let the patient know using the confirmation template.", "success")
                return redirect(url_for("sched.appointment", appt_id=result))
    return render_template("staff/sched/request_detail.html", r=r, matches=matches, v=v, errors=errors,
                           services=services(), dentists=dentists([r["branch_id"]]),
                           resources=_resources(conn, [r["branch_id"]]), branches=branches_for_user(g.user))


class _Rollback(Exception):
    pass


@bp.route("/schedules")
@require("calendar.events", "settings.manage", any_of=True)
def schedules():
    """Read-only view of dentists' weekly schedules (MyMedsPH: View Events/Schedules)."""
    conn = get_db()
    ids = g.user.scope_branch_ids or [0]
    marks = ",".join("?" for _ in ids)
    rows = conn.all(
        "SELECT ds.*, u.name AS dentist, b.name AS branch FROM dentist_schedules ds JOIN users u ON u.id = ds.dentist_id "
        f"JOIN branches b ON b.id = ds.branch_id WHERE u.active = 1 AND ds.branch_id IN ({marks}) ORDER BY ds.weekday, ds.start_time, u.name", ids)
    by_day = {wd: [r for r in rows if r["weekday"] == wd] for wd in range(7)}
    return render_template("staff/sched/schedules.html", by_day=by_day)

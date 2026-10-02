"""Time clock: staff time in / time out from their phone with a selfie and a location check.

- The selfie is taken with the phone's camera (a normal photo upload), and the phone's location is compared with
  the branch's saved location. Outside the allowed radius, or with location off, the time is still recorded but the
  day is flagged for the manager to review in Attendance.
- Each punch updates that day's time record (time_records), which Attendance (DTR) and payroll already use.
- Selfies are private: only users who manage attendance for that branch can see them, and they are deleted
  automatically after the retention period (System: timeclock.photo_days, default 60 days).
"""
from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, g, make_response, redirect, render_template, request, send_file, url_for

from .. import audit, settings
from ..notices import notify
from ..auth import require
from ..db import get_db
from ..attendance_rules import refresh_record
from ..payroll import evaluate_record
from ..permissions import branch_filter
from ..uploads import document_path, save_private_image
from ..util import clean, now, now_str, parse_date, to_int, today
from .common import branches_for_user

bp = Blueprint("timeclock", __name__, url_prefix="/staff/clock")
DEFAULT_PHOTO_DAYS = 60
POLICY = "camera=(self), microphone=(), geolocation=(self)"


def distance_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _float(v, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo <= f <= hi and f == f else None


def photo_days(conn):
    return int(settings.get("timeclock.photo_days", conn) or DEFAULT_PHOTO_DAYS)


def purge_old_photos(conn):
    """Delete selfies older than the retention period (the punch record itself is kept)."""
    cutoff = (now() - timedelta(days=photo_days(conn))).strftime("%Y-%m-%d %H:%M:%S")
    for p in conn.all("SELECT id, photo FROM time_punches WHERE photo IS NOT NULL AND at < ?", (cutoff,)):
        try:
            document_path(p["photo"]).unlink(missing_ok=True)
        except ValueError:
            pass
        conn.execute("UPDATE time_punches SET photo = NULL WHERE id = ?", (p["id"],))


def _employee(conn):
    return conn.one("SELECT * FROM employees WHERE user_id = ? AND active = 1", (g.user.id,))


FIELD_PREFIX = "field work"


def field_approvers(conn, branch_id: int) -> list[int]:
    """Users who can approve field work for a branch: super admins, and users whose access role has attendance.manage
    and who are assigned to that branch."""
    roles = [r["role"] for r in conn.all("SELECT role FROM role_permissions WHERE permission = 'attendance.manage'")]
    marks = ",".join("?" * len(roles)) or "''"
    rows = conn.all("SELECT u.id FROM users u WHERE u.active = 1 AND (u.role = 'super_admin' OR "
                    f"(COALESCE(NULLIF(u.access_role, ''), u.role) IN ({marks}) AND EXISTS "
                    "(SELECT 1 FROM user_branches ub WHERE ub.user_id = u.id AND ub.branch_id = ?)))", (*roles, branch_id))
    return [r["id"] for r in rows]


def _user_labs(conn, user):
    """Laboratories this user works at (Users → Authorized laboratories) that have an attendance branch set."""
    return conn.all("SELECT l.*, b.name AS branch_name FROM laboratories l JOIN user_labs ul ON ul.lab_id = l.id "
                    "JOIN branches b ON b.id = l.branch_id WHERE ul.user_id = ? AND l.active = 1 AND b.active = 1 ORDER BY l.name",
                    (user.id,))


def _with_policy(html):
    resp = make_response(html)
    resp.headers["Permissions-Policy"] = POLICY
    return resp


@bp.route("", methods=["GET", "POST"])
@require("attendance.clock")
def clock():
    conn = get_db()
    emp = _employee(conn)
    branches = branches_for_user(g.user)
    labs = _user_labs(conn, g.user)
    if not emp:
        return render_template("staff/timeclock/clock.html", emp=None, branches=[], labs=[], rec=None, punches=[], next_kind=None,
                               branch_id=None, place=None)
    day = today().isoformat()
    rec = conn.one("SELECT * FROM time_records WHERE employee_id = ? AND work_date = ?", (emp["id"], day))
    next_kind = "in" if not rec or not rec["time_in"] else ("out" if not rec["time_out"] else None)
    branch_id = (rec["branch_id"] if rec else None) or g.user.active_branch_id or emp["primary_branch_id"] or (branches[0]["id"] if branches else None)
    # Where today's record was started (a lab or a branch), or the default choice.
    first = conn.one("SELECT lab_id FROM time_punches WHERE time_record_id = ? ORDER BY id LIMIT 1", (rec["id"],)) if rec else None
    if first and first["lab_id"]:
        place = f"l:{first['lab_id']}"
    elif rec or branches:
        place = f"b:{branch_id}"
    else:
        place = f"l:{labs[0]['id']}" if labs else None
    if request.method == "POST":
        kind = request.form.get("kind")
        raw = request.form.get("place") or f"b:{request.form.get('branch_id') or ''}"
        lab = None
        if raw.startswith("l:"):
            lab = next((x for x in labs if x["id"] == to_int(raw[2:])), None)
            if not lab:
                flash("Choose the place you're at.", "error")
                return redirect(url_for("timeclock.clock"))
            branch = conn.one("SELECT * FROM branches WHERE id = ? AND active = 1", (lab["branch_id"],))
        else:
            branch_id = to_int(raw[2:])
            branch = conn.one("SELECT * FROM branches WHERE id = ? AND active = 1", (branch_id,)) if branch_id else None
            if branch and not g.user.in_branch(branch["id"]):
                branch = None
        # The place that is location-checked: the lab, or the branch.
        site = lab or branch
        if kind != next_kind:
            flash("You've already timed in and out today. Ask your manager if your time needs correcting." if next_kind is None
                  else "Please try again.", "error")
            return redirect(url_for("timeclock.clock"))
        if not branch:
            flash("Choose the branch or laboratory you're at.", "error")
            return redirect(url_for("timeclock.clock"))
        if rec and kind == "out" and (rec["branch_id"] != branch["id"] or place != (f"l:{lab['id']}" if lab else f"b:{branch['id']}")):
            flash("Time out at the same place where you timed in, or ask your manager to correct it.", "error")
            return redirect(url_for("timeclock.clock"))
        field = request.form.get("field") == "1"
        field_reason = clean(request.form.get("field_reason"), 200)
        if field and len(field_reason) < 3:
            flash("You ticked “I'm on the field”: write where you are and why (for example, “Supplier pickup in Manila”).", "error")
            return redirect(url_for("timeclock.clock"))
        f = request.files.get("photo")
        if not f or not f.filename:
            flash("Take a selfie first." if field else "Take a selfie in front of the clinic first.", "error")
            return redirect(url_for("timeclock.clock"))
        photo, err = save_private_image(f, "timeclock")
        if err:
            flash(err, "error")
            return redirect(url_for("timeclock.clock"))
        lat = _float(request.form.get("lat"), -90, 90)
        lng = _float(request.form.get("lng"), -180, 180)
        acc = _float(request.form.get("acc"), 0, 100000)
        dist = ok = None
        if not field and lat is not None and lng is not None and site["latitude"] is not None and site["longitude"] is not None:
            dist = round(distance_m(lat, lng, site["latitude"], site["longitude"]))
            # allow for the phone's own GPS uncertainty, up to 100 m extra
            ok = 1 if dist <= (site["clock_radius_m"] or 150) + min(acc or 0, 100) else 0
        t = now()
        hm = t.strftime("%H:%M")
        note = ""
        if field:
            note = f"{FIELD_PREFIX} (time-{kind}): {field_reason}"
        elif site["latitude"] is not None:
            if ok == 0:
                note = f"time-{kind} {dist:,} m from the {'lab' if lab else 'branch'}"
            elif ok is None:
                note = f"time-{kind} location not shared"
        with conn.transaction():
            if not rec:
                values = {"employee_id": emp["id"], "branch_id": branch["id"], "work_date": day, "time_in": hm, "time_out": None, "status": "ok"}
                status, auto = evaluate_record(conn, values)
                notes = "; ".join(x for x in (auto, note) if x)
                rid = conn.insert("time_records", {**values, "status": "exception" if notes else status, "exception_note": notes,
                                                   "source": "clock", "created_at": now_str()})
            else:
                rid = rec["id"]
                values = {**dict(rec), "time_in": rec["time_in"] or hm, "time_out": hm if kind == "out" else rec["time_out"]}
                status, auto = evaluate_record(conn, values)
                earlier = [x for x in (rec["exception_note"] or "").split("; ") if x.startswith(("time-in ", f"{FIELD_PREFIX} (time-in)"))]
                notes = "; ".join(x for x in (auto, *earlier, note) if x)
                if rec["status"] in ("corrected", "excused"):
                    status, notes = rec["status"], rec["exception_note"]
                conn.execute("UPDATE time_records SET time_in = ?, time_out = ?, status = ?, exception_note = ? WHERE id = ?",
                             (values["time_in"], values["time_out"], "exception" if notes and status == "ok" else status, notes, rid))
            if field:
                # The whole day waits for approval (again, if an earlier field punch was already approved).
                prev = conn.one("SELECT field_reason FROM time_records WHERE id = ?", (rid,))["field_reason"]
                reasons = "; ".join(x for x in (prev, f"time-{kind}: {field_reason}") if x)
                conn.execute("UPDATE time_records SET field_status = 'pending', field_reason = ?, field_reviewed_by = NULL, "
                             "field_reviewed_at = NULL, field_review_note = '', status = CASE WHEN status IN ('corrected','excused') "
                             "THEN status ELSE 'exception' END WHERE id = ?", (reasons[:500], rid))
            refresh_record(conn, rid)
            conn.insert("time_punches", {"employee_id": emp["id"], "branch_id": branch["id"], "lab_id": lab["id"] if lab else None,
                                         "field": 1 if field else 0, "field_reason": field_reason if field else "",
                                         "time_record_id": rid, "kind": kind, "at": now_str(),
                                         "latitude": lat, "longitude": lng, "accuracy_m": acc, "distance_m": dist, "location_ok": ok,
                                         "photo": photo, "created_at": now_str()})
            audit.record("time_clock", "time_record", rid, f"Time {kind} {hm} " + ("on the field" if field else f"at {site['name']}"),
                         branch_id=branch["id"])
            if field:
                notify(conn, field_approvers(conn, branch["id"]), "field_work", f"Field work to approve: {emp['full_name']}",
                       f"Time {kind} {t.strftime('%I:%M %p').lstrip('0')} on the field. Reason: {field_reason}",
                       url_for("timeclock.log", flag="field"), exclude=g.user.id)
            purge_old_photos(conn)
        msg = f"Timed {kind} at {t.strftime('%I:%M %p').lstrip('0')}."
        if field:
            flash(msg + " Marked as field work: it counts once your supervisor, HR or admin approves it.", "success")
            return redirect(url_for("timeclock.clock"))
        if ok == 0:
            msg += f" You seem to be about {dist:,} m from {site['name']}, so your manager will review it."
        elif ok is None and site["latitude"] is not None:
            msg += " Your location wasn't shared, so your manager will review it."
        flash(msg, "success" if ok != 0 else "error")
        return redirect(url_for("timeclock.clock"))
    punches = conn.all("SELECT p.*, COALESCE(l.name, b.name) AS branch FROM time_punches p JOIN branches b ON b.id = p.branch_id "
                       "LEFT JOIN laboratories l ON l.id = p.lab_id WHERE p.employee_id = ? AND p.at >= ? ORDER BY p.id", (emp["id"], day))
    return _with_policy(render_template("staff/timeclock/clock.html", emp=emp, branches=branches, labs=labs, rec=rec, punches=punches,
                                        next_kind=next_kind, branch_id=branch_id, place=place, now=now()))


@bp.route("/log")
@require("attendance.manage")
def log():
    conn = get_db()
    purge_old_photos(conn)
    start = parse_date(request.args.get("from")) or today()
    end = parse_date(request.args.get("to")) or start
    if end < start:
        start, end = end, start
    bf, bp_ = branch_filter(g.user, "p.branch_id")
    flag = request.args.get("flag", "")
    where, args = [bf, "p.at >= ?", "p.at < ?"], [*bp_, start.isoformat(), (end + timedelta(days=1)).isoformat()]
    if flag == "field":
        # Everything still waiting, whatever the date.
        where, args = [bf, "p.field = 1 AND t.field_status = 'pending'"], [*bp_]
    elif flag == "field_all":
        where.append("p.field = 1")
    elif flag == "review":
        where.append("(p.location_ok = 0 OR (p.location_ok IS NULL AND (CASE WHEN p.lab_id IS NOT NULL THEN l.latitude ELSE b.latitude END) IS NOT NULL))")
    rows = conn.all("SELECT p.*, e.full_name, e.user_id AS emp_user_id, b.name AS branch, l.name AS lab, "
                    "CASE WHEN p.lab_id IS NOT NULL THEN l.latitude ELSE b.latitude END AS b_lat, "
                    "t.field_status, t.field_review_note, t.work_date, ru.name AS reviewer "
                    "FROM time_punches p JOIN employees e ON e.id = p.employee_id JOIN branches b ON b.id = p.branch_id "
                    "LEFT JOIN laboratories l ON l.id = p.lab_id LEFT JOIN time_records t ON t.id = p.time_record_id "
                    "LEFT JOIN users ru ON ru.id = t.field_reviewed_by "
                    f"WHERE {' AND '.join(where)} ORDER BY p.at DESC LIMIT 500", args)
    pbf, pbp = branch_filter(g.user, "t.branch_id")
    pending = conn.scalar(f"SELECT COUNT(*) FROM time_records t WHERE t.field_status = 'pending' AND {pbf}", pbp) or 0
    return render_template("staff/timeclock/log.html", rows=rows, start=start, end=end, flag=flag, days=photo_days(conn), pending=pending)


@bp.route("/field/<int:rec_id>", methods=["POST"])
@require("attendance.manage")
def field_review(rec_id):
    """Approve or decline a day logged on the field. Approved: the day counts for attendance and payroll.
    Declined: the day doesn't count."""
    conn = get_db()
    rec = conn.one("SELECT t.*, e.full_name, e.user_id AS emp_user_id FROM time_records t JOIN employees e ON e.id = t.employee_id "
                   "WHERE t.id = ?", (rec_id,))
    if not rec or not g.user.in_branch(rec["branch_id"]):
        abort(404)
    back = request.form.get("next") or url_for("timeclock.log", flag="field")
    if not back.startswith("/staff/"):
        back = url_for("timeclock.log", flag="field")
    if rec["emp_user_id"] == g.user.id and not g.user.is_super_admin:
        flash("You can't approve your own field work. Another supervisor, HR or admin has to review it.", "error")
        return redirect(back)
    action = request.form.get("action")
    if action not in ("approve", "decline") or not rec["field_status"]:
        abort(400)
    note = clean(request.form.get("note"), 200)
    parts = [x for x in (rec["exception_note"] or "").split("; ") if x]
    others = [x for x in parts if not x.startswith(FIELD_PREFIX)]
    if action == "approve":
        notes = "; ".join(others)
        status = rec["status"] if rec["status"] in ("corrected", "excused") else ("exception" if others else "ok")
        new_state, word = "approved", "approved"
    else:
        notes = "; ".join([*others, "field work declined" + (f": {note}" if note else "")])
        status = rec["status"] if rec["status"] in ("corrected", "excused") else "exception"
        new_state, word = "declined", "declined"
    with conn.transaction():
        conn.execute("UPDATE time_records SET field_status = ?, field_reviewed_by = ?, field_reviewed_at = ?, field_review_note = ?, "
                     "status = ?, exception_note = ? WHERE id = ?", (new_state, g.user.id, now_str(), note, status, notes, rec_id))
        refresh_record(conn, rec_id)
        audit.record("field_work_review", "time_record", rec_id, f"Field work {word} for {rec['full_name']} on {rec['work_date']}",
                     {"note": note}, branch_id=rec["branch_id"])
        if rec["emp_user_id"]:
            notify(conn, [rec["emp_user_id"]], "field_work", f"Field work {word}: {rec['work_date']}",
                   ("It now counts for attendance and payroll." if action == "approve" else "This day doesn't count for attendance and payroll.")
                   + (f" Note: {note}" if note else ""), url_for("timeclock.clock"))
    flash(f"Field work {word} for {rec['full_name']} ({rec['work_date']}).", "success")
    return redirect(back)


@bp.route("/photo/<int:punch_id>")
@require("attendance.manage")
def photo(punch_id):
    conn = get_db()
    p = conn.one("SELECT * FROM time_punches WHERE id = ?", (punch_id,))
    if not p or not p["photo"] or not g.user.in_branch(p["branch_id"]):
        abort(404)
    try:
        path = document_path(p["photo"])
    except ValueError:
        abort(404)
    if not Path(path).exists():
        abort(404)
    resp = send_file(path, max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/settings", methods=["GET", "POST"])
@require("attendance.manage")
def setup():
    conn = get_db()
    branches = branches_for_user(g.user)
    # Laboratories where the clinic's own employees work (they have users assigned). A lab already linked to a branch
    # is managed by that branch's managers; an unlinked one only by a super admin.
    labs = [l for l in conn.all("SELECT l.*, (SELECT COUNT(*) FROM user_labs ul JOIN users u ON u.id = ul.user_id "
                                "WHERE ul.lab_id = l.id AND u.active = 1) AS staff FROM laboratories l WHERE l.active = 1 ORDER BY l.name")
            if l["staff"] and (g.user.is_super_admin or (l["branch_id"] and g.user.in_branch(l["branch_id"])))]
    if request.method == "POST":
        if request.form.get("action") == "retention":
            if not g.user.is_super_admin:
                abort(403)
            days = to_int(request.form.get("days"))
            if not days or not 7 <= days <= 365:
                flash("Enter a number of days from 7 to 365.", "error")
            else:
                settings.put("timeclock.photo_days", days, g.user.id, conn)
                audit.record("timeclock_retention", "setting", None, f"Time clock selfies kept for {days} days")
                flash("Saved.", "success")
            return redirect(url_for("timeclock.setup"))
        lab = None
        if request.form.get("lab_id"):
            lab = next((x for x in labs if x["id"] == to_int(request.form.get("lab_id"))), None)
            if not lab:
                abort(404)
            lab_branch = to_int(request.form.get("lab_branch_id"))
            if not any(x["id"] == lab_branch for x in branches):
                flash(f"Choose which branch handles attendance for {lab['name']}.", "error")
                return redirect(url_for("timeclock.setup") + f"#lab-{lab['id']}")
            b = None
        else:
            b = next((x for x in branches if x["id"] == to_int(request.form.get("branch_id"))), None)
            if not b:
                abort(404)
        raw_lat, raw_lng = clean(request.form.get("lat"), 20), clean(request.form.get("lng"), 20)
        lat, lng = _float(raw_lat, -90, 90), _float(raw_lng, -180, 180)
        radius = to_int(request.form.get("radius")) or 150
        if (raw_lat or raw_lng) and (lat is None or lng is None):
            flash("Enter the latitude and longitude as numbers (e.g. 14.8433 and 120.8114), or tap “Use my current location”.", "error")
        elif not 30 <= radius <= 2000:
            flash("Enter an allowed distance from 30 to 2,000 meters.", "error")
        elif lab:
            conn.execute("UPDATE laboratories SET latitude = ?, longitude = ?, clock_radius_m = ?, branch_id = ? WHERE id = ?",
                         (lat, lng, radius, lab_branch, lab["id"]))
            audit.record("timeclock_location", "laboratory", lab["id"], f"Time clock location for {lab['name']} updated", branch_id=lab_branch)
            flash(f"Saved the time clock location for {lab['name']}.", "success")
        else:
            conn.execute("UPDATE branches SET latitude = ?, longitude = ?, clock_radius_m = ? WHERE id = ?", (lat, lng, radius, b["id"]))
            audit.record("timeclock_location", "branch", b["id"], f"Time clock location for {b['name']} updated", branch_id=b["id"])
            flash(f"Saved the time clock location for {b['name']}.", "success")
        return redirect(url_for("timeclock.setup"))
    return _with_policy(render_template("staff/timeclock/settings.html", branches=branches, labs=labs, days=photo_days(conn)))

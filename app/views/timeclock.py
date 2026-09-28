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
    if not emp:
        return render_template("staff/timeclock/clock.html", emp=None, branches=[], rec=None, punches=[], next_kind=None, branch_id=None)
    day = today().isoformat()
    rec = conn.one("SELECT * FROM time_records WHERE employee_id = ? AND work_date = ?", (emp["id"], day))
    next_kind = "in" if not rec or not rec["time_in"] else ("out" if not rec["time_out"] else None)
    branch_id = (rec["branch_id"] if rec else None) or g.user.active_branch_id or emp["primary_branch_id"] or (branches[0]["id"] if branches else None)
    if request.method == "POST":
        kind = request.form.get("kind")
        branch_id = to_int(request.form.get("branch_id"))
        branch = conn.one("SELECT * FROM branches WHERE id = ? AND active = 1", (branch_id,)) if branch_id else None
        if kind != next_kind:
            flash("You've already timed in and out today. Ask your manager if your time needs correcting." if next_kind is None
                  else "Please try again.", "error")
            return redirect(url_for("timeclock.clock"))
        if not branch or not g.user.in_branch(branch["id"]):
            flash("Choose the branch you're at.", "error")
            return redirect(url_for("timeclock.clock"))
        if rec and kind == "out" and rec["branch_id"] != branch["id"]:
            flash("Time out at the same branch where you timed in, or ask your manager to correct it.", "error")
            return redirect(url_for("timeclock.clock"))
        f = request.files.get("photo")
        if not f or not f.filename:
            flash("Take a selfie in front of the clinic first.", "error")
            return redirect(url_for("timeclock.clock"))
        photo, err = save_private_image(f, "timeclock")
        if err:
            flash(err, "error")
            return redirect(url_for("timeclock.clock"))
        lat = _float(request.form.get("lat"), -90, 90)
        lng = _float(request.form.get("lng"), -180, 180)
        acc = _float(request.form.get("acc"), 0, 100000)
        dist = ok = None
        if lat is not None and lng is not None and branch["latitude"] is not None and branch["longitude"] is not None:
            dist = round(distance_m(lat, lng, branch["latitude"], branch["longitude"]))
            # allow for the phone's own GPS uncertainty, up to 100 m extra
            ok = 1 if dist <= (branch["clock_radius_m"] or 150) + min(acc or 0, 100) else 0
        t = now()
        hm = t.strftime("%H:%M")
        note = ""
        if branch["latitude"] is not None:
            if ok == 0:
                note = f"time-{kind} {dist:,} m from the branch"
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
                earlier = [x for x in (rec["exception_note"] or "").split("; ") if x.startswith("time-in ")]
                notes = "; ".join(x for x in (auto, *earlier, note) if x)
                if rec["status"] in ("corrected", "excused"):
                    status, notes = rec["status"], rec["exception_note"]
                conn.execute("UPDATE time_records SET time_in = ?, time_out = ?, status = ?, exception_note = ? WHERE id = ?",
                             (values["time_in"], values["time_out"], "exception" if notes and status == "ok" else status, notes, rid))
            refresh_record(conn, rid)
            conn.insert("time_punches", {"employee_id": emp["id"], "branch_id": branch["id"], "time_record_id": rid, "kind": kind, "at": now_str(),
                                         "latitude": lat, "longitude": lng, "accuracy_m": acc, "distance_m": dist, "location_ok": ok,
                                         "photo": photo, "created_at": now_str()})
            audit.record("time_clock", "time_record", rid, f"Time {kind} {hm} at {branch['name']}", branch_id=branch["id"])
            purge_old_photos(conn)
        msg = f"Timed {kind} at {t.strftime('%I:%M %p').lstrip('0')}."
        if ok == 0:
            msg += f" You seem to be about {dist:,} m from {branch['name']}, so your manager will review it."
        elif ok is None and branch["latitude"] is not None:
            msg += " Your location wasn't shared, so your manager will review it."
        flash(msg, "success" if ok != 0 else "error")
        return redirect(url_for("timeclock.clock"))
    punches = conn.all("SELECT p.*, b.name AS branch FROM time_punches p JOIN branches b ON b.id = p.branch_id "
                       "WHERE p.employee_id = ? AND p.at >= ? ORDER BY p.id", (emp["id"], day))
    return _with_policy(render_template("staff/timeclock/clock.html", emp=emp, branches=branches, rec=rec, punches=punches, next_kind=next_kind,
                                        branch_id=branch_id, now=now()))


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
    if flag == "review":
        where.append("(p.location_ok = 0 OR (p.location_ok IS NULL AND b.latitude IS NOT NULL))")
    rows = conn.all("SELECT p.*, e.full_name, b.name AS branch, b.latitude AS b_lat FROM time_punches p JOIN employees e ON e.id = p.employee_id "
                    f"JOIN branches b ON b.id = p.branch_id WHERE {' AND '.join(where)} ORDER BY p.at DESC LIMIT 500", args)
    return render_template("staff/timeclock/log.html", rows=rows, start=start, end=end, flag=flag, days=photo_days(conn))


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
        else:
            conn.execute("UPDATE branches SET latitude = ?, longitude = ?, clock_radius_m = ? WHERE id = ?", (lat, lng, radius, b["id"]))
            audit.record("timeclock_location", "branch", b["id"], f"Time clock location for {b['name']} updated", branch_id=b["id"])
            flash(f"Saved the time clock location for {b['name']}.", "success")
        return redirect(url_for("timeclock.setup"))
    return _with_policy(render_template("staff/timeclock/settings.html", branches=branches, days=photo_days(conn)))

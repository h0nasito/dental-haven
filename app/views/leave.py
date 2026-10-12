"""Leave forms: employees file a leave; HR or anyone allowed to approve leave (leave.approve) approves or disapproves it.

- An employee files a leave for themselves (type, dates, half day, reason, optional attachment such as a medical certificate).
- Approvers see pending forms of employees in their branches (super admins: all) and approve or disapprove with a note.
  Nobody approves their own leave.
- Approved leave days are marked in Attendance (DTR) as excused, so they don't show as missing or late.
  Pay is not changed here: whether a leave is paid is decided in payroll.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..notices import notify
from ..permissions import load_user_permissions
from ..uploads import IMAGE_TYPES, document_path, save_document, save_private_photo, sniff
from ..util import clean, now_str, parse_date, to_int, today
from .common import branches_for_user

bp = Blueprint("leave", __name__, url_prefix="/staff/leave")

SIL = "Service incentive leave (SIL)"   # the leave with pay: 5 days a year for regular employees
LEAVE_TYPES = [SIL, "Vacation leave", "Sick leave", "Emergency leave", "Birthday leave", "Maternity leave", "Paternity leave",
               "Solo parent leave", "Bereavement leave", "Leave without pay", "Other"]
STATUS = {"pending": ("Pending", "badge-amber"), "approved": ("Approved", "badge-green"), "disapproved": ("Disapproved", "badge-red"),
          "cancelled": ("Cancelled", "")}


DEFAULT_PAID_DAYS = 5   # service incentive leave of a regular employee, per calendar year


def entitlement(emp) -> float:
    """Leave-with-pay days a year: the employee's own number if HR set one, else 5 for regular employees, 0 for others."""
    if emp["paid_leave_days"] is not None:
        return float(emp["paid_leave_days"])
    return float(DEFAULT_PAID_DAYS) if emp["employment_type"] == "regular" else 0.0


def balance(conn, emp, year: int | None = None, exclude_id: int | None = None) -> dict:
    """Leave with pay for the calendar year: entitled, used (approved), pending, and available (entitled − used − pending)."""
    y = str(year or today().year)
    rows = conn.all("SELECT status, SUM(days) AS d FROM leave_requests WHERE employee_id = ? AND with_pay = 1 AND substr(start_date, 1, 4) = ? "
                    "AND status IN ('approved', 'pending') AND id != ? GROUP BY status", (emp["id"], y, exclude_id or 0))
    got = {r["status"]: r["d"] or 0 for r in rows}
    ent = entitlement(emp)
    used, pend = float(got.get("approved", 0)), float(got.get("pending", 0))
    return {"year": int(y), "entitled": ent, "used": used, "pending": pend, "available": max(0.0, ent - used - pend)}


def is_dentist(conn, emp) -> bool:
    u = conn.one("SELECT role FROM users WHERE id = ?", (emp["user_id"],)) if emp and emp["user_id"] else None
    return bool(u and u["role"] == "dentist")


def reliever_choices(conn, me) -> list[dict]:
    """Who can cover: a dentist picks from all dentists (any branch); staff pick from all other employees except dentists."""
    rows = conn.all("SELECT e.id, e.full_name, e.position, b.name AS branch, u.role FROM employees e LEFT JOIN users u ON u.id = e.user_id "
                    "LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE e.active = 1 AND e.id != ? ORDER BY e.full_name", (me["id"],))
    want_dentists = is_dentist(conn, me)
    return [dict(r) for r in rows if r["role"] != "super_admin" and (r["role"] == "dentist") == want_dentists]


def _me(conn):
    return conn.one("SELECT * FROM employees WHERE user_id = ? AND active = 1", (g.user.id,))


def count_days(start: date, end: date, half: str) -> float:
    """Calendar days from start to end, Sundays not counted (the clinics' day off); a half day counts 0.5."""
    if half:
        return 0.5
    n, d = 0, start
    while d <= end:
        if d.weekday() != 6:
            n += 1
        d += timedelta(days=1)
    return float(n)


def approvers(conn, branch_id) -> list[int]:
    """Active users allowed to approve leave for this branch (and every super admin)."""
    out = []
    for u in conn.all("SELECT id, role, access_role FROM users WHERE active = 1"):
        if u["role"] == "super_admin":
            out.append(u["id"])
            continue
        if branch_id and not conn.one("SELECT 1 AS x FROM user_branches WHERE user_id = ? AND branch_id = ?", (u["id"], branch_id)):
            continue
        if "leave.approve" in load_user_permissions(conn, u["id"], u["access_role"] or u["role"]):
            out.append(u["id"])
    return out


def _can_review(lr) -> bool:
    if not g.user.can("leave.approve"):
        return False
    me = get_db().one("SELECT id FROM employees WHERE user_id = ?", (g.user.id,))
    if me and me["id"] == lr["employee_id"]:
        return False                       # nobody approves their own leave
    return g.user.is_super_admin or (lr["branch_id"] and g.user.in_branch(lr["branch_id"]))


def _mark_attendance(conn, lr, on: bool):
    """Approved leave: the days become 'excused' in the DTR (records are created for days with no time in)."""
    start, end = date.fromisoformat(lr["start_date"]), date.fromisoformat(lr["end_date"])
    note = f"On leave: {lr['leave_type']}" + (f" ({lr['half_day'].upper()} half day)" if lr["half_day"] else "")
    d = start
    while d <= end:
        if d.weekday() != 6:
            rec = conn.one("SELECT * FROM time_records WHERE employee_id = ? AND work_date = ?", (lr["employee_id"], d.isoformat()))
            if on:
                if not rec and lr["branch_id"]:
                    conn.insert("time_records", {"employee_id": lr["employee_id"], "branch_id": lr["branch_id"], "work_date": d.isoformat(),
                                                 "status": "excused", "exception_note": note, "source": "leave", "created_at": now_str()})
                elif not lr["half_day"] and rec["status"] in ("ok", "exception"):
                    conn.execute("UPDATE time_records SET status = 'excused', exception_note = ? WHERE id = ?", (note, rec["id"]))
            elif rec and (rec["exception_note"] or "").startswith("On leave:"):
                if rec["source"] == "leave" and not rec["time_in"]:
                    conn.execute("DELETE FROM time_records WHERE id = ?", (rec["id"],))
                else:
                    conn.execute("UPDATE time_records SET status = 'exception', exception_note = 'leave cancelled: check this day' WHERE id = ?",
                                 (rec["id"],))
        d += timedelta(days=1)


@bp.route("/", methods=["GET", "POST"])
@require("leave.request", "leave.approve", any_of=True)
def index():
    conn = get_db()
    me = _me(conn)
    if request.method == "POST":
        if not g.user.can("leave.request"):
            abort(403)
        if not me:
            flash("Your account isn't linked to an employee record yet. Ask HR.", "error")
            return redirect(url_for("leave.index"))
        f = request.form
        ltype = f.get("leave_type")
        start, end = parse_date(f.get("start_date")), parse_date(f.get("end_date")) or parse_date(f.get("start_date"))
        half = f.get("half_day") if f.get("half_day") in ("am", "pm") else ""
        reason = clean(f.get("reason"), 500)
        rel_raw = f.get("reliever") or ""
        rel_ok_ids = {r["id"] for r in reliever_choices(conn, me)}
        reliever_id = int(rel_raw) if rel_raw.isdigit() and int(rel_raw) in rel_ok_ids else None
        with_pay = 1 if ltype == SIL else 0      # only SIL is with pay; it uses up the SIL days
        if ltype not in LEAVE_TYPES or not start or not end or end < start:
            flash("Choose the type of leave and the dates.", "error")
        elif half and end != start:
            flash("A half-day leave is for one day only.", "error")
        elif (end - start).days > 120:
            flash("A leave can be up to 120 days per form.", "error")
        elif start < today() - timedelta(days=30):
            flash("For a leave more than 30 days ago, ask HR to record it.", "error")
        elif len(reason) < 3:
            flash("Write the reason for the leave.", "error")
        elif rel_raw != "na" and not reliever_id:
            flash("Choose your reliever, or N/A if no one is available.", "error")
        elif with_pay and start.year != end.year:
            flash("For leave with pay, file one form per calendar year.", "error")
        elif with_pay and count_days(start, end, half) > balance(conn, me, start.year)["available"]:
            b = balance(conn, me, start.year)
            flash(f"Not enough SIL: {b['available']:g} day(s) left for {b['year']} "
                  f"({b['entitled']:g} a year, {b['used']:g} used, {b['pending']:g} waiting for approval). Choose another type of leave (without pay), or fewer days.", "error")
        elif conn.one("SELECT id FROM leave_requests WHERE employee_id = ? AND status IN ('pending','approved') AND start_date <= ? AND end_date >= ?",
                      (me["id"], end.isoformat(), start.isoformat())):
            flash("You already have a leave for some of these days.", "error")
        else:
            stored = ""
            att = request.files.get("attachment")
            if att and att.filename:
                head = att.stream.read(16)
                att.stream.seek(0)
                if sniff(head) in IMAGE_TYPES:
                    stored, err = save_private_photo(att, "leave")
                else:
                    stored, _m, _s, _o, err = save_document(att)
                if err:
                    flash(f"Attachment: {err}", "error")
                    return redirect(url_for("leave.index"))
            days = count_days(start, end, half)
            lid = conn.insert("leave_requests", {"employee_id": me["id"], "branch_id": me["primary_branch_id"], "leave_type": ltype,
                                                  "start_date": start.isoformat(), "end_date": end.isoformat(), "half_day": half, "days": days,
                                                  "reason": reason, "attachment": stored or "", "status": "pending", "with_pay": with_pay,
                                                  "reliever_id": reliever_id, "reliever_na": 0 if reliever_id else 1, "created_by": g.user.id,
                                                  "created_at": now_str()})
            audit.record("leave_filed", "leave", lid, f"{me['full_name']} filed {ltype} ({days:g} day(s){', with pay' if with_pay else ''}) {start} to {end}",
                         branch_id=me["primary_branch_id"])
            notify(conn, approvers(conn, me["primary_branch_id"]), "leave", f"Leave form to approve: {me['full_name']}",
                   f"{ltype}, {start.strftime('%b %d')}" + (f" – {end.strftime('%b %d')}" if end != start else "") + f" ({days:g} day(s))",
                   url_for("leave.index", show="pending"), exclude=g.user.id)
            flash("Leave form sent for approval.", "success")
        return redirect(url_for("leave.index"))
    show = request.args.get("show") or ("pending" if g.user.can("leave.approve") else "mine")
    mine = conn.all("SELECT l.*, u.name AS reviewer, rl.full_name AS reliever FROM leave_requests l LEFT JOIN users u ON u.id = l.reviewed_by "
                    "LEFT JOIN employees rl ON rl.id = l.reliever_id "
                    "WHERE l.employee_id = ? ORDER BY l.start_date DESC, l.id DESC LIMIT 100", (me["id"],)) if me else []
    rows, pending_n = [], 0
    if g.user.can("leave.approve"):
        ids = [b["id"] for b in branches_for_user(g.user, include_all=g.user.is_super_admin)]
        marks = ",".join("?" * len(ids)) or "NULL"
        where = f"(l.branch_id IN ({marks}){' OR l.branch_id IS NULL' if g.user.is_super_admin else ''})"
        pending_n = conn.scalar(f"SELECT COUNT(*) FROM leave_requests l WHERE l.status = 'pending' AND {where}", ids) or 0
        if show in ("pending", "all", "today"):
            extra = {"pending": " AND l.status = 'pending'", "all": "",
                     "today": " AND l.status = 'approved' AND l.start_date <= ? AND l.end_date >= ?"}[show]
            args = ids + ([today().isoformat(), today().isoformat()] if show == "today" else [])
            rows = conn.all("SELECT l.*, e.full_name, e.position, b.name AS branch, u.name AS reviewer, rl.full_name AS reliever FROM leave_requests l "
                            "LEFT JOIN employees rl ON rl.id = l.reliever_id "
                            "JOIN employees e ON e.id = l.employee_id LEFT JOIN branches b ON b.id = l.branch_id "
                            f"LEFT JOIN users u ON u.id = l.reviewed_by WHERE {where}{extra} ORDER BY "
                            "CASE l.status WHEN 'pending' THEN 0 ELSE 1 END, l.start_date DESC, l.id DESC LIMIT 300", args)
    bal = balance(conn, me) if me else None
    if rows:
        emps = {r["employee_id"] for r in rows}
        cache = {e["id"]: balance(conn, e) for e in conn.all(f"SELECT * FROM employees WHERE id IN ({','.join('?' * len(emps))})", list(emps))}
        rows = [{**dict(r), "bal": cache.get(r["employee_id"])} for r in rows]
    balances = []
    if show == "balances" and g.user.can("leave.approve"):
        ids2 = [b["id"] for b in branches_for_user(g.user, include_all=g.user.is_super_admin)]
        m2 = ",".join("?" * len(ids2)) or "NULL"
        for e in conn.all(f"SELECT e.*, b.name AS branch FROM employees e LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE e.active = 1 "
                          f"AND (e.primary_branch_id IN ({m2}){' OR e.primary_branch_id IS NULL' if g.user.is_super_admin else ''}) "
                          "ORDER BY e.full_name", ids2):
            balances.append({"e": e, **balance(conn, e)})
    used = {}
    if me:
        y = str(today().year)
        for r in conn.all("SELECT leave_type, SUM(days) AS d FROM leave_requests WHERE employee_id = ? AND status = 'approved' "
                          "AND substr(start_date, 1, 4) = ? GROUP BY leave_type", (me["id"], y)):
            used[r["leave_type"]] = r["d"]
    return render_template("staff/leave/index.html", me=me, mine=mine, rows=rows, show=show, pending_n=pending_n, types=LEAVE_TYPES,
                           status=STATUS, used=used, SIL=SIL, today=today().isoformat(), can_review=_can_review,
                           bal=bal, balances=balances, relievers=reliever_choices(conn, me) if me else [],
                           me_dentist=is_dentist(conn, me) if me else False)


@bp.route("/<int:leave_id>", methods=["POST"])
@require("leave.request", "leave.approve", any_of=True)
def act(leave_id):
    conn = get_db()
    lr = conn.one("SELECT l.*, e.full_name, e.user_id FROM leave_requests l JOIN employees e ON e.id = l.employee_id WHERE l.id = ?", (leave_id,))
    if not lr:
        abort(404)
    action = request.form.get("action")
    note = clean(request.form.get("note"), 300)
    back = redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/staff/leave") else url_for("leave.index"))
    if action == "cancel":
        if lr["user_id"] != g.user.id or lr["status"] not in ("pending", "approved") or \
                (lr["status"] == "approved" and lr["start_date"] <= today().isoformat()):
            flash("Only your own pending leave, or an approved leave that hasn't started yet, can be cancelled.", "error")
            return back
        with conn.transaction():
            if lr["status"] == "approved":
                _mark_attendance(conn, lr, False)
            conn.execute("UPDATE leave_requests SET status = 'cancelled' WHERE id = ?", (lr["id"],))
            audit.record("leave_cancelled", "leave", lr["id"], f"{lr['full_name']} cancelled {lr['leave_type']} {lr['start_date']}",
                         branch_id=lr["branch_id"])
        flash("Leave cancelled.", "success")
        return back
    if action not in ("approve", "disapprove"):
        abort(400)
    if not _can_review(lr):
        abort(403)
    if lr["status"] != "pending":
        flash("This leave form was already decided.", "error")
        return back
    if action == "approve" and lr["with_pay"]:
        emp = conn.one("SELECT * FROM employees WHERE id = ?", (lr["employee_id"],))
        b = balance(conn, emp, int(lr["start_date"][:4]), exclude_id=lr["id"])
        if lr["days"] > b["entitled"] - b["used"]:
            flash(f"Not enough leave with pay left for {lr['full_name']}: {max(0, b['entitled'] - b['used']):g} day(s). "
                  "Disapprove it, or ask them to file it without pay.", "error")
            return back
    if action == "disapprove" and len(note) < 3:
        flash("Write the reason for disapproving.", "error")
        return back
    with conn.transaction():
        new = "approved" if action == "approve" else "disapproved"
        conn.execute("UPDATE leave_requests SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                     (new, note, g.user.id, now_str(), lr["id"]))
        if new == "approved":
            _mark_attendance(conn, lr, True)
            if lr["reliever_id"]:
                rel = conn.one("SELECT user_id FROM employees WHERE id = ?", (lr["reliever_id"],))
                if rel and rel["user_id"]:
                    notify(conn, [rel["user_id"]], "leave", f"You are the reliever for {lr['full_name']}",
                           f"{lr['leave_type']}, {lr['start_date']}" + (f" to {lr['end_date']}" if lr["end_date"] != lr["start_date"] else ""),
                           url_for("leave.index", show="mine"))
        audit.record(f"leave_{new}", "leave", lr["id"], f"{new.capitalize()} {lr['full_name']}'s {lr['leave_type']} "
                     f"{lr['start_date']} to {lr['end_date']}" + (f": {note}" if note else ""), branch_id=lr["branch_id"])
        notify(conn, [lr["user_id"]], "leave", f"Your leave was {new}", f"{lr['leave_type']}, {lr['start_date']}"
               + (f" to {lr['end_date']}" if lr["end_date"] != lr["start_date"] else "") + (f". Note: {note}" if note else ""),
               url_for("leave.index", show="mine"))
    flash(f"Leave {new}.", "success")
    return back


@bp.route("/entitlement/<int:emp_id>", methods=["POST"])
@require("leave.approve")
def set_entitlement(emp_id):
    conn = get_db()
    e = conn.one("SELECT * FROM employees WHERE id = ?", (emp_id,))
    if not e or not (g.user.is_super_admin or (e["primary_branch_id"] and g.user.in_branch(e["primary_branch_id"]))):
        abort(404)
    raw = (request.form.get("days") or "").strip()
    try:
        days = None if raw == "" else float(raw)
    except ValueError:
        days = -1
    if days is not None and not 0 <= days <= 60:
        flash("Enter 0 to 60 days, or leave it empty for the default (5 for regular employees).", "error")
    else:
        conn.execute("UPDATE employees SET paid_leave_days = ? WHERE id = ?", (days, emp_id))
        audit.record("paid_leave_set", "employee", emp_id, f"Leave with pay for {e['full_name']}: "
                     + (f"{days:g} day(s) a year" if days is not None else "default"), branch_id=e["primary_branch_id"])
        flash("Saved.", "success")
    return redirect(url_for("leave.index", show="balances"))


@bp.route("/<int:leave_id>/attachment")
@require("leave.request", "leave.approve", any_of=True)
def attachment(leave_id):
    conn = get_db()
    lr = conn.one("SELECT l.*, e.user_id FROM leave_requests l JOIN employees e ON e.id = l.employee_id WHERE l.id = ?", (leave_id,))
    if not lr or not lr["attachment"]:
        abort(404)
    if lr["user_id"] != g.user.id and not (g.user.can("leave.approve") and (g.user.is_super_admin or g.user.in_branch(lr["branch_id"]))):
        abort(403)
    resp = send_file(document_path(lr["attachment"]), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

"""Announcements and the monthly duty schedule.

- Everyone signed in sees the announcements for their branches (and clinic-wide ones) and who is on duty.
- HR, supervisors, the super admin, or anyone given "announcements.manage" posts announcements and sets the duty
  schedule of a branch for a whole month (employees x days grid, with a weekly-pattern quick fill).
- Nothing here holds patient information.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import login_required, require
from ..db import get_db
from ..notices import notify
from ..util import clean, now_str, parse_date, to_int, today
from .common import branches_for_user

bp = Blueprint("announce", __name__, url_prefix="/staff/announcements")

# A dentist: has a dentist login, or has no login yet and the employee record's position says dentist
# (e.g. "Dentist", "Associate dentist"; not "Dental assistant").
IS_DENT = ("(u.role = 'dentist' OR (e.user_id IS NULL AND lower(e.position) LIKE '%dentist%' "
           "AND lower(e.position) NOT LIKE '%assistant%'))")
ROLE = f"CASE WHEN {IS_DENT} THEN 'dentist' ELSE u.role END AS role"

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------- helpers ----------

def parse_month(raw: str | None) -> date:
    try:
        y, m = (raw or "").split("-")
        return date(int(y), int(m), 1)
    except (ValueError, TypeError):
        t = today()
        return date(t.year, t.month, 1)


def month_days(first: date) -> list[date]:
    n = calendar.monthrange(first.year, first.month)[1]
    return [first + timedelta(days=i) for i in range(n)]


def shift_month(first: date, delta: int) -> date:
    m = first.month - 1 + delta
    return date(first.year + m // 12, m % 12 + 1, 1)


def active_announcements(conn, user, limit: int | None = None):
    """Announcements showing today: clinic-wide ones and those of the user's branches (managers see all branches)."""
    t = today().isoformat()
    rows = conn.all("SELECT a.*, b.name AS branch, u.name AS author FROM announcements a LEFT JOIN branches b ON b.id = a.branch_id "
                    "LEFT JOIN users u ON u.id = a.created_by WHERE a.starts_on <= ? AND (a.ends_on IS NULL OR a.ends_on >= ?) "
                    "ORDER BY a.pinned DESC, a.starts_on DESC, a.id DESC", (t, t))
    out = [r for r in rows if r["branch_id"] is None or user.is_super_admin or user.can("announcements.manage") or user.in_branch(r["branch_id"])]
    return out[:limit] if limit else out


def duty_on(conn, day: date, branch_ids: list[int] | None = None) -> list[dict]:
    """[{branch, people: [{name, position, dentist}]}] for one day, branches in their usual order."""
    rows = conn.all("SELECT d.branch_id, d.note, e.id AS employee_id, e.full_name, e.position, e.user_id, " + ROLE + ", b.name AS branch, b.sort_order "
                    "FROM duty_assignments d JOIN employees e ON e.id = d.employee_id JOIN branches b ON b.id = d.branch_id "
                    "LEFT JOIN users u ON u.id = e.user_id WHERE d.work_date = ? ORDER BY b.sort_order, " + IS_DENT + " DESC, e.full_name",
                    (day.isoformat(),))
    groups: dict[int, dict] = {}
    for r in rows:
        if branch_ids is not None and r["branch_id"] not in branch_ids:
            continue
        grp = groups.setdefault(r["branch_id"], {"branch_id": r["branch_id"], "branch": r["branch"], "people": []})
        grp["people"].append({"id": r["employee_id"], "name": r["full_name"], "position": r["position"], "dentist": r["role"] == "dentist",
                              "user_id": r["user_id"], "note": r["note"]})
    return list(groups.values())


def _my_employee(conn):
    return conn.one("SELECT * FROM employees WHERE user_id = ? AND active = 1", (g.user.id,))


def _default_branch(conn, branches):
    me = _my_employee(conn)
    ids = [b["id"] for b in branches]
    if me and me["primary_branch_id"] in ids:
        return me["primary_branch_id"]
    mine = [b["id"] for b in branches if g.user.in_branch(b["id"])]
    return (mine or ids or [None])[0]


def roster_rows(conn, branch_id: int, first: date, extra_ids: list[int]) -> list[dict]:
    """People to show in the editing grid: employees of the branch, dentists who work there, anyone already on this
    month's schedule, and anyone the manager added from another branch."""
    last = month_days(first)[-1]
    ids = {r["id"] for r in conn.all("SELECT id FROM employees WHERE active = 1 AND primary_branch_id = ?", (branch_id,))}
    ids |= {r["id"] for r in conn.all("SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id JOIN user_branches ub ON ub.user_id = u.id "
                                      "WHERE e.active = 1 AND u.role = 'dentist' AND u.active = 1 AND ub.branch_id = ?", (branch_id,))}
    # dentists without a login yet and with no home branch set: they can be scheduled at any branch
    ids |= {r["id"] for r in conn.all(f"SELECT e.id FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.active = 1 "
                                      f"AND e.user_id IS NULL AND e.primary_branch_id IS NULL AND {IS_DENT}")}
    ids |= {r["employee_id"] for r in conn.all("SELECT DISTINCT employee_id FROM duty_assignments WHERE branch_id = ? AND work_date BETWEEN ? AND ?",
                                               (branch_id, first.isoformat(), last.isoformat()))}
    ids |= set(extra_ids)
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = conn.all(f"SELECT e.id, e.full_name, e.position, e.primary_branch_id, b.name AS home_branch, e.user_id IS NULL AS no_login, {ROLE} FROM employees e "
                    f"LEFT JOIN users u ON u.id = e.user_id LEFT JOIN branches b ON b.id = e.primary_branch_id "
                    f"WHERE e.id IN ({marks}) AND (u.role IS NULL OR u.role != 'super_admin') "
                    f"ORDER BY {IS_DENT} DESC, e.full_name", list(ids))
    return [dict(r) for r in rows]


# ---------- announcements ----------

@bp.route("/")
@login_required
def index():
    conn = get_db()
    branches = branches_for_user(g.user, include_all=True)
    t = today()
    my_branch_ids = None if (g.user.is_super_admin or g.user.can("announcements.manage")) else [b["id"] for b in branches if g.user.in_branch(b["id"])]
    data = {
        "items": active_announcements(conn, g.user),
        "duty_today": duty_on(conn, t),
        "duty_tomorrow": duty_on(conn, t + timedelta(days=1)),
        "branches": branches,
        "my_branch_ids": my_branch_ids,
        "today": t,
        "me": _my_employee(conn),
    }
    if g.user.can("announcements.manage"):
        data["upcoming"] = conn.all("SELECT a.*, b.name AS branch FROM announcements a LEFT JOIN branches b ON b.id = a.branch_id "
                                    "WHERE a.starts_on > ? ORDER BY a.starts_on", (t.isoformat(),))
        data["ended"] = conn.all("SELECT a.*, b.name AS branch FROM announcements a LEFT JOIN branches b ON b.id = a.branch_id "
                                 "WHERE a.ends_on < ? ORDER BY a.ends_on DESC LIMIT 20", (t.isoformat(),))
    return render_template("staff/announce/index.html", **data)


@bp.route("/post", methods=["POST"])
@require("announcements.manage")
def post():
    conn = get_db()
    f = request.form
    title = clean(f.get("title"), 150)
    body = clean(f.get("body"), 2000)
    starts = parse_date(f.get("starts_on")) or today()
    ends = parse_date(f.get("ends_on"))
    branch_id = to_int(f.get("branch_id")) or None
    if not title:
        flash("Write a title for the announcement.", "error")
        return redirect(url_for("announce.index"))
    if ends and ends < starts:
        flash("The end date can't be before the start date.", "error")
        return redirect(url_for("announce.index"))
    if branch_id and not conn.one("SELECT 1 AS x FROM branches WHERE id = ? AND active = 1", (branch_id,)):
        abort(400)
    with conn.transaction():
        aid = conn.insert("announcements", {"branch_id": branch_id, "title": title, "body": body, "pinned": 1 if f.get("pinned") else 0,
                                            "starts_on": starts.isoformat(), "ends_on": ends.isoformat() if ends else None,
                                            "created_by": g.user.id, "created_at": now_str()})
        audit.record("announcement.post", "announcement", aid, title, branch_id=branch_id)
        sent = 0
        if f.get("notify") and starts <= today():
            if branch_id:
                users = [r["user_id"] for r in conn.all("SELECT ub.user_id FROM user_branches ub JOIN users u ON u.id = ub.user_id "
                                                        "WHERE ub.branch_id = ? AND u.active = 1", (branch_id,))]
            else:
                users = [r["id"] for r in conn.all("SELECT id FROM users WHERE active = 1")]
            sent = notify(conn, users, "announcement", "Announcement: " + title, body[:300], url_for("announce.index"), exclude=g.user.id)
    flash("Announcement posted." + (f" {sent} people notified." if sent else ""), "success")
    return redirect(url_for("announce.index"))


@bp.route("/<int:aid>/delete", methods=["POST"])
@require("announcements.manage")
def delete(aid):
    conn = get_db()
    a = conn.one("SELECT * FROM announcements WHERE id = ?", (aid,))
    if not a:
        abort(404)
    with conn.transaction():
        conn.execute("DELETE FROM announcements WHERE id = ?", (aid,))
        audit.record("announcement.delete", "announcement", aid, a["title"], branch_id=a["branch_id"])
    flash("Announcement removed.", "success")
    return redirect(url_for("announce.index"))


# ---------- duty schedule ----------

@bp.route("/duty")
@login_required
def duty():
    conn = get_db()
    branches = branches_for_user(g.user, include_all=True)
    first = parse_month(request.args.get("month"))
    raw = request.args.get("branch")
    branch_id = None if raw == "all" else (to_int(raw) or _default_branch(conn, branches))
    if branch_id and branch_id not in [b["id"] for b in branches]:
        abort(404)
    days = month_days(first)
    q = ("SELECT d.work_date, d.branch_id, d.note, e.id AS employee_id, e.full_name, e.position, " + ROLE + ", b.name AS branch FROM duty_assignments d "
         "JOIN employees e ON e.id = d.employee_id JOIN branches b ON b.id = d.branch_id LEFT JOIN users u ON u.id = e.user_id "
         "WHERE d.work_date BETWEEN ? AND ?")
    params = [days[0].isoformat(), days[-1].isoformat()]
    if branch_id:
        q += " AND d.branch_id = ?"
        params.append(branch_id)
    rows = conn.all(q + " ORDER BY b.sort_order, " + IS_DENT + " DESC, e.full_name", params)
    me = _my_employee(conn)
    only_me = bool(request.args.get("mine")) and me
    by_day: dict[str, list] = {d.isoformat(): [] for d in days}
    mine = 0
    for r in rows:
        if only_me and r["employee_id"] != me["id"]:
            continue
        by_day[r["work_date"]].append(dict(r))
        if me and r["employee_id"] == me["id"]:
            mine += 1
    # someone on duty at two branches on the same day
    seen: dict[tuple, set] = {}
    for r in conn.all("SELECT work_date, employee_id, branch_id FROM duty_assignments WHERE work_date BETWEEN ? AND ?", params[:2]):
        seen.setdefault((r["work_date"], r["employee_id"]), set()).add(r["branch_id"])
    double = {k for k, v in seen.items() if len(v) > 1}
    return render_template("staff/announce/duty.html", branches=branches, branch_id=branch_id, first=first, days=days, by_day=by_day,
                           prev=shift_month(first, -1), next=shift_month(first, 1), today=today(), me=me, only_me=only_me, mine=mine,
                           double=double, weekdays=WEEKDAYS)


@bp.route("/duty/edit", methods=["GET", "POST"])
@require("announcements.manage")
def duty_edit():
    conn = get_db()
    branches = branches_for_user(g.user, include_all=True)
    ids = [b["id"] for b in branches]
    first = parse_month(request.values.get("month"))
    branch_id = to_int(request.values.get("branch")) or _default_branch(conn, branches)
    if branch_id not in ids:
        abort(404)
    days = month_days(first)
    extra = [i for i in (to_int(x) for x in request.values.getlist("add")) if i]
    people = roster_rows(conn, branch_id, first, extra)
    branch = next(b for b in branches if b["id"] == branch_id)

    if request.method == "POST":
        f = request.form
        valid = {p["id"] for p in people}
        day_set = {d.isoformat() for d in days}
        chosen: set[tuple[str, int]] = set()
        for p in people:
            for v in f.getlist(f"d_{p['id']}"):
                if v in day_set:
                    chosen.add((v, p["id"]))
            pattern = {to_int(x) for x in f.getlist(f"w_{p['id']}")}
            for d in days:
                if d.weekday() in pattern:
                    chosen.add((d.isoformat(), p["id"]))
        chosen = {c for c in chosen if c[1] in valid}
        notes = {d.isoformat(): clean(f.get(f"n_{d.isoformat()}"), 80) for d in days}
        with conn.transaction():
            conn.execute("DELETE FROM duty_assignments WHERE branch_id = ? AND work_date BETWEEN ? AND ?",
                         (branch_id, days[0].isoformat(), days[-1].isoformat()))
            stamp = now_str()
            for day, emp in sorted(chosen):
                conn.insert("duty_assignments", {"branch_id": branch_id, "work_date": day, "employee_id": emp, "note": notes.get(day) or "",
                                                 "created_by": g.user.id, "created_at": stamp})
            audit.record("duty.save", "branch", branch_id, f"Duty schedule {first:%B %Y}: {len(chosen)} duty day(s)", branch_id=branch_id)
            sent = 0
            if f.get("notify"):
                emp_ids = sorted({c[1] for c in chosen})
                users = [r["user_id"] for r in conn.all(f"SELECT user_id FROM employees WHERE user_id IS NOT NULL AND id IN ({','.join('?' * len(emp_ids))})",
                                                        emp_ids)] if emp_ids else []
                sent = notify(conn, users, "duty", f"Duty schedule: {branch['name']}, {first:%B %Y}", "Your duty days are posted. Open to see them.",
                              url_for("announce.duty", branch=branch_id, month=f"{first:%Y-%m}", mine=1), exclude=g.user.id)
            clash = conn.all("SELECT d.work_date, e.full_name, b.name AS other FROM duty_assignments d JOIN employees e ON e.id = d.employee_id "
                             "JOIN branches b ON b.id = d.branch_id JOIN duty_assignments mine ON mine.employee_id = d.employee_id "
                             "AND mine.work_date = d.work_date AND mine.branch_id = ? WHERE d.branch_id != ? AND d.work_date BETWEEN ? AND ? "
                             "ORDER BY d.work_date", (branch_id, branch_id, days[0].isoformat(), days[-1].isoformat()))
        flash(f"Duty schedule saved for {branch['name']}, {first:%B %Y}." + (f" {sent} people notified." if sent else ""), "success")
        if clash:
            listed = "; ".join(f"{c['full_name']} on {c['work_date']} (also at {c['other']})" for c in clash[:6])
            flash(f"Check these: on duty at two branches the same day: {listed}" + (" …" if len(clash) > 6 else ""), "warning")
        return redirect(url_for("announce.duty", branch=branch_id, month=f"{first:%Y-%m}"))

    taken = {(r["work_date"], r["employee_id"]) for r in conn.all(
        "SELECT work_date, employee_id FROM duty_assignments WHERE branch_id = ? AND work_date BETWEEN ? AND ?",
        (branch_id, days[0].isoformat(), days[-1].isoformat()))}
    notes = {r["work_date"]: r["note"] for r in conn.all(
        "SELECT work_date, MAX(note) AS note FROM duty_assignments WHERE branch_id = ? AND work_date BETWEEN ? AND ? AND note != '' GROUP BY work_date",
        (branch_id, days[0].isoformat(), days[-1].isoformat()))}
    elsewhere = {}
    for r in conn.all("SELECT d.work_date, d.employee_id, b.name FROM duty_assignments d JOIN branches b ON b.id = d.branch_id "
                      "WHERE d.branch_id != ? AND d.work_date BETWEEN ? AND ?", (branch_id, days[0].isoformat(), days[-1].isoformat())):
        elsewhere[(r["work_date"], r["employee_id"])] = r["name"]
    shown = {p["id"] for p in people}
    others = [dict(r) for r in conn.all("SELECT e.id, e.full_name, e.position, b.name AS home_branch, " + ROLE + " FROM employees e LEFT JOIN users u ON u.id = e.user_id "
                                        "LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE e.active = 1 "
                                        "AND (u.role IS NULL OR u.role != 'super_admin') ORDER BY e.full_name") if r["id"] not in shown]
    return render_template("staff/announce/edit.html", branches=branches, branch=branch, branch_id=branch_id, first=first, days=days,
                           people=people, taken=taken, notes=notes, elsewhere=elsewhere, others=others, extra=extra,
                           prev=shift_month(first, -1), next=shift_month(first, 1), weekdays=WEEKDAYS, today=today())

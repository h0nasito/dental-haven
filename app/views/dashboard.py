"""Role-appropriate dashboards, the receptionist work queue and the branch switcher."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from ..auth import login_required, require
from ..db import get_db
from ..permissions import branch_filter
from ..util import now, now_str, to_int, today
from .common import followup_scope

bp = Blueprint("dash", __name__, url_prefix="/staff")


@bp.route("/")
@require("dashboard.view")
def home():
    conn = get_db()
    user = g.user
    t = today()
    d0, d1 = t.isoformat(), (t + timedelta(days=1)).isoformat()
    d7 = (t + timedelta(days=8)).isoformat()
    bf, bp_ = branch_filter(user, "a.branch_id")
    appt_scope, appt_params = bf, bp_
    if user.own_schedule_only:
        appt_scope, appt_params = "a.dentist_id = ?", [user.id]
    data = {}
    if user.can("appointments.view"):
        data["today_appts"] = conn.all(
            "SELECT a.*, p.first_name, p.last_name, p.alert_flag, s.name AS service, u.name AS dentist, b.name AS branch "
            "FROM appointments a JOIN patients p ON p.id = a.patient_id JOIN services s ON s.id = a.service_id "
            "LEFT JOIN users u ON u.id = a.dentist_id JOIN branches b ON b.id = a.branch_id "
            f"WHERE a.start_at >= ? AND a.start_at < ? AND {appt_scope} ORDER BY a.start_at", [d0, d1, *appt_params])
        data["upcoming_count"] = conn.scalar(
            f"SELECT COUNT(*) FROM appointments a WHERE a.start_at >= ? AND a.start_at < ? "
            f"AND a.status IN ('requested','confirmed') AND {appt_scope}", [d1, d7, *appt_params])
    if user.can("bookings.manage") or user.can("bookings.view"):
        rf, rp = branch_filter(user, "branch_id")
        data["pending_requests"] = conn.scalar(f"SELECT COUNT(*) FROM booking_requests WHERE status='pending' AND {rf}", rp)
    if user.can("leads.view"):
        lf, lp = branch_filter(user, "branch_id")
        since = (t - timedelta(days=30)).isoformat()
        data["new_leads"] = conn.scalar(f"SELECT COUNT(*) FROM leads WHERE status='new' AND ({lf} OR branch_id IS NULL)", lp)
        total30 = conn.scalar(f"SELECT COUNT(*) FROM leads WHERE created_at >= ? AND ({lf} OR branch_id IS NULL)", [since, *lp])
        conv30 = conn.scalar(f"SELECT COUNT(*) FROM leads WHERE created_at >= ? AND status IN ('booked','converted') "
                             f"AND ({lf} OR branch_id IS NULL)", [since, *lp])
        data["leads30"] = total30
        data["conversion"] = round(100 * conv30 / total30) if total30 else None
    if user.can("followups.view"):
        fq, fp = followup_scope(user)
        data["overdue"] = conn.scalar(f"SELECT COUNT(*) FROM follow_ups f WHERE f.status='open' AND f.due_at < ? AND {fq}",
                                      [now_str(), *fp])
        data["due_today"] = conn.scalar(
            f"SELECT COUNT(*) FROM follow_ups f WHERE f.status='open' AND f.due_at >= ? AND f.due_at < ? AND {fq}",
            [now_str(), d1, *fp])
    if user.can("reports.sales"):
        month_start = t.replace(day=1).isoformat()
        rows = []
        for b in conn.all("SELECT id, name FROM branches WHERE active=1 ORDER BY sort_order"):
            if b["id"] not in user.scope_branch_ids:
                continue
            sales = conn.scalar("SELECT COALESCE(SUM(total_cents),0) FROM invoices WHERE status='issued' AND branch_id=? "
                                "AND issued_at >= ? AND issued_at <= ?", (b["id"], month_start, d0))
            from ..billing import collections
            coll = collections(conn, [b["id"]], month_start, d0)["net"]
            rows.append({"branch": b["name"], "sales": sales, "collections": coll})
        data["sales_rows"] = rows
        data["sales_max"] = max([max(r["sales"], r["collections"]) for r in rows] + [1])
    if user.can("reports.operations"):
        vf, vp = branch_filter(user, "a.branch_id")
        since = (t - timedelta(days=30)).isoformat()
        data["visits30"] = conn.scalar(f"SELECT COUNT(*) FROM appointments a WHERE a.status='completed' AND a.start_at >= ? AND {vf}", [since, *vp])
        data["noshow30"] = conn.scalar(f"SELECT COUNT(*) FROM appointments a WHERE a.status='no_show' AND a.start_at >= ? AND {vf}", [since, *vp])
        data["top_services"] = conn.all(
            f"SELECT s.name, COUNT(*) AS n FROM appointments a JOIN services s ON s.id = a.service_id "
            f"WHERE a.status='completed' AND a.start_at >= ? AND {vf} GROUP BY s.name ORDER BY n DESC LIMIT 5", [since, *vp])
    if user.can("attendance.manage") or user.can("payroll.prepare"):
        af, ap = branch_filter(user, "branch_id")
        data["att_exceptions"] = conn.scalar(f"SELECT COUNT(*) FROM time_records WHERE status='exception' AND {af}", ap)
        data["payroll_open"] = conn.all("SELECT * FROM payroll_periods WHERE status IN ('draft','submitted') ORDER BY start_date DESC LIMIT 3")
    if user.can("reportcards.review"):
        if user.role == "dentist":
            data["reviews"] = conn.scalar("SELECT COUNT(*) FROM report_cards WHERE status='pending_review' AND reviewer_id=?", (user.id,))
        else:
            rf, rp = branch_filter(user, "branch_id")
            data["reviews"] = conn.scalar(f"SELECT COUNT(*) FROM report_cards WHERE status='pending_review' AND {rf}", rp)
    if user.can("calendar.birthdays") and user.can("patients.view"):
        data["birthdays"] = birthdays_this_week(conn, user)
    if user.can("dashboard.balances"):
        bf2, bp2 = branch_filter(user, "i.branch_id")
        data["balances"] = conn.all(
            "SELECT p.id, p.first_name, p.last_name, p.chart_no, SUM(i.total_cents - COALESCE((SELECT SUM(CASE WHEN kind='payment' THEN amount_cents "
            "ELSE -amount_cents END) FROM payments WHERE invoice_id = i.id AND status='valid'), 0)) AS balance "
            f"FROM invoices i JOIN patients p ON p.id = i.patient_id WHERE i.status = 'issued' AND p.active = 1 AND {bf2} "
            "GROUP BY p.id, p.first_name, p.last_name, p.chart_no HAVING SUM(i.total_cents - COALESCE((SELECT SUM(CASE WHEN kind='payment' "
            "THEN amount_cents ELSE -amount_cents END) FROM payments WHERE invoice_id = i.id AND status='valid'), 0)) > 0 "
            "ORDER BY balance DESC LIMIT 10", bp2)
    return render_template("staff/dashboard.html", d=data, now=now())


def birthdays_this_week(conn, user):
    """Patients (in the user's scope) whose birthday falls in the next 7 days."""
    from ..permissions import patient_scope
    frag, params = patient_scope(user, "p")
    t = today()
    days = [(t + timedelta(days=i)).strftime("%m-%d") for i in range(7)]
    marks = ",".join("?" for _ in days)
    rows = conn.all(f"SELECT p.id, p.first_name, p.last_name, p.birth_date FROM patients p WHERE {frag} AND p.active = 1 "
                    f"AND p.birth_date IS NOT NULL AND substr(p.birth_date, 6, 5) IN ({marks}) LIMIT 200", [*params, *days])
    for r in rows:
        md = r["birth_date"][5:10]
        r["days_away"] = days.index(md)
        r["turning"] = t.year - int(r["birth_date"][:4]) + (1 if md < t.strftime("%m-%d") else 0)
    return sorted(rows, key=lambda r: r["days_away"])


@bp.route("/queue")
@require("dashboard.view")
def queue():
    user = g.user
    if not (user.can("bookings.manage") or user.can("bookings.view") or user.can("leads.view") or user.can("followups.view")):
        abort(403)
    conn = get_db()
    t = today()
    tomorrow = (t + timedelta(days=1)).isoformat()
    q = {}
    if user.can("bookings.manage") or user.can("bookings.view"):
        rf, rp = branch_filter(user, "r.branch_id")
        q["requests"] = conn.all(
            "SELECT r.*, b.name AS branch, s.name AS service FROM booking_requests r JOIN branches b ON b.id = r.branch_id "
            f"JOIN services s ON s.id = r.service_id WHERE r.status='pending' AND {rf} ORDER BY r.preferred_start", rp)
    if user.can("leads.view"):
        lf, lp = branch_filter(user, "l.branch_id")
        q["new_leads"] = conn.all(
            "SELECT l.*, b.name AS branch, s.name AS service FROM leads l LEFT JOIN branches b ON b.id = l.branch_id "
            f"LEFT JOIN services s ON s.id = l.service_id WHERE l.status='new' AND ({lf} OR l.branch_id IS NULL) "
            "ORDER BY l.created_at", lp)
        q["lead_followups"] = conn.all(
            "SELECT l.*, b.name AS branch FROM leads l LEFT JOIN branches b ON b.id = l.branch_id "
            f"WHERE l.status IN ('contacted','qualified') AND l.next_follow_up_at IS NOT NULL AND l.next_follow_up_at < ? "
            f"AND ({lf} OR l.branch_id IS NULL) ORDER BY l.next_follow_up_at", [tomorrow, *lp])
    if user.can("followups.view"):
        fq, fp = followup_scope(user)
        q["followups"] = conn.all(
            "SELECT f.*, p.first_name, p.last_name, l.full_name AS lead_name, u.name AS assignee FROM follow_ups f "
            "LEFT JOIN patients p ON p.id = f.patient_id LEFT JOIN leads l ON l.id = f.lead_id "
            f"LEFT JOIN users u ON u.id = f.assignee_id WHERE f.status='open' AND f.due_at < ? AND {fq} ORDER BY f.due_at",
            [tomorrow, *fp])
    if user.can("reminders.view"):
        rf, rp = branch_filter(user, "r.branch_id")
        q["reminders_due"] = conn.scalar(
            f"SELECT COUNT(*) FROM reminders r WHERE r.status='pending' AND r.scheduled_for < ? AND {rf}", [tomorrow, *rp])
    return render_template("staff/queue.html", q=q, now_s=now_str())


@bp.route("/branch", methods=["POST"])
@login_required
def switch_branch():
    branch_id = to_int(request.form.get("branch_id"))
    if branch_id is not None and branch_id not in g.user.branch_ids:
        abort(403)
    get_db().execute("UPDATE sessions SET active_branch_id = ? WHERE id_hash = ?", (branch_id, g.session_hash))
    target = request.form.get("next") or url_for("dash.home")
    if not target.startswith("/staff") or "//" in target:
        target = url_for("dash.home")
    return redirect(target)

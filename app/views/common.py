"""Helpers shared by staff views."""
from __future__ import annotations

from flask import abort, g, request

from ..db import get_db
from ..permissions import branch_filter
from ..util import now_str, today


def register_context(app):
    @app.context_processor
    def _nav():
        user = g.get("user")
        if not user or not request.path.startswith("/staff"):
            return {}
        conn = get_db()
        branches = conn.all("SELECT id, name FROM branches WHERE active = 1 ORDER BY sort_order")
        nav_branches = [b for b in branches if b["id"] in user.branch_ids]
        counts = {"requests": 0, "overdue": 0, "queue": 0, "reviews": 0}
        bf, bp = branch_filter(user, "branch_id")
        if user.can("bookings.manage") or user.can("bookings.view"):
            counts["requests"] = conn.scalar(f"SELECT COUNT(*) FROM booking_requests WHERE status='pending' AND {bf}", bp)
        if user.can("followups.view"):
            fq, fp = followup_scope(user)
            counts["overdue"] = conn.scalar(
                f"SELECT COUNT(*) FROM follow_ups f WHERE f.status='open' AND f.due_at < ? AND {fq}", [now_str(), *fp])
        new_leads = 0
        if user.can("leads.view"):
            lf, lp = branch_filter(user, "branch_id")
            new_leads = conn.scalar(f"SELECT COUNT(*) FROM leads WHERE status='new' AND ({lf} OR branch_id IS NULL)", lp)
        counts["queue"] = (counts["requests"] or 0) + (counts["overdue"] or 0) + (new_leads or 0)
        if user.can("reportcards.review"):
            if user.role == "dentist":
                counts["reviews"] = conn.scalar(
                    "SELECT COUNT(*) FROM report_cards WHERE status='pending_review' AND reviewer_id = ?", (user.id,))
            else:
                counts["reviews"] = conn.scalar(
                    f"SELECT COUNT(*) FROM report_cards WHERE status='pending_review' AND {bf}", bp)
        lab_ids = [r["lab_id"] for r in conn.all("SELECT lab_id FROM user_labs WHERE user_id = ?", (user.id,))]
        nav_lab = user.is_super_admin or user.can("lab.view") or bool(lab_ids)
        return {"nav_branches": nav_branches, "nav_counts": counts, "nav_lab": nav_lab}


def followup_scope(user, alias="f"):
    """Follow-ups in the user's branches; dentists see follow-ups for their assigned patients."""
    if user.role == "dentist":
        return (f"{alias}.patient_id IN (SELECT patient_id FROM patient_assignments WHERE dentist_id = ?)", [user.id])
    bf, bp = branch_filter(user, f"{alias}.branch_id")
    return f"({bf} OR ({alias}.branch_id IS NULL AND {alias}.assignee_id = ?))", [*bp, user.id]


def branches_for_user(user, include_all=False):
    conn = get_db()
    rows = conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")
    if include_all:
        return rows
    return [b for b in rows if b["id"] in user.branch_ids]


def require_branch(branch_id):
    """Abort unless the current user works at this branch."""
    if branch_id is None or not g.user.in_branch(int(branch_id)):
        abort(403)


def dentists(branch_ids=None):
    conn = get_db()
    if branch_ids:
        marks = ",".join("?" for _ in branch_ids)
        return conn.all(
            f"SELECT DISTINCT u.id, u.name FROM users u JOIN user_branches ub ON ub.user_id = u.id "
            f"WHERE u.role='dentist' AND u.active=1 AND ub.branch_id IN ({marks}) ORDER BY u.name", branch_ids)
    return conn.all("SELECT id, name FROM users WHERE role='dentist' AND active=1 ORDER BY name")


def services(active_only=True):
    q = "SELECT * FROM services" + (" WHERE active = 1" if active_only else "") + " ORDER BY sort_order, name"
    return get_db().all(q)


def paginate(total: int, per_page: int = 25):
    page = max(1, int(request.args.get("page", 1) or 1))
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    return {"page": page, "pages": pages, "offset": (page - 1) * per_page, "limit": per_page, "total": total}


def date_range_args(default_days=30):
    from datetime import timedelta
    from ..util import parse_date
    end = parse_date(request.args.get("to")) or today()
    start = parse_date(request.args.get("from")) or (end - timedelta(days=default_days - 1))
    if start > end:
        start, end = end, start
    return start, end

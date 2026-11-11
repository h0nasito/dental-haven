"""Email each employee that their payslip is ready. The email has no amounts: it links to "My payslips", which needs
their sign-in. Sent from their branch's email account (see dentist_mail), only for approved payroll periods."""
from __future__ import annotations

from flask import current_app, url_for

from . import dentist_mail
from .util import now_str

STATUS_LABELS = {"pending": "Waiting to send", "sent": "Sent", "failed": "Failed", "not_set_up": "Not sent (email not set up)",
                 "demo": "Not sent (demo site)", "skipped": "Not sent"}


def recipients(conn, period_id: int) -> list[dict]:
    """Everyone with a line in the period, with their login email (or why there's none)."""
    rows = conn.all("SELECT l.employee_id, e.full_name, u.email, u.active AS user_active, b.slug AS branch_slug, b.name AS branch "
                    "FROM payroll_lines l JOIN employees e ON e.id = l.employee_id LEFT JOIN users u ON u.id = e.user_id "
                    "LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE l.period_id = ? ORDER BY e.full_name", (period_id,))
    out = []
    for r in rows:
        why = "" if r["email"] and r["user_active"] else ("No login" if not r["email"] else "Login is inactive")
        out.append({**dict(r), "why_not": why})
    return out


def queue(conn, period_id: int, by_user: int, again: bool = False) -> int:
    """Queue one email per employee not sent yet (again=True: everyone). Returns how many were queued."""
    sent = {r["employee_id"] for r in conn.all("SELECT employee_id FROM payslip_emails WHERE period_id = ? AND status IN ('sent', 'pending')",
                                               (period_id,))}
    n = 0
    for r in recipients(conn, period_id):
        if r["employee_id"] in sent and not again:
            continue
        conn.insert("payslip_emails", {"period_id": period_id, "employee_id": r["employee_id"], "email": r["email"] or "",
                                       "status": "skipped" if r["why_not"] else "pending", "error": r["why_not"],
                                       "created_by": by_user, "created_at": now_str()})
        n += 0 if r["why_not"] else 1
    return n


def compose(first_name: str, period, link: str) -> tuple[str, str]:
    subject = f"Your payslip is ready: {period['name']}"
    body = (f"Hi {first_name},\n\nYour payslip for {period['name']} ({period['start_date']} to {period['end_date']}) is ready.\n\n"
            f"Sign in to view it:\n{link}\n\nFor your privacy this email doesn't show your pay. If something looks wrong, "
            "talk to HR or your supervisor.\n\nDental Haven")
    return subject, body


def deliver(conn, period_id: int, limit: int = 5) -> int:
    """Send up to `limit` waiting emails. Never raises. Returns how many are still waiting."""
    demo = current_app.config.get("APP_ENV") == "demo"
    p = conn.one("SELECT * FROM payroll_periods WHERE id = ?", (period_id,))
    for q in conn.all("SELECT q.*, e.full_name, b.slug AS branch_slug, b.name AS branch FROM payslip_emails q JOIN employees e ON e.id = q.employee_id "
                      "LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE q.period_id = ? AND q.status = 'pending' ORDER BY q.id LIMIT ?",
                      (period_id, limit)):
        status, error = "sent", ""
        cfg = dentist_mail.config(q["branch_slug"], q["branch"] or "")
        if p["status"] != "approved":
            status, error = "skipped", "Payroll is not approved"
        elif demo:
            status = "demo"
        elif not cfg:
            status = "not_set_up"
        else:
            try:
                link = dentist_mail._base_url() + url_for("people.my_payslip", period_id=period_id)
                subject, body = compose((q["full_name"] or "").split(" ")[0], p, link)
                dentist_mail.send_email(q["email"], subject, body, cfg)
            except Exception as exc:  # noqa: BLE001 - report the failure without the message content
                status, error = "failed", f"{type(exc).__name__}: {str(exc)[:160]}"
                current_app.logger.warning("Payslip email %s failed: %s", q["id"], type(exc).__name__)
        conn.execute("UPDATE payslip_emails SET status = ?, error = ?, sent_at = ? WHERE id = ?",
                     (status, error, now_str() if status == "sent" else None, q["id"]))
    return conn.scalar("SELECT COUNT(*) FROM payslip_emails WHERE period_id = ? AND status = 'pending'", (period_id,)) or 0


def latest(conn, period_id: int) -> dict[int, dict]:
    """The latest email status per employee for the period."""
    out = {}
    for r in conn.all("SELECT * FROM payslip_emails WHERE period_id = ? ORDER BY id", (period_id,)):
        out[r["employee_id"]] = dict(r)
    return out

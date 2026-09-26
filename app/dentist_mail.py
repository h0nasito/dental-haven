"""Email dentists about their own appointments: approved/booked, rescheduled, cancelled.

Sending uses SMTP with Gmail app passwords. Each branch can send from its own Gmail; set these on
the server (e.g. Render → Environment), where <BRANCH> is the branch code in capitals
(MALOLOS, GUIGUINTO, BOCAUE, SJDM):
    MAIL_<BRANCH>_USERNAME   the branch Gmail address, e.g. dentalhavenmalolos@gmail.com
    MAIL_<BRANCH>_PASSWORD   that account's Gmail *app password*
A branch without its own account falls back to MAIL_USERNAME / MAIL_PASSWORD, if set.
Nothing is sent for a branch that has neither.
Optional: MAIL_FROM_NAME (default "Dental Haven <branch>"), MAIL_HOST (smtp.gmail.com), MAIL_PORT (587),
PUBLIC_BASE_URL (for the "open in Dental Haven" link).

The demo site never sends. Email text is never logged or stored: only who/when/status.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app, has_request_context, request

from .util import now, now_str, parse_dt

EVENTS = {
    "confirmed": ("New appointment", "You have a new appointment."),
    "rescheduled": ("Appointment rescheduled", "One of your appointments was rescheduled. The new schedule is below."),
    "cancelled": ("Appointment cancelled", "This appointment was cancelled. You don't need to see this patient at this time."),
    "reassigned": ("Appointment moved to another dentist",
                   "This appointment was moved to another dentist, so it's no longer on your schedule."),
}
STATUS_LABELS = {"pending": "Sending", "sent": "Sent", "failed": "Failed", "not_set_up": "Not sent (email not set up)",
                 "demo": "Not sent (demo site)", "skipped": "Not sent"}


def _env_key(slug: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in (slug or "").upper())


def config(branch_slug: str | None = None, branch_name: str = "") -> dict | None:
    """SMTP settings for a branch (its own Gmail, else the shared default). None if neither is set."""
    for prefix, label in ((f"MAIL_{_env_key(branch_slug)}_", branch_name), ("MAIL_", "")):
        if prefix == "MAIL__":
            continue
        user = os.environ.get(prefix + "USERNAME", "").strip()
        # Google shows app passwords in groups of four ("abcd efgh ..."); spaces aren't part of it.
        pw = os.environ.get(prefix + "PASSWORD", "").replace(" ", "")
        if user and pw:
            return {
                "host": os.environ.get("MAIL_HOST", "smtp.gmail.com").strip(),
                "port": int(os.environ.get("MAIL_PORT", "587") or 587),
                "username": user, "password": pw, "sender": user,
                "sender_name": os.environ.get("MAIL_FROM_NAME", f"Dental Haven {label}".strip()).strip(),
            }
    return None


def senders(conn) -> list[dict]:
    """Which sender each branch will use, for the settings page."""
    out = []
    for b in conn.all("SELECT slug, name FROM branches WHERE active = 1 ORDER BY sort_order"):
        c = config(b["slug"], b["name"])
        out.append({"branch": b["name"], "slug": b["slug"], "env": f"MAIL_{_env_key(b['slug'])}_USERNAME",
                    "sender": c["sender"] if c else None})
    return out


def state(conn=None) -> str:
    """'demo', 'off' (no sender configured at all) or 'on'."""
    if current_app.config.get("APP_ENV") == "demo":
        return "demo"
    if config():
        return "on"
    if conn is not None and any(s["sender"] for s in senders(conn)):
        return "on"
    pairs = (k[:-len("USERNAME")] for k in os.environ if k.startswith("MAIL_") and k.endswith("_USERNAME"))
    return "on" if any(os.environ.get(p + "USERNAME") and os.environ.get(p + "PASSWORD") for p in pairs) else "off"


def send_email(to: str, subject: str, body: str, c: dict | None = None) -> None:
    c = c or config()
    if not c:
        raise RuntimeError("Email is not set up")
    msg = EmailMessage()
    msg["From"] = formataddr((c["sender_name"], c["sender"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(c["host"], c["port"], timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(c["username"], c["password"])
        s.send_message(msg)


def _when(start, end=None) -> tuple[str, str]:
    day = start.strftime("%A, %B %d, %Y").replace(" 0", " ")
    t = start.strftime("%I:%M %p").lstrip("0")
    if end:
        t += " – " + end.strftime("%I:%M %p").lstrip("0")
    return day, t


def describe_slot(appt) -> str:
    """Short, patient-free description used as the 'previously' line of a reschedule."""
    start = parse_dt(appt["start_at"])
    return f"{start.strftime('%a, %b %d').replace(' 0', ' ')} · {start.strftime('%I:%M %p').lstrip('0')} · {appt['branch']}"


def _base_url() -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if not base and has_request_context():
        base = request.url_root
    return base.rstrip("/")


def compose(a, event: str, previous: str = "") -> tuple[str, str]:
    title, intro = EVENTS[event]
    start, end = parse_dt(a["start_at"]), parse_dt(a["end_at"])
    day, t = _when(start, end)
    short_day = start.strftime("%a, %b %d").replace(" 0", " ")
    # Subject has no patient name, so a phone's lock-screen preview doesn't show it.
    subject = f"{title}: {short_day} · {start.strftime('%I:%M %p').lstrip('0')} · {a['branch']}"
    lines = [f"Hi {a['dentist_name']},", "", intro, "",
             f"Day:        {day}", f"Time:       {t}",
             f"Branch:     {a['branch']}" + (f" ({a['branch_address']})" if a["branch_address"] else ""),
             f"Patient:    {a['first_name']} {a['last_name']}".rstrip(),
             f"Procedure:  {a['service']}"]
    if previous:
        lines.append(f"Previously: {previous}")
    base = _base_url()
    if base and event != "reassigned":
        lines += ["", f"Open in Dental Haven: {base}/staff/appointments/{a['id']}"]
    lines += ["", "—", "Automatic message from the Dental Haven clinic system. It contains patient information:",
              "please don't forward it. To stop these emails, ask the clinic admin."]
    return subject, "\n".join(lines)


def queue(conn, appointment_id: int, event: str, dentist_id: int | None, previous: str = "") -> int | None:
    if not dentist_id or event not in EVENTS:
        return None
    return conn.insert("dentist_emails", {"appointment_id": appointment_id, "user_id": dentist_id, "event": event,
                                          "previous": previous, "status": "pending", "created_at": now_str()})


def deliver(conn, ids) -> None:
    """Send queued emails. Never raises: a mail problem must not break booking."""
    mode = "demo" if current_app.config.get("APP_ENV") == "demo" else "live"
    for eid in [i for i in ids if i]:
        e = conn.one("SELECT * FROM dentist_emails WHERE id = ? AND status = 'pending'", (eid,))
        if not e:
            continue
        a = conn.one("SELECT a.*, p.first_name, p.last_name, s.name AS service, b.name AS branch, b.slug AS branch_slug, b.address AS branch_address, "
                     "u.name AS dentist_name, u.email AS dentist_email, u.active AS dentist_active, u.notify_email "
                     "FROM appointments a JOIN patients p ON p.id = a.patient_id JOIN services s ON s.id = a.service_id "
                     "JOIN branches b ON b.id = a.branch_id JOIN users u ON u.id = ? WHERE a.id = ?",
                     (e["user_id"], e["appointment_id"]))
        status, error = "sent", ""
        if not a:
            status, error = "skipped", "Appointment not found"
        elif not a["dentist_active"] or not a["notify_email"] or not a["dentist_email"]:
            status, error = "skipped", "Dentist's emails are turned off"
        elif parse_dt(a["end_at"]) < now():
            status, error = "skipped", "Appointment is in the past"
        elif mode == "demo":
            status = "demo"
        elif not config(a["branch_slug"], a["branch"]):
            status, error = "not_set_up", ""
        else:
            try:
                subject, body = compose(a, e["event"], e["previous"])
                send_email(a["dentist_email"], subject, body, config(a["branch_slug"], a["branch"]))
            except Exception as exc:  # noqa: BLE001 - report any SMTP/network failure, without message content
                status, error = "failed", f"{type(exc).__name__}: {str(exc)[:160]}"
                current_app.logger.warning("Dentist email %s failed: %s", eid, type(exc).__name__)
        conn.execute("UPDATE dentist_emails SET status = ?, error = ?, sent_at = ? WHERE id = ?",
                     (status, error, now_str() if status == "sent" else None, eid))


def notify(conn, appointment_id: int, event: str, dentist_id: int | None, previous: str = "") -> None:
    deliver(conn, [queue(conn, appointment_id, event, dentist_id, previous)])

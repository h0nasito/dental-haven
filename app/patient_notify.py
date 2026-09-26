"""Automatic messages to patients about their bookings: approved, declined, rescheduled, cancelled, and
day-before reminders.

Email uses the branch Gmail (same settings as dentist emails, see app/dentist_mail.py).
SMS uses Semaphore (semaphore.co) and stays OFF until these are set on the server:
    SEMAPHORE_API_KEY       the account's API key
    SEMAPHORE_SENDER_NAME   the approved sender name, e.g. DentalHaven
The SMS integration has not been verified with a real account yet.

Booking updates go to every patient who requested a booking (they answer the patient's own request),
unless the patient opted out of all messages. Reminders follow the patient's reminder consent.
The demo site never sends. Message text is never stored or logged.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from flask import current_app, has_request_context, request

from . import dentist_mail
from .util import now, now_str, parse_dt

SEMAPHORE_URL = "https://api.semaphore.co/api/v4/messages"
EVENT_LABELS = {"approved": "Booking approved", "declined": "Booking not available", "rescheduled": "Appointment moved",
                "cancelled": "Appointment cancelled", "reminder": "Reminder"}
STATUS_LABELS = {"sent": "Sent", "failed": "Failed", "not_set_up": "Not sent (not set up)", "demo": "Not sent (demo site)",
                 "skipped": "Not sent"}


# ---------------------------------------------------------------- helpers
def _demo() -> bool:
    return current_app.config.get("APP_ENV") == "demo"


def sms_config():
    key = os.environ.get("SEMAPHORE_API_KEY", "").strip()
    return {"key": key, "sender": os.environ.get("SEMAPHORE_SENDER_NAME", "").strip()} if key else None


def mask_email(e: str) -> str:
    name, _, dom = (e or "").partition("@")
    return (name[:1] + "***@" + dom) if dom else ""


def mask_phone(p: str) -> str:
    d = "".join(c for c in (p or "") if c.isdigit())
    return (d[:4] + "•••" + d[-3:]) if len(d) >= 7 else ""


def ph_mobile(p: str) -> str | None:
    """Normalise a Philippine mobile number to 09XXXXXXXXX (what Semaphore expects), or None."""
    d = "".join(c for c in (p or "") if c.isdigit())
    if d.startswith("63") and len(d) == 12:
        d = "0" + d[2:]
    if len(d) == 10 and d.startswith("9"):
        d = "0" + d
    return d if len(d) == 11 and d.startswith("09") else None


def _base_url() -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if not base and has_request_context():
        base = request.url_root
    return base.rstrip("/")


def _when(start):
    return start.strftime("%A, %B %d, %Y").replace(" 0", " "), start.strftime("%I:%M %p").lstrip("0")


def _short_when(start):
    return start.strftime("%a %b %d").replace(" 0", " ") + ", " + start.strftime("%I:%M %p").lstrip("0")


def _first_phone(phone_field: str) -> str:
    return (phone_field or "").split("/")[0].strip()


def send_sms(number: str, message: str, cfg: dict) -> None:
    data = {"apikey": cfg["key"], "number": number, "message": message}
    if cfg.get("sender"):
        data["sendername"] = cfg["sender"]
    req = urllib.request.Request(SEMAPHORE_URL, data=urllib.parse.urlencode(data).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed https URL
        body = resp.read().decode("utf-8", "replace")
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("error") or (isinstance(parsed, list) and parsed and parsed[0].get("status") == "Failed"):
        raise RuntimeError("SMS provider refused the message")


# ---------------------------------------------------------------- message text
def compose(event: str, ctx: dict) -> tuple[str, str, str]:
    """Returns (email subject, email body, sms text)."""
    branch = ctx["branch"]
    phone = ctx["branch_phone"]
    first = ctx["first_name"] or "there"
    head = f"Hi {first},"
    lines, sms = [], ""
    if event in ("approved", "rescheduled", "reminder"):
        day, t = _when(ctx["start"])
        details = [f"Day:      {day}", f"Time:     {t}", f"Branch:   Dental Haven {branch}" + (f", {ctx['address']}" if ctx["address"] else ""),
                   f"Service:  {ctx['service']}"] + ([f"Dentist:  {ctx['dentist']}"] if ctx.get("dentist") else [])
        if event == "approved":
            subject = f"Your Dental Haven appointment is confirmed: {_short_when(ctx['start'])}"
            lines = [head, "", "Good news! Your appointment request has been approved.", ""] + details
            sms = f"Dental Haven: Hi {first}, your appointment is confirmed for {_short_when(ctx['start'])} at our {branch} branch."
        elif event == "rescheduled":
            subject = f"Your Dental Haven appointment has moved: {_short_when(ctx['start'])}"
            lines = [head, "", "Your appointment has been moved. Here are the new details:", ""] + details
            sms = f"Dental Haven: Hi {first}, your appointment has moved to {_short_when(ctx['start'])} at our {branch} branch."
        else:
            subject = f"Reminder: your Dental Haven appointment {_short_when(ctx['start'])}"
            lines = [head, "", "This is a friendly reminder of your appointment:", ""] + details
            sms = f"Dental Haven: Hi {first}, reminder of your appointment on {_short_when(ctx['start'])} at our {branch} branch."
        lines += ["", f"Need to change it? Call {phone}." if phone else "Need to change it? Please contact the branch."]
        sms += f" To change, call {phone}." if phone else ""
    elif event == "cancelled":
        subject = "Your Dental Haven appointment has been cancelled"
        lines = [head, "", f"Your appointment on {_short_when(ctx['start'])} at Dental Haven {branch} has been cancelled.",
                 "", "We'd be glad to find you a new time" + (f": call {phone}" if phone else "") + (f" or book online at {ctx['book_url']}" if ctx.get("book_url") else "") + "."]
        sms = f"Dental Haven: Hi {first}, your appointment on {_short_when(ctx['start'])} was cancelled. To rebook, call {phone}." if phone else \
              f"Dental Haven: Hi {first}, your appointment on {_short_when(ctx['start'])} was cancelled."
    elif event == "declined":
        subject = "About your Dental Haven appointment request"
        lines = [head, "", f"Thank you for your request. Unfortunately we can't confirm {_short_when(ctx['start'])} at our {branch} branch.",
                 "", "Please choose another time" + (f" at {ctx['book_url']}" if ctx.get("book_url") else "") + (f", or call us at {phone}" if phone else "") + ". We'd love to see you."]
        sms = f"Dental Haven: Hi {first}, sorry, we can't confirm your requested time ({_short_when(ctx['start'])}). Please pick another time" + (f" or call {phone}." if phone else ".")
    else:
        raise ValueError(event)
    lines += ["", "— Dental Haven", "Happiest your teeth will ever be"]
    return subject, "\n".join(lines), sms[:300]


# ---------------------------------------------------------------- sending
def _log(conn, event, channel, status, *, patient_id=None, appointment_id=None, booking_request_id=None, branch_id=None,
         recipient="", error=""):
    conn.insert("patient_messages", {"event": event, "channel": channel, "patient_id": patient_id, "appointment_id": appointment_id,
                                     "booking_request_id": booking_request_id, "branch_id": branch_id, "recipient_masked": recipient,
                                     "status": status, "error": error[:200], "created_at": now_str(),
                                     "sent_at": now_str() if status == "sent" else None})


def _deliver(conn, event, ctx, *, email, phone, ids, allow_email=True, allow_sms=True) -> int:
    """Send by email and/or SMS. Returns how many messages were actually sent."""
    subject, body, sms = compose(event, ctx)
    sent = 0
    if email and allow_email:
        rec = mask_email(email)
        cfg = dentist_mail.config(ctx["branch_slug"], ctx["branch"])
        if _demo():
            _log(conn, event, "email", "demo", recipient=rec, **ids)
        elif not cfg:
            _log(conn, event, "email", "not_set_up", recipient=rec, **ids)
        else:
            try:
                dentist_mail.send_email(email, subject, body, cfg)
                _log(conn, event, "email", "sent", recipient=rec, **ids)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                _log(conn, event, "email", "failed", recipient=rec, error=type(exc).__name__, **ids)
    number = ph_mobile(phone) if phone else None
    if number and allow_sms:
        rec = mask_phone(number)
        cfg = sms_config()
        if _demo():
            _log(conn, event, "sms", "demo", recipient=rec, **ids)
        elif not cfg:
            _log(conn, event, "sms", "not_set_up", recipient=rec, **ids)
        else:
            try:
                send_sms(number, sms, cfg)
                _log(conn, event, "sms", "sent", recipient=rec, **ids)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                _log(conn, event, "sms", "failed", recipient=rec, error=type(exc).__name__, **ids)
    return sent


def _appt_ctx(conn, appt_id):
    a = conn.one("SELECT a.*, p.first_name, p.email, p.phone, p.opt_out_all, p.contact_sms, p.contact_email, s.name AS service, "
                 "b.name AS branch, b.slug AS branch_slug, b.address, b.phone AS branch_phone, u.name AS dentist "
                 "FROM appointments a JOIN patients p ON p.id = a.patient_id JOIN services s ON s.id = a.service_id "
                 "JOIN branches b ON b.id = a.branch_id LEFT JOIN users u ON u.id = a.dentist_id WHERE a.id = ?", (appt_id,))
    if not a:
        return None, None
    ctx = {"first_name": a["first_name"], "branch": a["branch"].split(" (")[0], "branch_slug": a["branch_slug"], "address": a["address"],
           "branch_phone": _first_phone(a["branch_phone"]), "service": a["service"], "dentist": a["dentist"],
           "start": parse_dt(a["start_at"]), "book_url": (_base_url() + "/book") if _base_url() else ""}
    return a, ctx


def notify_appointment(conn, appt_id: int, event: str, booking_request_id: int | None = None, fallback_email: str = "") -> None:
    """approved / rescheduled / cancelled. Never raises."""
    try:
        a, ctx = _appt_ctx(conn, appt_id)
        if not a or a["opt_out_all"] or parse_dt(a["end_at"]) < now():
            return
        _deliver(conn, event, ctx, email=a["email"] or fallback_email, phone=a["phone"],
                 ids={"patient_id": a["patient_id"], "appointment_id": appt_id, "booking_request_id": booking_request_id,
                      "branch_id": a["branch_id"]})
    except Exception:  # noqa: BLE001 - messaging must never break the clinic workflow
        current_app.logger.exception("Patient notification failed (appointment %s)", appt_id)


def notify_declined(conn, req) -> None:
    try:
        b = conn.one("SELECT * FROM branches WHERE id = ?", (req["branch_id"],))
        ctx = {"first_name": (req["full_name"] or "").split(" ")[0], "branch": b["name"].split(" (")[0], "branch_slug": b["slug"],
               "address": b["address"], "branch_phone": _first_phone(b["phone"]), "start": parse_dt(req["preferred_start"]),
               "book_url": (_base_url() + "/book") if _base_url() else ""}
        _deliver(conn, "declined", ctx, email=req["email"], phone=req["phone"],
                 ids={"booking_request_id": req["id"], "branch_id": req["branch_id"]})
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Patient notification failed (request %s)", req["id"])


def automatic_channels_available(branch_slug: str, branch_name: str) -> bool:
    return not _demo() and (bool(dentist_mail.config(branch_slug, branch_name)) or bool(sms_config()))


def send_due_reminders(conn) -> int:
    """Send reminders whose time has come, by email/SMS, following each patient's reminder consent.
    Reminders that can't go out automatically stay in the manual reminder outbox.
    Safe to run from several workers: each reminder is claimed before sending."""
    if _demo():
        return 0
    rows = conn.all("SELECT r.id, r.status, r.appointment_id, b.slug, b.name FROM reminders r "
                    "JOIN appointments a ON a.id = r.appointment_id JOIN patients p ON p.id = a.patient_id "
                    "JOIN branches b ON b.id = a.branch_id WHERE r.scheduled_for <= ? AND a.status = 'confirmed' AND a.start_at > ? "
                    "AND r.appointment_id IS NOT NULL AND p.opt_out_all = 0 AND (r.status = 'pending' OR "
                    "(r.status = 'skipped_no_consent' AND p.contact_email = 1 AND p.email != '')) "
                    "ORDER BY r.scheduled_for LIMIT 50", (now_str(), now_str()))
    done = 0
    for r in rows:
        if not automatic_channels_available(r["slug"], r["name"]):
            continue
        cur = conn.execute("UPDATE reminders SET status = 'sent_provider', provider = 'auto', result_note = 'Sending' "
                           "WHERE id = ? AND status = ?", (r["id"], r["status"]))
        if cur.rowcount == 0:
            continue  # another worker took it
        a, ctx = _appt_ctx(conn, r["appointment_id"])
        sent = _deliver(conn, "reminder", ctx, email=a["email"], phone=a["phone"],
                        ids={"patient_id": a["patient_id"], "appointment_id": a["id"], "branch_id": a["branch_id"]},
                        allow_email=bool(a["contact_email"]), allow_sms=bool(a["contact_sms"])) if a else 0
        if sent:
            conn.execute("UPDATE reminders SET result_note = 'Sent automatically', sent_at = ? WHERE id = ?", (now_str(), r["id"]))
            done += 1
        else:
            note = "Automatic sending failed: please send it manually" if r["status"] == "pending" else ""
            conn.execute("UPDATE reminders SET status = ?, provider = 'manual', result_note = ? WHERE id = ?",
                         (r["status"], note, r["id"]))
    return done


def start_worker(app, every_seconds: int = 300) -> None:
    """Background loop in each web worker that sends due reminders. Only on the live site."""
    import threading
    import time

    if app.config.get("APP_ENV") != "production" or app.config.get("TESTING") or os.environ.get("AUTO_REMINDERS", "on") == "off":
        return

    def loop():
        time.sleep(30)
        while True:
            try:
                with app.app_context():
                    from .db import get_db
                    n = send_due_reminders(get_db())
                    if n:
                        app.logger.info("Sent %s appointment reminder(s)", n)
            except Exception:  # noqa: BLE001
                app.logger.exception("Reminder worker error")
            time.sleep(every_seconds)

    threading.Thread(target=loop, name="reminder-worker", daemon=True).start()

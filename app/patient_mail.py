"""Emails to patients: automatic birthday greetings, and announcement / promotion blasts.

Who gets what (the clinic's choice, in line with the Data Privacy Act):
- Birthday greeting: patients with privacy consent who haven't opted out of emails. The birthday promo paragraph is added
  only for patients who accept promotions.
- Announcement: patients with privacy consent who haven't opted out of emails.
- Promotion: only patients who accept promotions ("OK to receive promotions/newsletters").
Every email has an unsubscribe link. Deleted patients, patients without an email, and "opted out of everything" are skipped.

Sending: emails wait in a queue (email_outbox) and are sent a few at a time by the background worker, through the branch
Gmail accounts (see dentist_mail). Each Gmail account sends at most `mail.daily_limit` emails a day (Gmail allows about
500), so a big blast is spread over several days instead of getting the account blocked.
Nothing is sent on the demo site. Logs never contain email text or addresses.
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import date, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

from . import settings
from .dentist_mail import _base_url, config
from .util import now, now_str, today

KINDS = {"announcement": "Announcement", "promotion": "Promotion", "birthday": "Birthday greeting"}
DEFAULT_DAILY_LIMIT = 400
BATCH = 40  # emails per worker run (every 5 minutes)

DEFAULT_BIRTHDAY_SUBJECT = "Happy birthday, {first_name}! 🎂"
DEFAULT_BIRTHDAY_BODY = ("Hi {first_name},\n\nHappy birthday from all of us at Dental Haven! We wish you a wonderful year ahead "
                         "and many reasons to smile.\n\nSee you at your next visit!")


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------

def audience_sql(kind: str, branch_id: int | None = None) -> tuple[str, list]:
    """WHERE clause (on patients p) for who may receive this kind of email."""
    where = ["p.active = 1", "p.email LIKE '%_@_%._%'", "p.opt_out_all = 0"]
    if kind == "promotion":
        where.append("p.consent_marketing = 1")
    else:
        where += ["p.consent_privacy = 1", "p.news_opt_out = 0"]
    args: list = []
    if branch_id:
        where.append("p.preferred_branch_id = ?")
        args.append(branch_id)
    return " AND ".join(where), args


def audience_count(conn, kind: str, branch_id: int | None = None) -> int:
    where, args = audience_sql(kind, branch_id)
    return conn.scalar(f"SELECT COUNT(*) FROM patients p WHERE {where}", args) or 0


# ---------------------------------------------------------------------------
# Unsubscribe links
# ---------------------------------------------------------------------------

def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="patient-email-unsubscribe")


def unsubscribe_token(patient_id: int) -> str:
    return _serializer().dumps({"p": patient_id})


def read_unsubscribe_token(token: str) -> int | None:
    try:
        data = _serializer().loads(token)
    except BadSignature:
        return None
    return data.get("p") if isinstance(data, dict) else None


def unsubscribe_url(patient_id: int) -> str:
    return f"{_base_url()}/unsubscribe/{unsubscribe_token(patient_id)}"


# ---------------------------------------------------------------------------
# Composing
# ---------------------------------------------------------------------------

def personalise(text: str, patient) -> str:
    first = (patient["first_name"] or "").strip().title() or "there"
    return (text or "").replace("{first_name}", first).replace("{FIRST_NAME}", first)


def footer(kind: str, patient_id: int) -> str:
    why = {"promotion": "you agreed to receive promotions from Dental Haven",
           "announcement": "you are a Dental Haven patient",
           "birthday": "you are a Dental Haven patient"}[kind]
    return (f"\n\n—\nDental Haven\nYou're receiving this email because {why}.\n"
            f"To stop these emails: {unsubscribe_url(patient_id)}")


def compose(kind: str, subject: str, body: str, patient) -> tuple[str, str]:
    return personalise(subject, patient)[:200], personalise(body, patient) + footer(kind, patient["id"])


def birthday_message(conn, patient) -> tuple[str, str]:
    subject = settings.get("birthday.subject", conn) or DEFAULT_BIRTHDAY_SUBJECT
    body = settings.get("birthday.body", conn) or DEFAULT_BIRTHDAY_BODY
    promo = (settings.get("birthday.promo", conn) or "").strip()
    if promo and patient["consent_marketing"]:
        body = f"{body}\n\n{promo}"
    return compose("birthday", subject, body, patient)


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------

def queue_campaign(conn, campaign) -> int:
    """Put one email per eligible patient into the queue. Safe to call twice (one email per patient per campaign)."""
    where, args = audience_sql(campaign["kind"], campaign["branch_id"])
    n = 0
    ts = now_str()
    for p in conn.all(f"SELECT p.id, p.first_name, p.email FROM patients p WHERE {where} ORDER BY p.id", args):
        subject, body = compose(campaign["kind"], campaign["subject"], campaign["body"], p)
        cur = conn.execute("INSERT OR IGNORE INTO email_outbox (kind, campaign_id, patient_id, to_email, subject, body, dedupe_key, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (campaign["kind"], campaign["id"], p["id"], p["email"].strip(), subject, body, f"c{campaign['id']}-p{p['id']}", ts))
        n += cur.rowcount or 0
    return n


def _birthday_today_sql(day: date) -> tuple[str, list]:
    md = [day.strftime("%m-%d")]
    # People born on 29 February are greeted on 28 February in other years.
    leap = day.year % 4 == 0 and (day.year % 100 != 0 or day.year % 400 == 0)
    if day.month == 2 and day.day == 28 and not leap:
        md.append("02-29")
    return f"substr(p.birth_date, 6, 5) IN ({','.join('?' * len(md))})", md


def queue_birthdays(conn, day: date | None = None) -> int:
    """Queue today's birthday greetings (once a day; only when turned on)."""
    if not settings.get("birthday.enabled", conn):
        return 0
    day = day or today()
    if settings.get("birthday.last_run", conn) == day.isoformat():
        return 0
    if now().hour < 8 and day == today():
        return 0  # send from 8 AM
    settings.put("birthday.last_run", day.isoformat(), None, conn)
    where, args = audience_sql("birthday")
    bsql, bargs = _birthday_today_sql(day)
    n = 0
    for p in conn.all(f"SELECT p.* FROM patients p WHERE {where} AND {bsql}", [*args, *bargs]):
        subject, body = birthday_message(conn, p)
        cur = conn.execute("INSERT OR IGNORE INTO email_outbox (kind, patient_id, to_email, subject, body, dedupe_key, created_at) "
                           "VALUES ('birthday', ?, ?, ?, ?, ?, ?)",
                           (p["id"], p["email"].strip(), subject, body, f"bday-{p['id']}-{day.year}", now_str()))
        n += cur.rowcount or 0
    return n


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def sender_configs(conn) -> list[dict]:
    """Distinct Gmail accounts available (one per branch that has its own, plus the shared default)."""
    seen, out = set(), []
    for b in conn.all("SELECT slug, name FROM branches WHERE active = 1 ORDER BY sort_order"):
        c = config(b["slug"], b["name"])
        if c and c["sender"] not in seen:
            seen.add(c["sender"])
            out.append(c)
    c = config()
    if c and c["sender"] not in seen:
        out.append(c)
    return out


def daily_limit(conn) -> int:
    import os
    saved = settings.get("mail.daily_limit", conn)
    if saved:
        return int(saved)
    # Brevo's free plan allows 300 emails a day in total; keep a little room for appointment emails.
    return 280 if os.environ.get("BREVO_API_KEY", "").strip() else DEFAULT_DAILY_LIMIT


def sent_today(conn, sender: str) -> int:
    start = today().isoformat()
    return conn.scalar("SELECT COUNT(*) FROM email_outbox WHERE sender = ? AND status IN ('sent','sending') AND claimed_at >= ?",
                       (sender, start)) or 0


def smtp_send(c: dict, to: str, subject: str, body: str, unsubscribe: str = "") -> None:
    if c.get("transport") == "brevo":
        from .dentist_mail import brevo_send
        brevo_send(c, to, subject, body, {"List-Unsubscribe": f"<{unsubscribe}>"} if unsubscribe else None)
        return
    msg = EmailMessage()
    msg["From"] = formataddr((c["sender_name"] or "Dental Haven", c["sender"]))
    msg["To"] = to
    msg["Subject"] = subject
    if unsubscribe:
        msg["List-Unsubscribe"] = f"<{unsubscribe}>"
    msg.set_content(body)
    with smtplib.SMTP(c["host"], c["port"], timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(c["username"], c["password"])
        s.send_message(msg)


def send_queued(conn, batch: int = BATCH, sender_fn=None) -> int:
    """Send up to `batch` queued emails within each account's daily limit. Returns how many were sent."""
    if current_app.config.get("APP_ENV") == "demo":
        return 0
    sender_fn = sender_fn or smtp_send
    configs = sender_configs(conn)
    if not configs:
        return 0
    limit = daily_limit(conn)
    if configs[0].get("transport") == "brevo":
        # One Brevo account sends for every branch, so the daily limit counts all senders together.
        def limit_for(_sender):
            return limit - (conn.scalar("SELECT COUNT(*) FROM email_outbox WHERE status IN ('sent','sending') AND claimed_at >= ?",
                                        (today().isoformat(),)) or 0)
    else:
        limit_for = lambda sender: limit - sent_today(conn, sender)  # noqa: E731
    # Rows left in "sending" for over an hour (e.g. the server restarted mid-send) go back to the queue.
    conn.execute("UPDATE email_outbox SET status = 'pending' WHERE status = 'sending' AND claimed_at < ?",
                 ((now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),))
    sent = 0
    for c in configs:
        room = min(batch - sent, limit_for(c["sender"]))
        if room <= 0:
            continue
        rows = conn.all("SELECT id FROM email_outbox WHERE status = 'pending' ORDER BY CASE kind WHEN 'birthday' THEN 0 ELSE 1 END, id LIMIT ?",
                        (room,))
        for r in rows:
            # Claim the row first, so two web workers never send the same email.
            cur = conn.execute("UPDATE email_outbox SET status = 'sending', sender = ?, claimed_at = ?, attempts = attempts + 1 "
                               "WHERE id = ? AND status = 'pending'", (c["sender"], now_str(), r["id"]))
            if not cur.rowcount:
                continue
            e = conn.one("SELECT o.*, p.active, p.opt_out_all, p.consent_marketing, p.news_opt_out FROM email_outbox o "
                         "JOIN patients p ON p.id = o.patient_id WHERE o.id = ?", (r["id"],))
            # Re-check consent at send time: the patient may have unsubscribed since the email was queued.
            still_ok = e["active"] and not e["opt_out_all"] and (
                e["consent_marketing"] if e["kind"] == "promotion" else not e["news_opt_out"])
            if not still_ok:
                conn.execute("UPDATE email_outbox SET status = 'cancelled', error = 'Unsubscribed or deleted before sending' WHERE id = ?",
                             (e["id"],))
                continue
            try:
                sender_fn(c, e["to_email"], e["subject"], e["body"], unsubscribe_url(e["patient_id"]))
            except Exception as exc:  # noqa: BLE001 - any SMTP / network problem; no email content in the log
                final = e["attempts"] >= 3
                conn.execute("UPDATE email_outbox SET status = ?, error = ? WHERE id = ?",
                             ("failed" if final else "pending", type(exc).__name__, e["id"]))
                current_app.logger.warning("Patient email %s not sent: %s", e["id"], type(exc).__name__)
                continue
            conn.execute("UPDATE email_outbox SET status = 'sent', sent_at = ?, error = '' WHERE id = ?", (now_str(), e["id"]))
            sent += 1
    # Campaigns with nothing left to send are done.
    conn.execute("UPDATE email_campaigns SET status = 'done', updated_at = ? WHERE status = 'queued' AND NOT EXISTS "
                 "(SELECT 1 FROM email_outbox o WHERE o.campaign_id = email_campaigns.id AND o.status IN ('pending','sending'))",
                 (now_str(),))
    return sent


def run(conn) -> int:
    """One worker pass: queue today's birthdays, then send what the daily limits allow."""
    queue_birthdays(conn)
    return send_queued(conn)


def stats(conn, campaign_id: int | None = None) -> dict:
    where, args = ("campaign_id = ?", [campaign_id]) if campaign_id else ("1 = 1", [])
    out = {s: 0 for s in ("pending", "sending", "sent", "failed", "cancelled")}
    for r in conn.all(f"SELECT status, COUNT(*) AS n FROM email_outbox WHERE {where} GROUP BY status", args):
        out[r["status"]] = r["n"]
    return out

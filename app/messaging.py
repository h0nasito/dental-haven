"""Messaging: template rendering, reminder scheduling and a provider interface.

No provider sends real messages in this build. The only provider is ManualProvider:
staff preview the rendered text, send it themselves (clinic phone / Messenger / email),
then record the result. To add SMS/email later, implement MessagingProvider and register it
in PROVIDERS once credentials, consent rules and templates are approved (docs/INTEGRATIONS.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from .util import fmt_dt, hm_to_min, now, now_str, parse_dt

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
ALLOWED_PLACEHOLDERS = {
    "first_name": "Patient or lead first name",
    "clinic": "Clinic name",
    "branch": "Branch name",
    "branch_phone": "Branch contact number",
    "date": "Appointment date",
    "time": "Appointment time",
    "service": "Service name",
    "dentist": "Dentist name",
}
CHANNELS = {"sms": "SMS", "email": "Email", "messenger": "Messenger", "call": "Phone call"}


def render(body: str, values: dict) -> str:
    """Fill {{placeholders}}. Unknown/missing placeholders become blanks, never raw data dumps."""
    def sub(m):
        key = m.group(1)
        if key not in ALLOWED_PLACEHOLDERS:
            return ""
        return str(values.get(key) or "")
    return PLACEHOLDER_RE.sub(sub, body or "").strip()


def appointment_values(conn, appt_id: int) -> dict:
    a = conn.one(
        "SELECT a.start_at, p.first_name, b.name AS branch, b.phone AS branch_phone, s.name AS service, u.name AS dentist "
        "FROM appointments a JOIN patients p ON p.id = a.patient_id JOIN branches b ON b.id = a.branch_id "
        "JOIN services s ON s.id = a.service_id LEFT JOIN users u ON u.id = a.dentist_id WHERE a.id = ?", (appt_id,))
    if not a:
        return {}
    start = parse_dt(a["start_at"])
    return {
        "first_name": a["first_name"], "clinic": "Dental Haven", "branch": a["branch"], "branch_phone": a["branch_phone"],
        "date": start.strftime("%A, %B %d").replace(" 0", " "), "time": start.strftime("%I:%M %p").lstrip("0"),
        "service": a["service"], "dentist": a["dentist"] or "your dentist",
    }


def channel_allowed(patient, channel: str) -> tuple[bool, str]:
    """Respect communication preferences and opt-outs."""
    if patient is None:
        return False, "skipped_no_consent"
    if patient["opt_out_all"]:
        return False, "skipped_opt_out"
    if channel == "sms" and not (patient["contact_sms"] and patient["phone"]):
        return False, "skipped_no_consent"
    if channel == "email" and not (patient["contact_email"] and patient["email"]):
        return False, "skipped_no_consent"
    if channel == "messenger" and not patient["contact_messenger"]:
        return False, "skipped_no_consent"
    return True, "pending"


def adjust_for_quiet_hours(when, quiet_start: str, quiet_end: str):
    """Move a send time out of quiet hours (e.g. 20:00–08:00) to the next allowed morning."""
    m = when.hour * 60 + when.minute
    qs, qe = hm_to_min(quiet_start), hm_to_min(quiet_end)
    in_quiet = (m >= qs or m < qe) if qs > qe else (qs <= m < qe)
    if not in_quiet:
        return when
    target = when.replace(hour=qe // 60, minute=qe % 60, second=0)
    if m >= qs and qs > qe:
        target += timedelta(days=1)
    return target


def schedule_appointment_reminders(conn, appt_id: int):
    """Create pending reminder rows from active appointment rules. Idempotent per (appointment, rule)."""
    from . import settings
    a = conn.one("SELECT * FROM appointments WHERE id = ?", (appt_id,))
    if not a or a["status"] not in ("confirmed",):
        return 0
    patient = conn.one("SELECT * FROM patients WHERE id = ?", (a["patient_id"],))
    values = appointment_values(conn, appt_id)
    qs = settings.get("messaging.quiet_start", conn) or "20:00"
    qe = settings.get("messaging.quiet_end", conn) or "08:00"
    created = 0
    for rule in conn.all("SELECT r.*, t.body FROM reminder_rules r JOIN message_templates t ON t.id = r.template_id "
                         "WHERE r.purpose = 'appointment' AND r.active = 1 AND t.active = 1"):
        if conn.one("SELECT id FROM reminders WHERE appointment_id = ? AND rule_id = ?", (appt_id, rule["id"])):
            continue
        when = parse_dt(a["start_at"]) + timedelta(minutes=rule["offset_minutes"])
        when = adjust_for_quiet_hours(when, qs, qe)
        if when >= parse_dt(a["start_at"]):
            when = parse_dt(a["start_at"]) - timedelta(hours=2)
        if when < now():
            continue  # too late for this reminder
        ok, status = channel_allowed(patient, rule["channel"])
        conn.insert("reminders", {
            "patient_id": a["patient_id"], "appointment_id": appt_id, "rule_id": rule["id"], "branch_id": a["branch_id"],
            "channel": rule["channel"], "template_id": rule["template_id"], "scheduled_for": fmt_dt(when),
            "status": status, "rendered_body": render(rule["body"], values) if ok else "",
            "provider": "manual", "created_at": now_str(),
        })
        created += 1
    return created


def cancel_appointment_reminders(conn, appt_id: int, note: str, regenerate: bool = False):
    """Cancel unsent reminders. On reschedule (regenerate=True) unsent rows are removed so fresh ones
    can be created for the new time; on cancellation they are kept as 'cancelled' for the record."""
    if regenerate:
        conn.execute("DELETE FROM reminders WHERE appointment_id = ? AND status IN ('pending','skipped_opt_out','skipped_no_consent')",
                     (appt_id,))
    else:
        conn.execute("UPDATE reminders SET status = 'cancelled', result_note = ? WHERE appointment_id = ? AND status = 'pending'",
                     (note, appt_id))


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

@dataclass
class SendResult:
    ok: bool
    status: str       # 'sent_manual' | 'sent_provider' | 'failed'
    note: str = ""


class MessagingProvider:
    name = "base"
    sends_automatically = False

    def send(self, channel: str, to: str, body: str) -> SendResult:  # pragma: no cover - interface
        raise NotImplementedError


class ManualProvider(MessagingProvider):
    """Staff send the message themselves and record the outcome. Nothing leaves the system."""
    name = "manual"
    sends_automatically = False

    def send(self, channel: str, to: str, body: str) -> SendResult:
        return SendResult(ok=True, status="sent_manual", note="Sent manually by staff")


PROVIDERS = {"manual": ManualProvider}


def get_provider(name: str) -> MessagingProvider:
    return PROVIDERS.get(name, ManualProvider)()

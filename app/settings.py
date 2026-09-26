"""Configurable settings with safe defaults. Values are JSON in the settings table."""
from __future__ import annotations

import json

from .db import get_db
from .util import now_str

DEFAULTS: dict[str, object] = {
    # Booking
    "booking.auto_confirm": False,          # online requests stay pending until staff confirm
    "booking.min_notice_hours": 12,
    "booking.max_days_ahead": 60,
    "booking.slot_step_min": 30,
    # Invoicing (no tax assumptions until the clinic confirms)
    "invoice.number_format": "{prefix}-{year}-{seq:05d}",
    "invoice.tax_enabled": False,
    "invoice.tax_label": "Tax",
    "invoice.tax_rate_bp": 0,               # basis points, e.g. 1200 = 12%
    "invoice.tax_inclusive": True,
    # Messaging
    "messaging.provider": "manual",         # only 'manual' is implemented; no automatic sending
    "messaging.quiet_start": "20:00",
    "messaging.quiet_end": "08:00",
    # Payroll
    "payroll.rules_confirmed": False,       # estimates are labelled unconfirmed until this is true
    "payroll.standard_day_minutes": 480,
    "payroll.grace_minutes": 0,
    # Privacy
    "privacy.retention_note": "Retention period to be confirmed by the clinic (see docs/PRIVACY_CHECKLIST.md).",
}

LABELS = {
    "booking.auto_confirm": "Automatically confirm online booking requests when the slot is free",
    "booking.min_notice_hours": "Minimum notice for online requests (hours)",
    "booking.max_days_ahead": "How far ahead patients can request (days)",
    "booking.slot_step_min": "Online slot step (minutes)",
    "invoice.number_format": "Invoice number format",
    "invoice.tax_enabled": "Apply tax on invoices",
    "invoice.tax_label": "Tax label",
    "invoice.tax_rate_bp": "Tax rate (basis points, 1200 = 12%)",
    "invoice.tax_inclusive": "Prices already include tax",
    "messaging.provider": "Messaging provider",
    "messaging.quiet_start": "Quiet hours start",
    "messaging.quiet_end": "Quiet hours end",
    "payroll.rules_confirmed": "Clinic pay rules confirmed and configured",
    "payroll.standard_day_minutes": "Standard working day (minutes)",
    "payroll.grace_minutes": "Late grace period (minutes)",
    "privacy.retention_note": "Record retention note",
}


def get(key: str, conn=None):
    conn = conn or get_db()
    row = conn.one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is None:
        return DEFAULTS.get(key)
    try:
        return json.loads(row["value"])
    except ValueError:
        return DEFAULTS.get(key)


def all_settings(conn=None) -> dict:
    conn = conn or get_db()
    values = dict(DEFAULTS)
    for row in conn.all("SELECT key, value FROM settings"):
        try:
            values[row["key"]] = json.loads(row["value"])
        except ValueError:
            pass
    return values


def put(key: str, value, user_id=None, conn=None):
    conn = conn or get_db()
    payload = json.dumps(value)
    if conn.one("SELECT key FROM settings WHERE key = ?", (key,)):
        conn.execute("UPDATE settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = ?",
                     (payload, now_str(), user_id, key))
    else:
        conn.execute("INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?)",
                     (key, payload, now_str(), user_id))

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
    "payroll.staff_start_time": "08:00",      # staff are late from 08:01 (dentists: from the branch opening time)
    "payroll.staff_end_time": "17:00",        # time after this is overtime (only for employees eligible for overtime)
    "payroll.short_lunch_minutes": 30,
    "payroll.ot_block_minutes": 30,           # overtime after 5 PM counts in whole blocks: under 30 min = 0, 45 min = 30        # extra overtime when a staff member took a 30-minute lunch instead of 1 hour
    "payroll.late_peso_per_minute": 1,        # ₱ deducted per late minute (clinic rule: 1 minute = ₱1)
    "payroll.late_applies_dentists": False,
    "payroll.pay_unworked_regular_holiday": True,
    # 'payment': the cashier records the dentist's commission on each payment (counted on the payment date);
    # 'procedure': commission is counted from bill lines on the date the procedure was done.
    "payroll.dentist_commission_basis": "payment",
    # Laboratory: trial fitting agreement signed by the patient and the dentist ({case_type}, {teeth}, {shade} are filled in).
    # The clinic should review this wording.
    "lab.fitting_agreement": ("Case: {case_type} · Teeth: {teeth} · Shade: {shade}\n\n"
                              "Today I tried in my {case_type} with my dentist. We checked the fit, shape, color and bite together, "
                              "and the dentist explained the result to me.\n\n"
                              "By signing, the dentist and I agree that the laboratory may proceed with the final processing of this "
                              "case as fitted today, including the changes written on this form (if any).\n\n"
                              "I understand that changes I ask for after signing may need extra time, and possibly an additional fee, "
                              "which my dentist will discuss with me before any work is done."),
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
    "payroll.staff_start_time": "Staff start time (late from the next minute), HH:MM",
    "payroll.staff_end_time": "Staff end time (overtime after this), HH:MM",
    "payroll.short_lunch_minutes": "Overtime added for a short lunch (minutes)",
    "payroll.ot_block_minutes": "Overtime counts in blocks of (minutes): less than one block = none, the rest is rounded down",
    "payroll.late_peso_per_minute": "Late deduction per minute (₱)",
    "payroll.late_applies_dentists": "Also deduct lates from dentists",
    "payroll.pay_unworked_regular_holiday": "Pay 1 day for a regular holiday not worked (staff on daily rate)",
    "payroll.dentist_commission_basis": "Dentist commission is counted",
    "lab.fitting_agreement": "Trial fitting agreement (patient and dentist sign it on the lab case)",
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

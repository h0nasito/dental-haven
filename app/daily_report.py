"""Daily collection report per branch, emailed automatically (one combined email for all branches).

For each branch and day:
  GROSS: money received, by payment method (payments and patient deposits; account-credit use is not new money),
         minus refunds made that day.
  EXPENSES: expenses entered for that day (not voided), the lab fee share of each payment received (lab fee typed on
         the bill lines, in proportion to the payment), and dentist commissions counted the same way as payroll
         (System settings -> Payroll -> "Dentist commission is counted": per payment, or per procedure done that day).
  NET: gross - expenses.
No patient names are included. Sent at report.daily_time (default 23:00) to report.daily_recipients, once a day.
"""
from __future__ import annotations

import re

from . import settings
from .billing import CREDIT_METHOD, PAYMENT_METHODS, lab_share
from .util import now, now_str, peso

EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def recipients(conn) -> list[str]:
    raw = settings.get("report.daily_recipients", conn) or ""
    out = []
    for part in re.split(r"[\s,;]+", raw):
        if EMAIL_RE.match(part) and part.lower() not in (x.lower() for x in out):
            out.append(part)
    return out


def _method(m: str) -> str:
    return PAYMENT_METHODS.get(m, (m or "Other").replace("_", " ").title())


def branch_report(conn, branch, day: str) -> dict:
    bid = branch["id"]
    gross: dict[str, int] = {}
    refunds = 0
    for r in conn.all("SELECT kind, method, amount_cents FROM payments WHERE status = 'valid' AND method != ? AND branch_id = ? "
                      "AND substr(received_at, 1, 10) = ?", (CREDIT_METHOD, bid, day)):
        if r["kind"] == "payment":
            gross[_method(r["method"])] = gross.get(_method(r["method"]), 0) + r["amount_cents"]
        else:
            refunds += r["amount_cents"]
    for r in conn.all("SELECT kind, method, amount_cents FROM patient_credits WHERE status = 'valid' AND branch_id = ? AND entry_date = ? "
                      "AND kind IN ('deposit', 'refund')", (bid, day)):
        if r["kind"] == "deposit":
            label = f"{_method(r['method'])} (deposit)"
            gross[label] = gross.get(label, 0) + r["amount_cents"]
        else:
            refunds += r["amount_cents"]
    gross_total = sum(gross.values())

    expenses = []   # (label, details, amount)
    for e in conn.all("SELECT category, item, description, payee, amount_cents, status FROM expenses WHERE branch_id = ? AND expense_date = ? "
                      "AND status != 'void' ORDER BY id", (bid, day)):
        details = " · ".join(x for x in (e["item"], e["description"], e["payee"]) if x)
        expenses.append((e["category"], details + (" (not posted yet)" if e["status"] == "draft" else ""), e["amount_cents"]))

    # Lab fees typed on bill lines: the share of each payment received today.
    lab = 0
    for r in conn.all("SELECT p.amount_cents, i.total_cents, (SELECT COALESCE(SUM(lab_fee_cents), 0) FROM invoice_items WHERE invoice_id = i.id) AS lab_fee "
                      "FROM payments p JOIN invoices i ON i.id = p.invoice_id WHERE p.status = 'valid' AND p.kind = 'payment' "
                      "AND p.branch_id = ? AND substr(p.received_at, 1, 10) = ?", (bid, day)):
        lab += lab_share(r["amount_cents"], r["lab_fee"], r["total_cents"])
    if lab:
        expenses.append(("Lab fee", "from bills paid today", lab))

    for name, amount in sorted(dentist_commissions(conn, bid, day).items()):
        if amount:
            expenses.append(("Dentist commission", name, amount))
    exp_total = sum(x[2] for x in expenses)
    return {"branch": branch["name"], "gross": sorted(gross.items(), key=lambda x: -x[1]), "gross_total": gross_total,
            "refunds": refunds, "expenses": expenses, "expenses_total": exp_total, "net": gross_total - refunds - exp_total}


def dentist_commissions(conn, branch_id: int, day: str) -> dict[str, int]:
    """Commission per dentist for the day at this branch, the same way payroll counts it."""
    from .payroll import commission_items, dentist_rates, per_procedure
    out: dict[str, int] = {}
    # Entries recorded by the cashier on a payment, or typed manually (both kinds count in payroll).
    for r in conn.all("SELECT c.amount_cents, e.full_name, COALESCE(p.branch_id, i.branch_id, e.primary_branch_id) AS bid "
                      "FROM dentist_commissions c JOIN employees e ON e.id = c.employee_id LEFT JOIN payments p ON p.id = c.payment_id "
                      "LEFT JOIN invoices i ON i.id = c.invoice_id WHERE c.status = 'valid' AND c.earned_on = ?", (day,)):
        if r["bid"] == branch_id:
            out[r["full_name"]] = out.get(r["full_name"], 0) + r["amount_cents"]
    if per_procedure(conn):
        for d in conn.all("SELECT u.id AS uid, e.id AS eid, e.full_name FROM users u JOIN employees e ON e.user_id = u.id WHERE u.role = 'dentist'"):
            rates = dentist_rates(conn, d["eid"], day)
            if not rates:
                continue
            svc = {r["service_id"]: r["commission_bp"] for r in conn.all("SELECT * FROM dentist_service_rates WHERE employee_id = ?", (d["eid"],))}
            total = sum(i["commission_cents"] for i in commission_items(conn, d["uid"], day, day, branch_id, rates["commission_bp"], svc))
            if total:
                out[d["full_name"]] = out.get(d["full_name"], 0) + total
    return out


def build(conn, day: str) -> list[dict]:
    return [branch_report(conn, b, day) for b in conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")]


def as_text(reports: list[dict], day_label: str) -> str:
    lines = [f"DAILY COLLECTION REPORT · {day_label}", ""]
    for r in reports:
        lines += [f"BRANCH: {r['branch']}", "GROSS"]
        lines += [f"  - {m}: {peso(a)}" for m, a in r["gross"]] or ["  - No collections"]
        lines.append(f"TOTAL GROSS AMOUNT: {peso(r['gross_total'])}")
        if r["refunds"]:
            lines.append(f"LESS REFUNDS: {peso(r['refunds'])}")
        lines.append("EXPENSES")
        lines += [f"  - {label}{(' – ' + det) if det else ''}: {peso(a)}" for label, det, a in r["expenses"]] or ["  - None"]
        lines.append(f"TOTAL EXPENSES: {peso(r['expenses_total'])}")
        lines.append(f"NET: {peso(r['net'])}")
        lines.append("")
    if len(reports) > 1:
        g = sum(r["gross_total"] for r in reports)
        rf = sum(r["refunds"] for r in reports)
        ex = sum(r["expenses_total"] for r in reports)
        lines += ["ALL BRANCHES", f"TOTAL GROSS: {peso(g)}"] + ([f"LESS REFUNDS: {peso(rf)}"] if rf else []) + \
                 [f"TOTAL EXPENSES: {peso(ex)}", f"NET: {peso(g - rf - ex)}", ""]
    lines.append("Automatic report from the Dental Haven clinic system. Totals only; no patient details.")
    return "\n".join(lines)


def _mail_config(conn):
    from . import dentist_mail
    c = dentist_mail.config()
    if c:
        return c
    for b in conn.all("SELECT slug, name FROM branches WHERE active = 1 ORDER BY sort_order"):
        c = dentist_mail.config(b["slug"], b["name"])
        if c:
            return {**c, "sender_name": "Dental Haven"}
    return None


def send(conn, day: str, to: list[str] | None = None) -> tuple[int, str]:
    """Email the report for `day`. Returns (emails sent, message)."""
    from datetime import date
    from flask import current_app
    from . import dentist_mail
    to = to if to is not None else recipients(conn)
    if not to:
        return 0, "No recipients set (System settings → Daily collection report)."
    if current_app.config.get("APP_ENV") == "demo" or current_app.config.get("TESTING"):
        return 0, "Not sent: the demo site never sends emails."
    c = _mail_config(conn)
    if not c:
        return 0, "Email isn't set up on the server."
    d = date.fromisoformat(day)
    label = f"{d.strftime('%A')}, {d.strftime('%b')} {d.day}, {d.year}"
    body = as_text(build(conn, day), label)
    sent = 0
    errors = []
    for addr in to:
        try:
            dentist_mail.send_email(addr, f"Daily collection report · {label}", body, c)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - report each address, keep going
            errors.append(f"{addr}: {exc}"[:200])
    conn.insert("report_sends", {"report_day": day, "recipients": ", ".join(to), "sent": sent, "error": "; ".join(errors)[:1000],
                                 "created_at": now_str()})
    return sent, (f"Sent to {sent} of {len(to)}." + (" Problems: " + "; ".join(errors) if errors else ""))


def run(conn) -> bool:
    """Called often by the background worker: sends today's report once, at or after the set time."""
    if not settings.get("report.daily_enabled", conn):
        return False
    t = now()
    at = settings.get("report.daily_time", conn) or "23:00"
    day = t.date().isoformat()
    if t.strftime("%H:%M") < at:
        return False
    with conn.transaction(immediate=True):   # check and mark together, so two web workers never both send
        if settings.get("report.daily_last_sent", conn) == day:
            return False
        settings.put("report.daily_last_sent", day, None, conn)
    send(conn, day)
    return True

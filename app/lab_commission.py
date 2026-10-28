"""Technician commissions.

Automatic: each technician has a commission % (Employees page). When a clinic pays a lab invoice, the technician assigned
to each work or branch case on it earns that % of the part of the payment that belongs to their work (the payment is
shared across the invoice's works in proportion to their amounts). It counts in the payroll cutoff of the payment date.

Older manual entries (an amount typed on a work or case) still count, when that work is delivered, as before. A work or
case with a manual entry gets no automatic commission, so nothing is counted twice. New manual entries can't be added.
"""
from __future__ import annotations


def technicians(conn):
    return conn.all("SELECT e.id, e.full_name, e.lab_commission_bp FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.active = 1 "
                    "AND (lower(e.position) LIKE '%technician%' OR u.access_role = 'technician') ORDER BY e.full_name")


def entries(conn, work_id=None, case_id=None):
    col, val = ("work_id", work_id) if work_id else ("case_id", case_id)
    return conn.all(f"SELECT c.*, e.full_name, u.name AS by_name FROM lab_commissions c JOIN employees e ON e.id = c.employee_id "
                    f"LEFT JOIN users u ON u.id = c.created_by WHERE c.{col} = ? ORDER BY c.id", (val,))


def rate(conn, employee_id) -> int | None:
    r = conn.one("SELECT lab_commission_bp FROM employees WHERE id = ?", (employee_id,)) if employee_id else None
    return r["lab_commission_bp"] if r else None


def _payments(conn, kind: str, where: str, args: list):
    """Payments on invoices that include works (kind='work') or cases ('case'), with each one's share of the payment."""
    if kind == "work":
        join, col = "JOIN lab_works x ON x.id = it.work_id", "work_id"
        extra = "x.number AS ref, x.case_type, x.clinic_name AS source_name"
    else:
        join, col = "JOIN lab_cases x ON x.id = it.case_id JOIN branches b ON b.id = x.branch_id", "case_id"
        extra = "'#' || x.id AS ref, x.case_type, b.name AS source_name"
    rows = conn.all(
        f"SELECT p.id AS payment_id, p.receipt_no, p.received_on, p.amount_cents AS pay, i.subtotal_cents, i.number AS invoice_number, "
        f"x.id AS item_id, x.technician_id, {extra}, SUM(it.amount_cents) AS line "
        f"FROM lab_payments p JOIN lab_invoices i ON i.id = p.invoice_id JOIN lab_invoice_items it ON it.invoice_id = i.id AND it.{col} IS NOT NULL "
        f"{join} WHERE p.status = 'ok' AND i.status != 'void' AND {where} "
        f"AND NOT EXISTS (SELECT 1 FROM lab_commissions m WHERE m.{col} = x.id) "
        f"GROUP BY p.id, x.id ORDER BY p.received_on, p.id", args)
    out = []
    for r in rows:
        share = round(r["pay"] * r["line"] / r["subtotal_cents"]) if r["subtotal_cents"] else 0
        out.append({**dict(r), "share": max(0, min(share, r["pay"]))})
    return out


def auto_for_period(conn, employee_id: int, start: str, end: str) -> list[dict]:
    bp = rate(conn, employee_id)
    items = []
    for kind in ("work", "case"):
        for r in _payments(conn, kind, "x.technician_id = ? AND p.received_on BETWEEN ? AND ?", [employee_id, start, end]):
            amt = round(r["share"] * bp / 10000) if bp else 0
            note = (f"{bp / 100:g}% of {r['share'] / 100:,.2f} paid" if bp else "No commission % set for this technician") \
                + f" · receipt {r['receipt_no']}"
            items.append({"src": kind, "work_id": r["item_id"] if kind == "work" else None, "case_id": r["item_id"] if kind == "case" else None,
                          "ref": r["ref"], "case_type": r["case_type"], "source_name": r["source_name"], "out_on": r["received_on"],
                          "note": note, "amount_cents": amt, "paid_cents": r["share"], "rate_bp": bp, "auto": True})
    return items


def earned(conn, work_id=None, case_id=None) -> list[dict]:
    """Payments so far on one work or case, with the assigned technician's commission on each (for the work/case page)."""
    kind, val = ("work", work_id) if work_id else ("case", case_id)
    out = []
    for r in _payments(conn, kind, "x.id = ?", [val]):
        bp = rate(conn, r["technician_id"])
        out.append({"received_on": r["received_on"], "receipt_no": r["receipt_no"], "paid_cents": r["share"],
                    "amount_cents": round(r["share"] * bp / 10000) if bp else 0})
    return out


def for_period(conn, employee_id: int, start: str, end: str):
    """Commission for a payroll cutoff: automatic % on payments received in it, plus older manual entries on work delivered in it."""
    manual = [dict(r, auto=False) for r in conn.all(
        "SELECT c.*, 'work' AS src, w.number AS ref, w.case_type, w.clinic_name AS source_name, w.delivered_on AS out_on "
        "FROM lab_commissions c JOIN lab_works w ON w.id = c.work_id "
        "WHERE c.employee_id = ? AND w.status = 'delivered' AND w.delivered_on BETWEEN ? AND ? "
        "UNION ALL "
        "SELECT c.*, 'case' AS src, '#' || lc.id AS ref, lc.case_type, b.name AS source_name, lc.completed_on AS out_on "
        "FROM lab_commissions c JOIN lab_cases lc ON lc.id = c.case_id JOIN branches b ON b.id = lc.branch_id "
        "WHERE c.employee_id = ? AND lc.status = 'delivered' AND lc.completed_on BETWEEN ? AND ? ORDER BY out_on",
        (employee_id, start, end, employee_id, start, end))]
    return sorted(manual + auto_for_period(conn, employee_id, start, end), key=lambda r: (r["out_on"] or "", r["ref"]))


def page_context(conn, user, work=None, case=None) -> dict:
    """What the Technician card on a work or case page needs."""
    item = work or case
    tech = conn.one("SELECT id, full_name, lab_commission_bp FROM employees WHERE id = ?", (item["technician_id"],)) if item["technician_id"] else None
    return {"comm_entries": entries(conn, work_id=work["id"]) if work else entries(conn, case_id=case["id"]),
            "comm_techs": technicians(conn), "comm_tech": tech,
            "comm_earned": earned(conn, work_id=work["id"]) if work else earned(conn, case_id=case["id"]),
            "comm_show_money": user.is_super_admin or user.can("compensation.manage") or user.can("lab.commission"),
            "comm_lab_user": user.is_super_admin or bool(conn.one("SELECT 1 AS x FROM user_labs WHERE user_id = ? AND lab_id = ?",
                                                                  (user.id, item["lab_id"]))),
            "comm_field": "work_id" if work else "case_id", "comm_id": item["id"]}

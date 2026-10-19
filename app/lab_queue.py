"""The laboratory's work queue: what the lab receptionist (and lab staff) need to act on, for their own lab(s).

- New cases sent by the branches, waiting to be accepted.
- Due by tomorrow or overdue (outside-clinic works and branch cases still in production).
- Ready for pick-up or delivery.
- On hold, remake, or out for trial fitting.
- Billing (with lab billing access): delivered work not billed yet, and unpaid invoices past their due date.
"""
from __future__ import annotations

from datetime import timedelta

from .lab_status import LATE, sql_list
from .util import today

LAB_POSITION_WORDS = ("lab", "technician")


def lab_ids(conn, user_id: int) -> list[int]:
    return [r["lab_id"] for r in conn.all("SELECT ul.lab_id FROM user_labs ul JOIN laboratories l ON l.id = ul.lab_id "
                                          "WHERE ul.user_id = ? AND l.active = 1", (user_id,))]


def is_lab_only(conn, user) -> bool:
    """Works at the lab, not the clinic: assigned to a lab and the position is a lab one (Laboratory Receptionist, technicians)."""
    if user.is_super_admin or not lab_ids(conn, user.id):
        return False
    e = conn.one("SELECT position FROM employees WHERE user_id = ?", (user.id,))
    pos = (e["position"] if e else "").lower()
    return any(w in pos for w in LAB_POSITION_WORDS) or user.access_role in ("technician", "lab_receptionist")


def _marks(ids):
    return ",".join("?" for _ in ids)


def build(conn, ids: list[int], can_works: bool, can_billing: bool) -> dict:
    if not ids:
        return {}
    t = today()
    day, tomorrow = t.isoformat(), (t + timedelta(days=1)).isoformat()
    m = _marks(ids)
    case_sel = ("SELECT c.id, c.case_type, c.status, c.due_on, c.sent_on, c.teeth, b.name AS branch, p.last_name, p.first_name, "
                "l.name AS lab FROM lab_cases c JOIN branches b ON b.id = c.branch_id JOIN patients p ON p.id = c.patient_id "
                f"JOIN laboratories l ON l.id = c.lab_id WHERE c.lab_id IN ({m}) ")
    work_sel = (f"SELECT w.id, w.number, w.case_type, w.status, w.due_on, w.clinic_name, w.units, w.price_cents, w.invoice_id "
                f"FROM lab_works w WHERE w.lab_id IN ({m}) ")

    def cases(where, args=(), order="c.due_on IS NULL, c.due_on, c.id"):
        return [dict(r, kind="case") for r in conn.all(case_sel + where + f" ORDER BY {order}", [*ids, *args])]

    def works(where, args=(), order="w.due_on IS NULL, w.due_on, w.id"):
        if not can_works:
            return []
        return [dict(r, kind="work") for r in conn.all(work_sel + where + f" ORDER BY {order}", [*ids, *args])]

    def by_due(rows):
        return sorted(rows, key=lambda r: (r["due_on"] is None, r["due_on"] or "", r["id"]))

    q = {
        "today": day,
        "new_cases": cases("AND c.status = 'sent'", order="c.sent_on, c.id"),
        "due": by_due(works(f"AND w.status IN {sql_list(LATE)} AND w.due_on IS NOT NULL AND w.due_on <= ?", [tomorrow])
                      + cases(f"AND c.status IN {sql_list(LATE)} AND c.status != 'sent' AND c.due_on IS NOT NULL AND c.due_on <= ?", [tomorrow])),
        "ready": by_due(works("AND w.status = 'ready'") + cases("AND c.status = 'ready'")),
        "waiting": by_due(works("AND w.status IN ('on_hold', 'remake', 'try_in')") + cases("AND c.status IN ('on_hold', 'remake', 'try_in')")),
    }
    if can_billing:
        q["to_bill"] = works("AND w.status = 'delivered' AND w.invoice_id IS NULL", order="w.delivered_on, w.id")
        q["unpaid"] = [dict(r) for r in conn.all(
            f"SELECT i.id, i.number, i.clinic_name, i.due_on, i.total_cents, i.paid_cents FROM lab_invoices i WHERE i.lab_id IN ({m}) "
            "AND i.status = 'issued' AND i.paid_cents < i.total_cents AND i.due_on IS NOT NULL AND i.due_on < ? ORDER BY i.due_on",
            [*ids, day])]
    return q


def count(conn, ids: list[int], can_works: bool) -> int:
    """For the menu badge: new branch cases + work due by tomorrow or overdue."""
    if not ids:
        return 0
    tomorrow = (today() + timedelta(days=1)).isoformat()
    m = _marks(ids)
    n = conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE lab_id IN ({m}) AND (status = 'sent' OR (status IN {sql_list(LATE)} "
                    "AND due_on IS NOT NULL AND due_on <= ?))", [*ids, tomorrow]) or 0
    if can_works:
        n += conn.scalar(f"SELECT COUNT(*) FROM lab_works WHERE lab_id IN ({m}) AND status IN {sql_list(LATE)} "
                         "AND due_on IS NOT NULL AND due_on <= ?", [*ids, tomorrow]) or 0
    return n

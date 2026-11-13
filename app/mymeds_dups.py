"""Bill lines entered twice in MyMedsPH (same patient, date, item and price on imported bills): find them so a person can
remove the extra copy. Removing a line fixes the bill total; a "Paid in MyMedsPH" payment made of that total is reduced
with it, so the patient isn't left with a credit that never existed."""
from __future__ import annotations

from .billing import LEGACY_METHOD


def find(conn, branch_ids: list[int] | None = None) -> list[dict]:
    where = "" if branch_ids is None else f" AND i.branch_id IN ({','.join('?' * len(branch_ids)) or 'NULL'})"
    rows = conn.all("SELECT ii.id, ii.invoice_id, ii.description, ii.amount_cents, ii.done_on, i.number, i.patient_id, i.branch_id, "
                    "p.first_name, p.last_name, p.chart_no FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id "
                    "JOIN patients p ON p.id = i.patient_id WHERE i.legacy = 1 AND i.status = 'issued'" + where +
                    " ORDER BY i.patient_id, ii.done_on, ii.id", list(branch_ids or []))
    groups: dict[tuple, list] = {}
    for r in rows:
        key = (r["patient_id"], r["done_on"], (r["description"] or "").strip().lower(), r["amount_cents"])
        groups.setdefault(key, []).append(dict(r))
    out = []
    for (pid, day, _, amt), lines in groups.items():
        if len(lines) < 2:
            continue
        first = lines[0]
        out.append({"patient_id": pid, "patient": f"{first['last_name']}, {first['first_name']}", "chart": first["chart_no"], "date": day,
                    "description": first["description"], "amount": amt, "lines": lines, "extra": len(lines) - 1})
    out.sort(key=lambda g: (-(g["amount"] * g["extra"]), g["patient"]))
    return out


def remove_line(conn, item_id: int, recalc) -> tuple[bool, str]:
    """Remove one copy. Refused if it isn't a duplicate any more or the bill's other payments would exceed the new total."""
    it = conn.one("SELECT ii.*, i.patient_id, i.legacy, i.status, i.total_cents FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id "
                  "WHERE ii.id = ?", (item_id,))
    if not it or it["legacy"] != 1 or it["status"] != "issued":
        return False, "That line can't be removed here."
    twins = conn.scalar("SELECT COUNT(*) FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id WHERE i.patient_id = ? AND i.legacy = 1 "
                        "AND i.status = 'issued' AND ii.done_on IS ? AND LOWER(TRIM(ii.description)) = LOWER(TRIM(?)) AND ii.amount_cents = ?",
                        (it["patient_id"], it["done_on"], it["description"], it["amount_cents"]))
    if twins < 2:
        return False, "That line has no copy any more."
    if conn.scalar("SELECT 1 FROM dentist_commissions WHERE invoice_id = ? AND status = 'valid' LIMIT 1", (it["invoice_id"],)):
        return False, "This bill has dentist commission recorded. Remove the line from the bill itself after checking the commission."
    new_total = it["total_cents"] - it["amount_cents"]
    pays = conn.all("SELECT * FROM payments WHERE invoice_id = ? AND status = 'valid' AND kind = 'payment' ORDER BY id", (it["invoice_id"],))
    mm = [p for p in pays if p["method"] == LEGACY_METHOD]
    other = sum(p["amount_cents"] for p in pays if p["method"] != LEGACY_METHOD)
    if other > new_total:
        return False, "This bill's payments are more than its total without that line. Check the payments on the bill first."
    paid = other + sum(p["amount_cents"] for p in mm)
    over = paid - new_total
    for p in reversed(mm):                     # trim the "Paid in MyMedsPH" amount that included the copy
        if over <= 0:
            break
        cut = min(over, p["amount_cents"])
        if cut == p["amount_cents"]:
            conn.execute("UPDATE payments SET status = 'void', void_reason = 'Duplicate MyMedsPH line removed' WHERE id = ?", (p["id"],))
        else:
            conn.execute("UPDATE payments SET amount_cents = amount_cents - ? WHERE id = ?", (cut, p["id"]))
        over -= cut
    conn.execute("DELETE FROM invoice_items WHERE id = ?", (item_id,))
    recalc(conn, it["invoice_id"])
    return True, ""

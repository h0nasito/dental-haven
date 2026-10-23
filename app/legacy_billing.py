"""Turn MyMedsPH bills (imported as history in legacy_bills) into real bills.

The MyMedsPH export has one row per bill line: date, service, qty, price, discount, total and a numeric status, but
no bill number, payments or dentist. So:
- lines of one patient on one date with the same meaning become one bill (number MM-000123, dated that day);
- what each status number means (paid / unpaid / keep as history) is chosen once by an admin, after comparing
  with MyMedsPH; the choice is saved and used again for bills that come in with later imports;
- a "paid" bill gets one payment of its total on the bill date, method "Paid in MyMedsPH";
- an "unpaid" bill keeps its balance, to be collected like any bill;
- the dentist is left empty: staff set it on a line when needed (commission then follows as for any bill).
These bills count in sales reports, collections and (once a dentist is set) commission, like any other bill.
The conversion can be undone for bills nobody has added a payment to since.
"""
from __future__ import annotations

import json

from . import settings
from .billing import LEGACY_METHOD
from .util import now_str

CHOICES = {"paid": "Paid", "unpaid": "Unpaid (balance to collect)", "history": "Keep as history only"}
MAP_KEY = "legacy.bill_status_map"
BRANCH_KEY = "legacy.bill_default_branch"


def saved_map(conn) -> dict:
    raw = settings.get(MAP_KEY, conn)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    return raw if isinstance(raw, dict) else {}


def status_summary(conn) -> list[dict]:
    """Each status number among the old bill lines not converted yet: lines, total, dates and a few sample services."""
    rows = conn.all("SELECT status_code AS code, COUNT(*) AS n, COUNT(DISTINCT patient_id) AS patients, COALESCE(SUM(total_cents), 0) AS total, "
                    "MIN(bill_date) AS first, MAX(bill_date) AS last FROM legacy_bills WHERE invoice_id IS NULL "
                    "GROUP BY status_code ORDER BY status_code")
    out = []
    for r in rows:
        samples = conn.all("SELECT bill_date, COALESCE(NULLIF(service, ''), item) AS service, total_cents FROM legacy_bills "
                           "WHERE invoice_id IS NULL AND status_code = ? ORDER BY bill_date DESC, id DESC LIMIT 4", (r["code"],))
        out.append(dict(r, samples=samples))
    return out


def convert(conn, mapping: dict, default_branch_id: int | None, user_id: int) -> dict:
    """Create bills for the old lines whose status is mapped to paid/unpaid. Call inside a transaction."""
    stats = {"bills": 0, "lines": 0, "paid": 0, "unpaid": 0, "no_branch": 0, "total": 0}
    wanted = {c: k for c, k in mapping.items() if k in ("paid", "unpaid")}
    if not wanted:
        return stats
    marks = ",".join("?" * len(wanted))
    lines = conn.all(f"SELECT lb.*, p.preferred_branch_id AS branch_id FROM legacy_bills lb JOIN patients p ON p.id = lb.patient_id "
                     f"WHERE lb.invoice_id IS NULL AND lb.status_code IN ({marks}) ORDER BY lb.patient_id, lb.bill_date, lb.id", list(wanted))
    services = {r["name"].strip().lower(): r["id"] for r in conn.all("SELECT id, name FROM services")}
    groups: dict[tuple, list] = {}
    for ln in lines:
        groups.setdefault((ln["patient_id"], ln["bill_date"], wanted[ln["status_code"]]), []).append(ln)
    ts = now_str()
    for (pid, day, kind), items in groups.items():
        branch = items[0]["branch_id"] or default_branch_id
        if not branch:
            stats["no_branch"] += len(items)
            continue
        total = sum(i["total_cents"] for i in items)
        iid = conn.insert("invoices", {"number": f"MM-{items[0]['id']:06d}", "branch_id": branch, "patient_id": pid, "status": "issued",
                                       "issued_at": f"{day} 12:00:00", "subtotal_cents": total, "discount_cents": 0, "tax_cents": 0,
                                       "total_cents": total, "notes": "Imported from MyMedsPH", "created_by": user_id, "created_at": ts,
                                       "legacy": 1})
        for i in items:
            desc = i["service"] or i["item"] or "Service"
            if i["item"] and i["service"] and i["item"].strip().lower() != i["service"].strip().lower():
                desc = f"{i['service']} · {i['item']}"
            conn.insert("invoice_items", {"invoice_id": iid, "service_id": services.get((i["service"] or i["item"] or "").strip().lower()),
                                          "description": desc[:250], "qty": i["qty"] or 1,
                                          "unit_price_cents": i["unit_price_cents"] or (i["total_cents"] // max(1, i["qty"] or 1)),
                                          "discount_cents": i["discount_cents"], "amount_cents": i["total_cents"], "done_on": day})
            conn.execute("UPDATE legacy_bills SET invoice_id = ? WHERE id = ?", (iid, i["id"]))
        if kind == "paid" and total > 0:
            conn.insert("payments", {"invoice_id": iid, "branch_id": branch, "kind": "payment", "amount_cents": total, "method": LEGACY_METHOD,
                                     "reference": "", "received_at": f"{day} 12:00:00", "received_by": user_id, "status": "valid",
                                     "notes": "Paid in MyMedsPH (imported)", "created_at": ts})
        stats["bills"] += 1
        stats["lines"] += len(items)
        stats[kind] += 1
        stats["total"] += total
    return stats


def undo(conn) -> dict:
    """Remove converted bills again (lines go back to history), except bills staff have worked on since:
    a new payment, a dentist set on a line, account credit, a signature or commission entry, or voided.
    Done in a few set-based steps, so tens of thousands of bills go quickly."""
    total = conn.scalar("SELECT COUNT(*) FROM invoices WHERE legacy = 1") or 0
    conn.execute("DROP TABLE IF EXISTS tmp_legacy_undo")
    conn.execute("CREATE TEMP TABLE tmp_legacy_undo (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO tmp_legacy_undo (id) SELECT id FROM invoices WHERE legacy = 1 AND status = 'issued'")
    # keep bills staff have worked on: one pass over each table
    conn.execute("DELETE FROM tmp_legacy_undo WHERE id IN (SELECT invoice_id FROM payments WHERE method != ?)", (LEGACY_METHOD,))
    conn.execute("DELETE FROM tmp_legacy_undo WHERE id IN (SELECT invoice_id FROM invoice_items WHERE dentist_id IS NOT NULL)")
    for t in ("patient_credits", "payment_signatures", "dentist_commissions", "quotations", "visit_notes"):
        conn.execute(f"DELETE FROM tmp_legacy_undo WHERE id IN (SELECT invoice_id FROM {t} WHERE invoice_id IS NOT NULL)")
    removed = conn.scalar("SELECT COUNT(*) FROM tmp_legacy_undo") or 0
    conn.execute("UPDATE legacy_bills SET invoice_id = NULL WHERE invoice_id IN (SELECT id FROM tmp_legacy_undo)")
    conn.execute("DELETE FROM payments WHERE invoice_id IN (SELECT id FROM tmp_legacy_undo)")
    conn.execute("DELETE FROM invoice_items WHERE invoice_id IN (SELECT id FROM tmp_legacy_undo)")
    conn.execute("DELETE FROM invoices WHERE id IN (SELECT id FROM tmp_legacy_undo)")
    conn.execute("DROP TABLE tmp_legacy_undo")
    return {"removed": removed, "kept": total - removed}

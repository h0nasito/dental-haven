"""Lab works report: every piece of work the lab handled in a period, outside clinic works and branch cases together.

One row per work or case: who it's for (dental clinic or branch), what it is, the technician(s), when it started, when
it was due and delivered, the amount and how far it's paid. No patient names (the report is for the lab's business).

Amounts: what the work's lines on its lab invoice add up to, after the invoice's discount; not yet billed = its price.
When one invoice covers several works, its payments are shared out in proportion to each work's amount."""
from __future__ import annotations

from datetime import date

from .lab_status import CLOSED, label as status_label

BASES = {"started": "Started (received / sent to lab)", "delivered": "Delivered"}
PAYMENT_STATES = {"paid": "Paid", "partial": "Partly paid", "unpaid": "Unpaid", "draft": "On a draft invoice", "unbilled": "Not billed yet"}


def _days(a: str | None, b: str | None) -> int | None:
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days if a and b else None
    except ValueError:
        return None


def _delivered_event(conn, table: str, col: str, ref: int) -> str | None:
    """When the delivered date wasn't saved, the day the status was changed to Delivered."""
    v = conn.scalar(f"SELECT MAX(created_at) FROM {table} WHERE {col} = ? AND status = 'delivered'", (ref,))
    return v[:10] if v else None


def build(conn, lab_ids: list[int], start: str, end: str, basis: str = "started", kind: str = "", client_id: int | None = None,
          technician: int | None = None, case_type: str = "", status: str = "", payment: str = "") -> dict:
    marks = ",".join("?" * len(lab_ids)) or "NULL"
    w_date = "w.delivered_on" if basis == "delivered" else "w.received_on"
    c_date = "c.completed_on" if basis == "delivered" else "c.sent_on"
    client = conn.one("SELECT * FROM lab_clients WHERE id = ?", (client_id,)) if client_id else None
    rows = []
    if kind in ("", "outside") and not (client and client["branch_id"]):
        q = (f"SELECT w.*, cl.branch_id AS client_branch FROM lab_works w LEFT JOIN lab_clients cl ON cl.id = w.client_id "
             f"WHERE w.lab_id IN ({marks}) AND {w_date} BETWEEN ? AND ?")
        args = [*lab_ids, start, end]
        if client:
            q += " AND w.client_id = ?"
            args.append(client["id"])
        for w in conn.all(q, args):
            items = conn.all("SELECT case_type, units, arch FROM lab_work_items WHERE work_id = ? ORDER BY sort_order, id", (w["id"],))
            rows.append({"src": "work", "id": w["id"], "ref": w["number"], "kind": "outside", "who": w["clinic_name"],
                         "who_sub": w["doctor"], "case_type": w["case_type"], "units": w["units"] or 1,
                         "items": [(i["case_type"], i["units"] or 1) for i in items] or [(w["case_type"], w["units"] or 1)],
                         "arches": [i["arch"] for i in items] or [w["arch"]],
                         "status": w["status"], "start": w["received_on"], "due": w["due_on"],
                         "delivered": (w["delivered_on"] or _delivered_event(conn, "lab_work_events", "work_id", w["id"]))
                         if w["status"] == "delivered" else None,
                         "price": w["price_cents"], "invoice_id": w["invoice_id"], "technician_id": w["technician_id"]})
    if kind in ("", "branch") and not (client and not client["branch_id"]):
        q = (f"SELECT c.*, b.name AS branch, u.name AS dentist FROM lab_cases c JOIN branches b ON b.id = c.branch_id "
             f"LEFT JOIN users u ON u.id = c.dentist_id WHERE c.lab_id IN ({marks}) AND {c_date} BETWEEN ? AND ?")
        args = [*lab_ids, start, end]
        if client:
            q += " AND c.branch_id = ?"
            args.append(client["branch_id"])
        for c in conn.all(q, args):
            items = conn.all("SELECT case_type, units, arch FROM lab_case_items WHERE case_id = ? ORDER BY sort_order, id", (c["id"],))
            rows.append({"src": "case", "id": c["id"], "ref": f"#{c['id']}", "kind": "branch", "who": c["branch"],
                         "who_sub": c["dentist"] or "", "case_type": c["case_type"], "units": c["units"] or 1,
                         "items": [(i["case_type"], i["units"] or 1) for i in items] or [(c["case_type"], c["units"] or 1)],
                         "arches": [i["arch"] for i in items] or [""],
                         "status": c["status"], "start": c["sent_on"], "due": c["due_on"] or c["install_on"],
                         "delivered": (c["completed_on"] or _delivered_event(conn, "lab_case_events", "case_id", c["id"]))
                         if c["status"] == "delivered" else None,
                         "price": c["lab_fee_cents"], "invoice_id": c["invoice_id"], "technician_id": c["technician_id"]})

    # Technicians (from commissions on the work or case)
    techs: dict[tuple, list] = {}
    for t in conn.all("SELECT lc.work_id, lc.case_id, lc.employee_id, lc.amount_cents, e.full_name FROM lab_commissions lc "
                      "JOIN employees e ON e.id = lc.employee_id"):
        key = ("work", t["work_id"]) if t["work_id"] else ("case", t["case_id"])
        techs.setdefault(key, []).append(t)

    invoices = {}
    today_s = date.today().isoformat()
    out = []
    for r in rows:
        r["status_label"] = status_label(r["status"])
        r["techs"] = [dict(t) for t in techs.get((r["src"], r["id"]), [])]   # older manual commission entries
        r["auto_tech"] = None
        if r.get("technician_id") and not r["techs"]:
            emp = conn.one("SELECT full_name, lab_commission_bp FROM employees WHERE id = ?", (r["technician_id"],))
            if emp:
                r["auto_tech"] = {"employee_id": r["technician_id"], "full_name": emp["full_name"], "amount_cents": 0,
                                  "bp": emp["lab_commission_bp"] or 0}
                r["techs"] = [r["auto_tech"]]
        r["tech_names"] = ", ".join(dict.fromkeys(t["full_name"] for t in r["techs"]))
        r["commission"] = sum(t["amount_cents"] or 0 for t in r["techs"])
        arch_label = {"upper": "upper", "lower": "lower", "both": "upper & lower"}
        r["what"] = ", ".join(f"{ct}{' ×' + str(u) if u and u != 1 else ''}" + (f" ({arch_label[a]})" if a in arch_label else "")
                              for (ct, u), a in zip(r["items"], r.get("arches") or [""] * len(r["items"])))
        r["all_types"] = [ct for ct, _ in r["items"]]
        inv = None
        if r["invoice_id"]:
            inv = invoices.get(r["invoice_id"]) or conn.one("SELECT * FROM lab_invoices WHERE id = ?", (r["invoice_id"],))
            invoices[r["invoice_id"]] = inv
        if inv and inv["status"] != "void":
            col = "work_id" if r["src"] == "work" else "case_id"
            lines = conn.scalar(f"SELECT COALESCE(SUM(amount_cents), 0) "
                                f"FROM lab_invoice_items WHERE invoice_id = ? AND {col} = ?", (inv["id"], r["id"])) or 0
            sub = inv["subtotal_cents"] or 0
            billed = round(lines * inv["total_cents"] / sub) if sub else lines
            r["amount"] = billed
            r["invoice"] = inv["number"] or "Draft"
            if inv["status"] == "draft":
                r["paid"], r["payment"] = 0, "draft"
            else:
                r["paid"] = round(billed * min(inv["paid_cents"], inv["total_cents"]) / inv["total_cents"]) if inv["total_cents"] else 0
                r["payment"] = "paid" if inv["paid_cents"] >= inv["total_cents"] else ("partial" if inv["paid_cents"] > 0 else "unpaid")
                r["past_due"] = r["payment"] != "paid" and bool(inv["due_on"]) and inv["due_on"] < today_s
        else:
            r["amount"], r["paid"], r["payment"], r["invoice"] = r["price"] or 0, 0, "unbilled", ""
        r["balance"] = (r["amount"] or 0) - (r["paid"] or 0) if r["payment"] != "unbilled" else 0
        if r["auto_tech"]:   # the technician's % of what's been paid for this work so far
            r["auto_tech"]["amount_cents"] = round((r["paid"] or 0) * r["auto_tech"]["bp"] / 10000)
        r["commission"] = sum(t["amount_cents"] or 0 for t in r["techs"])
        r["days"] = _days(r["start"], r["delivered"])
        r["on_time"] = None if not (r["delivered"] and r["due"]) else r["delivered"][:10] <= r["due"][:10]
        r["late_now"] = r["status"] not in CLOSED and r["status"] != "ready" and bool(r["due"]) and r["due"][:10] < today_s
        if technician and not any(t["employee_id"] == technician for t in r["techs"]):
            continue
        if case_type and case_type not in r["all_types"]:
            continue
        if status == "open" and r["status"] in CLOSED or status == "delivered" and r["status"] != "delivered" \
                or status == "cancelled" and r["status"] != "cancelled":
            continue
        if payment and r["payment"] != payment:
            continue
        out.append(r)
    out.sort(key=lambda r: ((r["delivered"] if basis == "delivered" else r["start"]) or "", r["ref"]))

    counted = [r for r in out if r["status"] != "cancelled"]
    by_type, by_tech, by_who = {}, {}, {}
    for r in counted:
        for ct, u in r["items"]:
            t = by_type.setdefault(ct, {"works": 0, "units": 0})
            t["works"] += 1
            t["units"] += u or 1
        for name, amt in {t["full_name"]: 0 for t in r["techs"]}.items():
            x = by_tech.setdefault(name, {"works": 0, "delivered": 0, "commission": 0})
            x["works"] += 1
            x["delivered"] += 1 if r["status"] == "delivered" else 0
        for t in r["techs"]:
            by_tech[t["full_name"]]["commission"] += t["amount_cents"] or 0
        w = by_who.setdefault((r["kind"], r["who"]), {"works": 0, "amount": 0, "paid": 0, "balance": 0})
        w["works"] += 1
        w["amount"] += r["amount"] or 0
        w["paid"] += r["paid"] or 0
        w["balance"] += r["balance"] or 0
    delivered = [r for r in counted if r["delivered"]]
    timed = [r for r in delivered if r["on_time"] is not None]
    days = [r["days"] for r in delivered if r["days"] is not None]
    return {
        "rows": out,
        "count": len(counted), "cancelled": len(out) - len(counted),
        "delivered": len(delivered), "open": sum(1 for r in counted if r["status"] not in CLOSED),
        "late_now": sum(1 for r in counted if r["late_now"]),
        "amount": sum(r["amount"] or 0 for r in counted), "paid": sum(r["paid"] or 0 for r in counted),
        "balance": sum(r["balance"] or 0 for r in counted),
        "unbilled": sum(r["amount"] or 0 for r in counted if r["payment"] == "unbilled"),
        "unbilled_count": sum(1 for r in counted if r["payment"] == "unbilled"),
        "on_time": round(100 * sum(1 for r in timed if r["on_time"]) / len(timed)) if timed else None,
        "avg_days": round(sum(days) / len(days), 1) if days else None,
        "by_type": sorted(by_type.items(), key=lambda x: (-x[1]["works"], x[0])),
        "by_tech": sorted(by_tech.items(), key=lambda x: (-x[1]["works"], x[0])),
        "untagged": sum(1 for r in counted if not r["techs"]),
        "by_who": sorted(by_who.items(), key=lambda x: (-x[1]["amount"], x[0][1])),
    }

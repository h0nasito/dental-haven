"""Dentist commission report by payroll cutoff (1st–15th, 16th–end of month), counted exactly as payroll counts it.

Per payment (System settings → Payroll, the default): the commission the cashier recorded on each payment, plus manual
entries. Per procedure: each bill line done in the cutoff, (amount − its share of the bill discount − lab fee) × the
dentist's rate, plus manual entries. Patients are shown by chart number only (as in payroll).
"""
from __future__ import annotations

import calendar
import csv
import io
from datetime import date

from flask import Blueprint, Response, abort, g, render_template, request

from .. import audit
from ..auth import require
from ..db import get_db
from ..payroll import commission_items, dentist_rates, per_procedure
from ..util import parse_date, peso, to_int, today

bp = Blueprint("commissions", __name__, url_prefix="/staff/commissions")


def cutoff(d: date, half: int) -> tuple[date, date]:
    last = calendar.monthrange(d.year, d.month)[1]
    return (d.replace(day=1), d.replace(day=15)) if half == 1 else (d.replace(day=16), d.replace(day=last))


def current_cutoff(t: date | None = None) -> tuple[date, int]:
    t = t or today()
    return t.replace(day=1), (1 if t.day <= 15 else 2)


def _branches(conn):
    rows = conn.all("SELECT id, name FROM branches WHERE active = 1 ORDER BY sort_order")
    return rows if g.user.is_super_admin else [b for b in rows if b["id"] in g.user.branch_ids]


def build(conn, start: date, end: date, branch_ids: list[int], branch_id=None, dentist_id=None) -> list[dict]:
    """[{dentist, user_id, rows: [...], base, commission, n}] for dentists with commission in the period."""
    s, e = start.isoformat(), end.isoformat()
    proc = per_procedure(conn)
    allowed = set([branch_id] if branch_id else branch_ids)
    out = []
    for d in conn.all("SELECT u.id AS uid, u.name, e.id AS eid FROM users u JOIN employees e ON e.user_id = u.id "
                      "WHERE u.role = 'dentist' ORDER BY u.name"):
        if dentist_id and d["uid"] != dentist_id:
            continue
        rows = []
        if proc:
            r = dentist_rates(conn, d["eid"], e)
            svc = {x["service_id"]: x["commission_bp"] for x in conn.all("SELECT * FROM dentist_service_rates WHERE employee_id = ?", (d["eid"],))}
            for it in commission_items(conn, d["uid"], s, e, None, (r["commission_bp"] or 0) if r else 0, svc):
                if it["branch_id"] not in allowed or not it["commission_cents"]:
                    continue
                rows.append({"date": it["done_on"], "branch": it["branch"], "bill": it["invoice_number"] or "draft", "chart": it["chart_no"],
                             "what": (it["description"] or "").split(" · ")[0] + (f" #{it['tooth']}" if it.get("tooth") else ""),
                             "base": it["base_cents"], "rate_bp": it["rate_bp"], "amount": it["commission_cents"], "kind": "Procedure"})
        for m in conn.all("SELECT c.*, i.number AS bill, p.chart_no, COALESCE(pb.name, ib.name) AS branch, COALESCE(pay.branch_id, i.branch_id) AS bid, "
                          "pay.method, (SELECT group_concat(description, ', ') FROM invoice_items WHERE invoice_id = c.invoice_id) AS items "
                          "FROM dentist_commissions c LEFT JOIN invoices i ON i.id = c.invoice_id LEFT JOIN patients p ON p.id = i.patient_id "
                          "LEFT JOIN payments pay ON pay.id = c.payment_id LEFT JOIN branches pb ON pb.id = pay.branch_id "
                          "LEFT JOIN branches ib ON ib.id = i.branch_id WHERE c.employee_id = ? AND c.status = 'valid' AND c.amount_cents != 0 "
                          "AND c.earned_on BETWEEN ? AND ? "
                          "ORDER BY c.earned_on, c.id", (d["eid"], s, e)):
            if m["bid"] is not None and m["bid"] not in allowed:
                continue
            if m["bid"] is None and branch_id:
                continue
            what = m["description"] or ""
            if m["items"] and (not what or what.startswith("Payment on")):
                what = m["items"]
            rows.append({"date": m["earned_on"], "branch": m["branch"] or "—", "bill": m["bill"] or "—", "chart": m["chart_no"] or "—",
                         "what": what[:160], "base": m["base_cents"], "rate_bp": m["rate_bp"], "amount": m["amount_cents"],
                         "kind": "Payment" if m["payment_id"] else "Manual"})
        if rows:
            rows.sort(key=lambda r: (r["date"] or "", r["bill"] or ""))
            by_branch: dict[str, int] = {}
            for r in rows:
                by_branch[r["branch"]] = by_branch.get(r["branch"], 0) + r["amount"]
            out.append({"dentist": d["name"], "user_id": d["uid"], "rows": rows, "n": len(rows), "commission": sum(r["amount"] for r in rows),
                        "base": sum(r["base"] or 0 for r in rows), "by_branch": sorted(by_branch.items())})
    return out


@bp.route("/")
@require("commission.view")
def index():
    conn = get_db()
    branches = _branches(conn)
    ids = [b["id"] for b in branches]
    m = request.args.get("month") or ""
    try:
        y, mo = (int(x) for x in m.split("-"))
        month = date(y, mo, 1)
    except (ValueError, TypeError):
        month = None
    cm, ch = current_cutoff()
    month = month or cm
    half = to_int(request.args.get("half")) or (ch if month == cm else 1)
    half = half if half in (1, 2, 3) else 1
    if half == 3:                                      # custom range
        start = parse_date(request.args.get("from")) or month
        end = parse_date(request.args.get("to")) or cutoff(month, 2)[1]
        if start > end:
            start, end = end, start
    else:
        start, end = cutoff(month, half)
    branch_id = to_int(request.args.get("branch"))
    branch_id = branch_id if branch_id in ids else None
    dentist_id = to_int(request.args.get("dentist"))
    data = build(conn, start, end, ids, branch_id, dentist_id)
    total = sum(d["commission"] for d in data)
    fmt = request.args.get("format")
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([f"Dentist commissions {start.isoformat()} to {end.isoformat()}"])
        w.writerow(["Dentist", "Date", "Branch", "Bill", "Chart no.", "Procedure / for", "Type", "Base (PHP)", "Rate %", "Commission (PHP)"])
        for d in data:
            for r in d["rows"]:
                w.writerow([d["dentist"], r["date"], r["branch"], r["bill"], r["chart"], r["what"], r["kind"],
                            (r["base"] or 0) / 100 if r["base"] is not None else "", (r["rate_bp"] or 0) / 100 if r["rate_bp"] is not None else "",
                            r["amount"] / 100])
            w.writerow([d["dentist"], "", "", "", "", "Total", "", "", "", d["commission"] / 100])
        w.writerow(["All dentists", "", "", "", "", "Total", "", "", "", total / 100])
        audit.record("commission_report_exported", "report", None, f"Dentist commissions {start.isoformat()}–{end.isoformat()}")
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=dentist-commissions-{start.isoformat()}-{end.isoformat()}.csv"})
    dentists = conn.all("SELECT u.id, u.name FROM users u JOIN employees e ON e.user_id = u.id WHERE u.role = 'dentist' ORDER BY u.name")
    months = []
    t = today().replace(day=1)
    for i in range(12):
        mm = (t.month - i - 1) % 12 + 1
        yy = t.year + ((t.month - i - 1) // 12)
        months.append(date(yy, mm, 1))
    tpl = "staff/commissions/print.html" if request.args.get("print") else "staff/commissions/index.html"
    return render_template(tpl, data=data, total=total, start=start, end=end, month=month, half=half, months=months,
                           branches=branches, branch_id=branch_id, dentists=dentists, dentist_id=dentist_id, peso=peso,
                           basis="per procedure (bill lines)" if per_procedure(conn) else "per payment (recorded by the cashier)",
                           query=request.query_string.decode())

"""Monthly business report: scorecard, key ratios, costs by group and a few plain-language takeaways.

Everything comes from what is already recorded:
- Gross collections: money received (payments + deposits, less refunds), as in the Financial report.
- Expenses: the Expenses / Monthly bills entries of the month, lab fees on bills paid, grouped as below.
- Payroll: "Salaries & wages" expenses + dentist commissions + approved payroll runs that end in the month.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import finance_report

GROUPS = {
    "Clinical supplies & lab": ["Dental supplies", "Laboratory fees", "Lab fees (on bills paid)"],
    "Fixed overhead": ["Rent", "Electricity", "Water", "Internet & phone", "Utilities (power, water, internet)", "Equipment & maintenance",
                       "Repairs", "Taxes, permits & licenses"],
    "Administrative & marketing": ["Marketing & advertising", "Professional fees", "Office supplies", "Transportation & delivery",
                                   "Pantry & cleaning supplies", "Food & meals", "Miscellaneous"],
    "Payroll": ["Salaries & wages", "Dentist commissions", "Payroll runs (approved)"],
}
GROUP_OF = {c: g for g, cats in GROUPS.items() for c in cats}


def month_bounds(m: date) -> tuple[date, date]:
    start = m.replace(day=1)
    nxt = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
    return start, nxt - timedelta(days=1)


def _payroll_runs(conn, ids: list[int], start: str, end: str) -> int:
    """Gross pay (estimate + adjustment + additions) of approved payroll runs ending in the month, for these branches."""
    from .payroll import period_items
    total = 0
    marks = ",".join("?" * len(ids)) or "NULL"
    for p in conn.all(f"SELECT id FROM payroll_periods WHERE status = 'approved' AND end_date BETWEEN ? AND ? "
                      f"AND (branch_id IS NULL OR branch_id IN ({marks}))", [start, end, *ids]):
        items = period_items(conn, p["id"])
        for ln in conn.all("SELECT * FROM payroll_lines WHERE period_id = ?", (p["id"],)):
            if ln["estimate_cents"] is None:
                continue
            total += ln["estimate_cents"] + (ln["adjustment_cents"] or 0) + items.get(ln["employee_id"], {}).get("add_total", 0)
    return total


def figures(conn, branches: list[dict], start: date, end: date) -> dict:
    s, e = start.isoformat(), end.isoformat()
    rep = finance_report.build(conn, branches, s, e)
    st = finance_report.statement(conn, branches, s, e, rep["branch_totals"])
    gross = st["gross_total"]
    lines: dict[str, dict[str, int]] = {g: {} for g in GROUPS}
    for r in st["rows"]:
        g = GROUP_OF.get(r["label"], "Administrative & marketing")
        lines[g][r["label"]] = lines[g].get(r["label"], 0) + r["total"]
    runs = _payroll_runs(conn, [b["id"] for b in branches], s, e)
    if runs:
        lines["Payroll"]["Payroll runs (approved)"] = runs
    groups = {g: {"lines": sorted(v.items(), key=lambda x: -x[1]), "total": sum(v.values())} for g, v in lines.items()}
    for v in groups.values():
        v["pct"] = round(100 * v["total"] / gross, 1) if gross else None
    payroll = groups["Payroll"]["total"]
    expenses = sum(v["total"] for g, v in groups.items() if g != "Payroll")
    net = gross - expenses - payroll
    pct = lambda v: round(100 * v / gross, 1) if gross else None  # noqa: E731
    return {"start": start, "end": end, "gross": gross, "expenses": expenses, "payroll": payroll, "net": net, "groups": groups,
            "margin": pct(net), "supply_pct": pct(groups["Clinical supplies & lab"]["total"]), "payroll_pct": pct(payroll),
            "double_payroll": bool(runs and lines["Payroll"].get("Salaries & wages")), "drafts": st["drafts_total"]}


def _chg(now: int, before: int):
    return None if not before else round(100 * (now - before) / abs(before))


def takeaways(cur: dict, prev: dict, month_label: str, prev_label: str) -> list[str]:
    """Two or three plain sentences about the month, from the numbers only."""
    out = []
    peso = lambda c: f"₱{c / 100:,.0f}"  # noqa: E731
    if not cur["gross"] and not cur["expenses"] and not cur["payroll"]:
        return [f"Nothing is recorded for {month_label} yet."]
    g = _chg(cur["gross"], prev["gross"])
    if cur["net"] >= 0:
        out.append(f"{month_label} made a net profit of {peso(cur['net'])}" + (f" ({cur['margin']}% of collections)" if cur["margin"] is not None else "")
                   + (f"; collections were {'up' if g >= 0 else 'down'} {abs(g)}% on {prev_label}." if g is not None else "."))
    else:
        out.append(f"{month_label} ran at a loss of {peso(-cur['net'])}: costs were higher than the {peso(cur['gross'])} collected"
                   + (f" (collections {'up' if g >= 0 else 'down'} {abs(g)}% on {prev_label})." if g is not None else "."))
    groups = [(k, v["total"]) for k, v in cur["groups"].items() if v["total"]]
    if groups:
        k, v = max(groups, key=lambda x: x[1])
        pv = prev["groups"][k]["total"]
        c = _chg(v, pv)
        out.append(f"The biggest cost was {k.lower()} at {peso(v)}" + (f" ({round(100 * v / cur['gross'])}% of collections)" if cur["gross"] else "")
                   + (f", {'up' if c >= 0 else 'down'} {abs(c)}% on {prev_label}." if c is not None and c != 0 else "."))
    if cur["margin"] is not None and prev["margin"] is not None:
        d = round(cur["margin"] - prev["margin"], 1)
        if abs(d) >= 1:
            out.append(f"Net profit margin {'improved' if d > 0 else 'fell'} by {abs(d)} points ({prev['margin']}% → {cur['margin']}%).")
    if cur["drafts"]:
        out.append(f"{peso(cur['drafts'])} of expenses are recorded but not posted yet; they are included above.")
    return out[:4]

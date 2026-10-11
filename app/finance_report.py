"""Financial report: collections grouped by where the money went (Cash, GCash, Bank transfer – BDO, ...),
per branch, and what landed in each bank account / e-wallet (incl. cash deposited from the bank deposit records)."""
from __future__ import annotations

from .billing import BANK_METHODS, CREDIT_METHOD, PAYMENT_METHODS, banks


def _label(method: str, account: str) -> str:
    label = PAYMENT_METHODS.get(method, method)
    if method in BANK_METHODS:
        return f"{label} – {account or 'bank not set'}"
    return label


def _order(conn):
    """Category order: as in the payment form."""
    out = []
    for k, label in PAYMENT_METHODS.items():
        if k in BANK_METHODS:
            out += [f"{label} – {b}" for b in banks(conn)] + [f"{label} – bank not set"]
        elif k != CREDIT_METHOD:
            out.append(label)
    return out


def build(conn, branches: list[dict], start: str, end: str) -> dict:
    ids = [b["id"] for b in branches]
    marks = ",".join("?" * len(ids)) or "NULL"
    cats: dict[str, dict] = {}

    def add(label, bid, field, amt):
        c = cats.setdefault(label, {"collected": {}, "refunds": {}})
        c[field][bid] = c[field].get(bid, 0) + amt

    for r in conn.all(f"SELECT branch_id, kind, method, account, SUM(amount_cents) AS amt FROM payments WHERE status = 'valid' AND method != ? "
                      f"AND branch_id IN ({marks}) AND substr(received_at, 1, 10) BETWEEN ? AND ? GROUP BY branch_id, kind, method, account",
                      [CREDIT_METHOD, *ids, start, end]):
        add(_label(r["method"], r["account"]), r["branch_id"], "collected" if r["kind"] == "payment" else "refunds", r["amt"])
    for r in conn.all(f"SELECT branch_id, kind, method, account, SUM(amount_cents) AS amt FROM patient_credits WHERE status = 'valid' "
                      f"AND kind IN ('deposit', 'refund') AND branch_id IN ({marks}) AND entry_date BETWEEN ? AND ? "
                      "GROUP BY branch_id, kind, method, account", [*ids, start, end]):
        add(_label(r["method"], r["account"]), r["branch_id"], "collected" if r["kind"] == "deposit" else "refunds", r["amt"])
    order = _order(conn)
    rows = []
    for label in sorted(cats, key=lambda x: (order.index(x) if x in order else 999, x)):
        c = cats[label]
        net = {b: c["collected"].get(b, 0) - c["refunds"].get(b, 0) for b in ids}
        rows.append({"label": label, "net": net, "total": sum(net.values()), "collected": sum(c["collected"].values()),
                     "refunds": sum(c["refunds"].values())})
    branch_totals = {b: sum(r["net"][b] for r in rows) for b in ids}

    # Where the money is: bank accounts and GCash (transfers + cash deposited), and cash not yet deposited.
    dep = {}
    for r in conn.all(f"SELECT bank, SUM(amount_cents) AS amt FROM cash_deposits WHERE status = 'ok' AND branch_id IN ({marks}) "
                      "AND deposit_date BETWEEN ? AND ? GROUP BY bank", [*ids, start, end]):
        dep[r["bank"]] = r["amt"]
    by_label = {r["label"]: r["total"] for r in rows}
    accounts = []
    for name in ["GCash", *banks(conn)]:
        direct = by_label.get("GCash", 0) if name == "GCash" else sum(v for k, v in by_label.items()
                                                                        if any(k == f"{PAYMENT_METHODS[m]} – {name}" for m in BANK_METHODS))
        accounts.append({"name": name, "direct": direct, "cash_deposited": dep.pop(name, 0)})
    for name, amt in sorted(dep.items()):    # deposits into a bank that isn't on the list
        accounts.append({"name": name or "Bank not set", "direct": 0, "cash_deposited": amt})
    for a in accounts:
        a["total"] = a["direct"] + a["cash_deposited"]
    cash_net = by_label.get("Cash", 0)
    deposited = sum(a["cash_deposited"] for a in accounts)
    return {"rows": rows, "branch_totals": branch_totals, "total": sum(branch_totals.values()), "accounts": accounts,
            "cash_net": cash_net, "cash_deposited": deposited}


def lab_build(conn, lab_ids: list[int], start: str, end: str) -> dict:
    """Laboratory payments received, by where the money went, split into outside clinics and our own branches."""
    from .views.lab_works import LAB_BANK_METHODS, METHODS, lab_pay_label
    marks = ",".join("?" * len(lab_ids)) or "NULL"
    cats: dict[str, dict] = {}
    for r in conn.all(f"SELECT p.method, p.account, (SELECT branch_id FROM lab_clients WHERE id = i.client_id) AS branch_id, "
                      f"SUM(p.amount_cents) AS amt FROM lab_payments p JOIN lab_invoices i ON i.id = p.invoice_id "
                      f"WHERE p.status = 'ok' AND i.lab_id IN ({marks}) AND p.received_on BETWEEN ? AND ? "
                      "GROUP BY p.method, p.account, branch_id IS NULL", [*lab_ids, start, end]):
        c = cats.setdefault(lab_pay_label(r["method"], r["account"]), {"outside": 0, "branch": 0})
        c["branch" if r["branch_id"] else "outside"] += r["amt"]
    order = []
    for k, label in METHODS.items():
        order += [f"{label} – {b}" for b in banks(conn)] + [f"{label} – bank not set"] if k in LAB_BANK_METHODS else [label]
    rows = [{"label": k, **v, "total": v["outside"] + v["branch"]}
            for k, v in sorted(cats.items(), key=lambda x: (order.index(x[0]) if x[0] in order else 999, x[0]))]
    by_label = {r["label"]: r["total"] for r in rows}
    accounts = [{"name": "GCash", "total": by_label.get("GCash", 0)}]
    accounts += [{"name": b, "total": by_label.get(f"{METHODS['bank']} – {b}", 0)} for b in banks(conn)]
    return {"rows": rows, "outside": sum(r["outside"] for r in rows), "branch": sum(r["branch"] for r in rows),
            "total": sum(r["total"] for r in rows), "accounts": accounts, "cash": by_label.get("Cash", 0)}


def statement(conn, branches: list[dict], start: str, end: str, gross: dict[int, int], posted_only: bool = False) -> dict:
    """Gross collections less expenses, per branch: expenses by category (Rent, Electricity, ...), lab fees on bills
    and dentist commissions (counted the same way as the daily collection report)."""
    from datetime import date, timedelta
    from .daily_report import dentist_commissions
    from .billing import lab_share
    ids = [b["id"] for b in branches]
    marks = ",".join("?" * len(ids)) or "NULL"
    lines: dict[str, dict[int, int]] = {}
    drafts = {b: 0 for b in ids}
    for r in conn.all(f"SELECT branch_id, category, status, SUM(amount_cents) AS amt FROM expenses WHERE status != 'void' "
                      f"AND branch_id IN ({marks}) AND expense_date BETWEEN ? AND ? GROUP BY branch_id, category, status", [*ids, start, end]):
        if r["status"] == "draft":
            drafts[r["branch_id"]] += r["amt"]
            if posted_only:
                continue
        lines.setdefault(r["category"], {b: 0 for b in ids})[r["branch_id"]] += r["amt"]
    from .views.expenses import CATEGORIES
    rows = [{"label": c, "by": v, "total": sum(v.values())}
            for c, v in sorted(lines.items(), key=lambda x: (CATEGORIES.index(x[0]) if x[0] in CATEGORIES else 99, x[0]))]
    lab = {b: 0 for b in ids}
    for r in conn.all(f"SELECT p.branch_id, p.amount_cents, i.total_cents, (SELECT COALESCE(SUM(lab_fee_cents), 0) FROM invoice_items "
                      f"WHERE invoice_id = i.id) AS lab_fee FROM payments p JOIN invoices i ON i.id = p.invoice_id WHERE p.status = 'valid' "
                      f"AND p.kind = 'payment' AND p.branch_id IN ({marks}) AND substr(p.received_at, 1, 10) BETWEEN ? AND ?", [*ids, start, end]):
        lab[r["branch_id"]] += lab_share(r["amount_cents"], r["lab_fee"], r["total_cents"])
    if any(lab.values()):
        rows.append({"label": "Lab fees (on bills paid)", "by": lab, "total": sum(lab.values())})
    comm = {b: 0 for b in ids}
    d, last = date.fromisoformat(start), date.fromisoformat(end)
    while d <= last and (last - date.fromisoformat(start)).days <= 400:
        for b in ids:
            comm[b] += sum(dentist_commissions(conn, b, d.isoformat()).values())
        d += timedelta(days=1)
    if any(comm.values()):
        rows.append({"label": "Dentist commissions", "by": comm, "total": sum(comm.values())})
    exp = {b: sum(r["by"][b] for r in rows) for b in ids}
    net = {b: gross.get(b, 0) - exp[b] for b in ids}
    return {"rows": rows, "expenses": exp, "expenses_total": sum(exp.values()), "net": net, "net_total": sum(net.values()),
            "gross": gross, "gross_total": sum(gross.get(b, 0) for b in ids), "drafts": drafts, "drafts_total": sum(drafts.values())}

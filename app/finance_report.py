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

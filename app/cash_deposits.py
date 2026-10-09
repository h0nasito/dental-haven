"""Cash book per branch: cash collected minus cash paid out, minus what was deposited in the bank = cash on hand.

Cash in: patient payments and advance deposits paid in cash. Cash out: cash refunds and expenses paid in cash
(not voided). Bank deposits are recorded by the cashier with the deposit slip. Counting starts on the date in the
setting deposits.since (set when this feature was installed), so older history doesn't show as undeposited."""
from __future__ import annotations

from datetime import date, timedelta

from . import settings


def since(conn) -> str:
    return settings.get("deposits.since", conn) or date.today().isoformat()


def cash_days(conn, branch_id: int, start: str, end: str) -> dict[str, dict]:
    """{day: {"in", "refunds", "expenses", "net"}} for days with any cash movement."""
    days: dict[str, dict] = {}

    def row(d):
        return days.setdefault(d, {"in": 0, "refunds": 0, "expenses": 0, "deposited": 0})

    for r in conn.all("SELECT substr(received_at, 1, 10) AS d, kind, SUM(amount_cents) AS amt FROM payments WHERE status = 'valid' "
                      "AND method = 'cash' AND branch_id = ? AND substr(received_at, 1, 10) BETWEEN ? AND ? GROUP BY d, kind",
                      (branch_id, start, end)):
        row(r["d"])["in" if r["kind"] == "payment" else "refunds"] += r["amt"]
    for r in conn.all("SELECT entry_date AS d, kind, SUM(amount_cents) AS amt FROM patient_credits WHERE status = 'valid' AND method = 'cash' "
                      "AND kind IN ('deposit', 'refund') AND branch_id = ? AND entry_date BETWEEN ? AND ? GROUP BY d, kind",
                      (branch_id, start, end)):
        row(r["d"])["in" if r["kind"] == "deposit" else "refunds"] += r["amt"]
    for r in conn.all("SELECT expense_date AS d, SUM(amount_cents) AS amt FROM expenses WHERE status != 'void' AND method = 'cash' "
                      "AND branch_id = ? AND expense_date BETWEEN ? AND ? GROUP BY d", (branch_id, start, end)):
        row(r["d"])["expenses"] += r["amt"]
    for r in conn.all("SELECT deposit_date AS d, SUM(amount_cents) AS amt FROM cash_deposits WHERE status = 'ok' "
                      "AND branch_id = ? AND deposit_date BETWEEN ? AND ? GROUP BY d", (branch_id, start, end)):
        row(r["d"])["deposited"] += r["amt"]
    for v in days.values():
        v["net"] = v["in"] - v["refunds"] - v["expenses"]
    return days


def net_cash(conn, branch_id: int, start: str, end: str) -> int:
    """Cash collected minus cash paid out from start to end (inclusive)."""
    if not start or not end or start > end:
        return 0
    return sum(v["net"] for v in cash_days(conn, branch_id, start, end).values())


def on_hand(conn, branch_id: int, upto: str | None = None) -> int:
    """Cash not yet deposited at the end of `upto` (default today)."""
    upto = upto or date.today().isoformat()
    s = since(conn)
    if upto < s:
        return 0
    return sum(v["net"] - v["deposited"] for v in cash_days(conn, branch_id, s, upto).values())


def book(conn, branch_id: int, start: date, end: date) -> dict:
    """Day-by-day cash book with an opening balance and a running balance."""
    s = since(conn)
    first = max(start.isoformat(), s)
    opening = on_hand(conn, branch_id, (date.fromisoformat(first) - timedelta(days=1)).isoformat()) if first > s else 0
    days = cash_days(conn, branch_id, first, end.isoformat()) if first <= end.isoformat() else {}
    rows, bal = [], opening
    for d in sorted(days):
        v = days[d]
        bal += v["net"] - v["deposited"]
        rows.append({"day": d, **v, "balance": bal})
    tot = {k: sum(r[k] for r in rows) for k in ("in", "refunds", "expenses", "net", "deposited")}
    return {"opening": opening, "rows": rows, "closing": bal, "totals": tot, "since": s}

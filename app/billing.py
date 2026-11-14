"""Invoice arithmetic and numbering. Tax is off by default and fully configurable."""
from __future__ import annotations

from . import settings
from .util import today

CREDIT_METHOD = "account_credit"  # payments made from a patient's account credit (not new money received)
LEGACY_METHOD = "mymeds"          # bills marked paid in MyMedsPH, brought over when old bills are converted (method unknown)

PAYMENT_METHODS = {
    "cash": "Cash", "gcash": "GCash", "maya": "Maya", "card": "Debit/credit card", "bank_transfer": "Bank transfer",
    "check": "Check", "hmo": "HMO / insurance", "other": "Other",
}

DEFAULT_BANKS = ["BDO", "BPI", "Security Bank", "RCBC", "AUB"]
PROOF_METHODS = ("gcash", "maya", "card", "bank_transfer", "check", "hmo", "other")   # these come with a proof of payment
MAX_PROOFS = 4
BANK_METHODS = ("bank_transfer",)          # these ask which bank account the money went into


def banks(conn=None) -> list[str]:
    """The clinic's bank accounts (System setting finance.banks)."""
    from . import settings
    v = settings.get("finance.banks", conn)
    return [b for b in (v or DEFAULT_BANKS) if b]


def pay_options(conn=None, include_credit=False) -> list[tuple[str, str]]:
    """Payment type choices: 'Cash', 'GCash', 'Bank transfer – BDO', ... (value 'method' or 'method:Bank')."""
    out = []
    for k, label in PAYMENT_METHODS.items():
        if k in BANK_METHODS:
            out += [(f"{k}:{b}", f"{label} – {b}") for b in banks(conn)]
        else:
            out.append((k, label))
    return out


def parse_pay(value: str, conn=None) -> tuple[str, str] | None:
    """'bank_transfer:BDO' -> ('bank_transfer', 'BDO'); 'gcash' -> ('gcash', 'GCash'); invalid -> None."""
    method, _, account = (value or "").partition(":")
    if method not in PAYMENT_METHODS or method == CREDIT_METHOD:
        return None
    if method in BANK_METHODS:
        if account not in banks(conn):
            return None
        return method, account
    return method, "GCash" if method == "gcash" else ""


def pay_label(method: str, account: str = "") -> str:
    label = PAYMENT_METHODS.get(method, "Account credit" if method == CREDIT_METHOD else
                                "Paid in MyMedsPH" if method == LEGACY_METHOD else method)
    return f"{label} – {account}" if account and method in BANK_METHODS else label


def compute_totals(items: list[dict], invoice_discount: int, conn=None) -> dict:
    subtotal = sum(int(i["amount_cents"]) for i in items)
    discount = max(0, min(int(invoice_discount or 0), subtotal))
    net = subtotal - discount
    tax = 0
    total = net
    if settings.get("invoice.tax_enabled", conn):
        rate_bp = int(settings.get("invoice.tax_rate_bp", conn) or 0)
        if settings.get("invoice.tax_inclusive", conn):
            tax = round(net - net * 10000 / (10000 + rate_bp)) if rate_bp else 0
        else:
            tax = round(net * rate_bp / 10000)
            total = net + tax
    return {"subtotal_cents": subtotal, "discount_cents": discount, "tax_cents": tax, "total_cents": total}


def line_amount(qty: int, unit_cents: int, discount_cents: int) -> int:
    return max(0, qty * unit_cents - discount_cents)


def next_invoice_number(conn, branch_id: int) -> str:
    """Allocate the next number for a branch. Call inside a transaction."""
    seq = conn.one("SELECT * FROM invoice_sequences WHERE branch_id = ?", (branch_id,))
    if not seq:
        b = conn.one("SELECT slug FROM branches WHERE id = ?", (branch_id,))
        prefix = (b["slug"][:3] if b else "INV").upper()
        conn.execute("INSERT INTO invoice_sequences (branch_id, prefix, next_no) VALUES (?, ?, 1)", (branch_id, prefix))
        seq = {"prefix": prefix, "next_no": 1}
    fmt = settings.get("invoice.number_format", conn) or "{prefix}-{year}-{seq:05d}"
    number = fmt.format(prefix=seq["prefix"], year=today().year, seq=seq["next_no"])
    conn.execute("UPDATE invoice_sequences SET next_no = next_no + 1 WHERE branch_id = ?", (branch_id,))
    return number


def paid_amount(conn, invoice_id: int) -> int:
    return int(conn.scalar(
        "SELECT COALESCE(SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END), 0) "
        "FROM payments WHERE invoice_id = ? AND status = 'valid'", (invoice_id,)) or 0)


def payment_state(total: int, paid: int, status: str) -> str:
    if status != "issued":
        return status
    if paid <= 0:
        return "unpaid"
    if paid < total:
        return "partial"
    return "paid"


def credit_balance(conn, patient_id: int) -> int:
    return int(conn.scalar(
        "SELECT COALESCE(SUM(CASE WHEN kind = 'deposit' THEN amount_cents ELSE -amount_cents END), 0) "
        "FROM patient_credits WHERE patient_id = ? AND status = 'valid'", (patient_id,)) or 0)


def mark_xray_lines(conn) -> None:
    """Flag bill lines that are X-rays (invoice_items.xray = 1), so collection reports can leave them out: X-rays are
    their own section with their own collections and deposits. Only lines not checked yet (new or edited)."""
    rows = conn.all("SELECT id, description FROM invoice_items WHERE xray IS NULL")
    if not rows:
        return
    from .views.xray import type_for
    for r in rows:
        conn.execute("UPDATE invoice_items SET xray = ? WHERE id = ?", (1 if type_for(conn, r["description"]) else 0, r["id"]))


def clinic_share(conn, alias: str = "p", amount: str = "", invoice_id: str = "") -> str:
    """SQL for the part of a payment that is for the clinic's work, not X-rays on the same bill: each payment is shared
    over its bill's lines in proportion, and the X-ray lines' share is left out. Use as SUM({clinic_share}) etc."""
    mark_xray_lines(conn)
    a = alias
    amount, invoice_id = amount or f"{a}.amount_cents", invoice_id or f"{a}.invoice_id"
    return (f"CAST(ROUND({amount} * (SELECT CASE WHEN COALESCE(SUM(MAX(ii.amount_cents, 0)), 0) > 0 "
            f"THEN 1.0 - 1.0 * SUM(CASE WHEN ii.xray = 1 THEN MAX(ii.amount_cents, 0) ELSE 0 END) / SUM(MAX(ii.amount_cents, 0)) ELSE 1.0 END "
            f"FROM invoice_items ii WHERE ii.invoice_id = {invoice_id})) AS INTEGER)")


def collections(conn, branch_ids: list[int], start: str, end: str) -> dict:
    """Money actually received in the period: payments (excluding account-credit applications) plus
    patient deposits, minus refunds of either. Account credit used on a bill is not counted twice."""
    if not branch_ids:
        return {"received": 0, "refunded": 0, "net": 0}
    marks = ",".join("?" for _ in branch_ids)
    amt = clinic_share(conn)          # X-ray lines on bills are not the clinic's collections
    pay = conn.one(
        f"SELECT COALESCE(SUM(CASE WHEN p.kind='payment' THEN {amt} ELSE 0 END),0) AS received, "
        f"COALESCE(SUM(CASE WHEN p.kind='refund' THEN {amt} ELSE 0 END),0) AS refunded FROM payments p "
        f"WHERE p.status='valid' AND p.method != ? AND p.branch_id IN ({marks}) AND p.received_at BETWEEN ? AND ?",
        [CREDIT_METHOD, *branch_ids, start, end])
    dep = conn.one(
        "SELECT COALESCE(SUM(CASE WHEN kind='deposit' THEN amount_cents ELSE 0 END),0) AS received, "
        "COALESCE(SUM(CASE WHEN kind='refund' THEN amount_cents ELSE 0 END),0) AS refunded FROM patient_credits "
        f"WHERE status='valid' AND branch_id IN ({marks}) AND entry_date BETWEEN ? AND ?", [*branch_ids, start, end])
    received = pay["received"] + dep["received"]
    refunded = pay["refunded"] + dep["refunded"]
    return {"received": received, "refunded": refunded, "net": received - refunded, "deposits": dep["received"]}


def commission_dentists(conn) -> list[dict]:
    """Every dentist who can earn commission, with their usual % (to pre-fill the cashier's commission): logins with the
    Dentist role, a super admin who is also a dentist, and active employees with a dentist position even without a login
    (e.g. an associate covering at another branch). The option value is the login id, or "e<employee id>" without one."""
    from .payroll import dentist_rates
    from .util import today
    out, seen = [], set()
    for d in conn.all("SELECT u.id, u.name, u.role, u.license_no, e.id AS emp_id, e.position FROM users u LEFT JOIN employees e ON e.user_id = u.id "
                      "WHERE u.active = 1 AND (u.role = 'dentist' OR (u.role = 'super_admin' AND e.id IS NOT NULL AND "
                      "(COALESCE(u.license_no, '') != '' OR LOWER(COALESCE(e.position, '')) LIKE '%dentist%'))) ORDER BY u.name"):
        r = dentist_rates(conn, d["emp_id"], today().isoformat()) if d["emp_id"] else None
        out.append({"id": d["id"], "name": d["name"], "rate_bp": r["commission_bp"] if r else None, "has_employee": bool(d["emp_id"])})
        if d["emp_id"]:
            seen.add(d["emp_id"])
    for e in conn.all("SELECT e.id, e.full_name FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.active = 1 "
                      "AND LOWER(COALESCE(e.position, '')) LIKE '%dentist%' AND (e.user_id IS NULL OR u.active = 0) ORDER BY e.full_name"):
        if e["id"] in seen:
            continue
        r = dentist_rates(conn, e["id"], today().isoformat())
        out.append({"id": f"e{e['id']}", "name": e["full_name"], "rate_bp": r["commission_bp"] if r else None, "has_employee": True})
    out.sort(key=lambda d: (d["name"] or "").lower())
    return out


def commission_target(conn, raw) -> tuple[int | None, int | None]:
    """The dentist picked in a commission box: (login id, employee id). "e12" = employee 12 without a login."""
    raw = (str(raw or "")).strip()
    if raw.startswith("e") and raw[1:].isdigit():
        e = conn.one("SELECT id, user_id FROM employees WHERE id = ?", (int(raw[1:]),))
        return (e["user_id"], e["id"]) if e else (None, None)
    if raw.isdigit():
        e = conn.one("SELECT id FROM employees WHERE user_id = ?", (int(raw),))
        return int(raw), (e["id"] if e else None)
    return None, None


def invoice_commission_info(conn, inv) -> dict:
    """The dentist most lines on this bill belong to (or the visit's dentist), and the bill's total lab fees."""
    row = conn.one("SELECT dentist_id, COUNT(*) AS n FROM invoice_items WHERE invoice_id = ? AND dentist_id IS NOT NULL "
                   "GROUP BY dentist_id ORDER BY n DESC LIMIT 1", (inv["id"],))
    dentist = row["dentist_id"] if row else None
    if not dentist and inv["appointment_id"]:
        a = conn.one("SELECT dentist_id FROM appointments WHERE id = ?", (inv["appointment_id"],))
        dentist = a["dentist_id"] if a else None
    lab = conn.scalar("SELECT COALESCE(SUM(lab_fee_cents), 0) FROM invoice_items WHERE invoice_id = ?", (inv["id"],)) or 0
    # Bill lines with a dentist (and maybe a commission set on the line): the payment's commission follows the lines, so the
    # cashier doesn't enter it again; several dentists are split. Preview for the whole bill, scaled to the amount paid.
    n_dent = conn.scalar("SELECT COUNT(DISTINCT dentist_id) FROM invoice_items WHERE invoice_id = ? AND dentist_id IS NOT NULL", (inv["id"],)) or 0
    custom = conn.scalar("SELECT COUNT(*) FROM invoice_items WHERE invoice_id = ? AND dentist_id IS NOT NULL "
                         "AND commission_mode IN ('percent', 'amount')", (inv["id"],)) or 0
    split = split_commission(conn, inv, inv["total_cents"]) if (n_dent or custom) and inv["total_cents"] else []
    no_dentist = conn.scalar("SELECT COUNT(*) FROM invoice_items WHERE invoice_id = ? AND dentist_id IS NULL AND COALESCE(xray, 0) = 0 "
                             "AND amount_cents > 0", (inv["id"],)) or 0
    return {"dentist_id": dentist, "lab_fee_cents": int(lab), "split": split, "split_no_dentist": no_dentist}


def no_commission_names(conn) -> set[str]:
    """Upper-case names of price-list items marked "No dentist commission" (e.g. ASEPSIS FEE)."""
    return {r["name"].strip().upper() for r in conn.all("SELECT name FROM fee_schedule WHERE no_commission = 1")}


def line_no_commission(line, names: set[str]) -> bool:
    """A bill line earns no commission when it's a "no commission" price-list item and the line itself doesn't set one."""
    if (line["commission_mode"] or "auto") != "auto" or not names:
        return False
    return (line["description"] or "").split(" · ")[0].strip().upper() in names


def commission_free_cents(conn, invoice_id: int) -> int:
    """The bill's amount on lines that earn no commission (e.g. asepsis fee), for the single-dentist % of a payment."""
    names = no_commission_names(conn)
    if not names:
        return 0
    return sum(max(0, l["amount_cents"]) for l in conn.all("SELECT description, amount_cents, commission_mode FROM invoice_items WHERE invoice_id = ?",
                                                           (invoice_id,)) if line_no_commission(l, names))


def split_commission(conn, inv, pay_cents: int, first: bool | None = None) -> list[dict]:
    """A payment's dentist commission split by bill line: each line's dentist earns on that line's share of the payment
    (after its lab fee share), at the % or amount set on the line, else the dentist's rate for that service, else their
    usual rate. A fixed amount on a line is paid once, in full, with the first payment that records the split commission
    (later payments add nothing for it); on a line linked to a lab case it waits until the case is installed.
    Each row's "fixed" is that part, "fixed_items" which lines it pays, "waiting" lines held for installation, and
    "already" the commission already recorded for that dentist on this bill. The rest follows the amount paid.
    (first is no longer used.)
    X-ray lines (own section) and lines without a dentist earn nothing here. One row per dentist."""
    from .payroll import dentist_rates
    from .util import today
    mark_xray_lines(conn)
    lines = conn.all("SELECT ii.*, u.name AS dentist_name, e.id AS emp_id FROM invoice_items ii LEFT JOIN users u ON u.id = ii.dentist_id "
                     "LEFT JOIN employees e ON e.user_id = ii.dentist_id WHERE ii.invoice_id = ? ORDER BY ii.id", (inv["id"],))
    tot = sum(max(0, l["amount_cents"]) for l in lines)
    if pay_cents < 0 or (pay_cents > 0 and not tot):
        return []                                  # pay_cents 0: only the fixed amounts (e.g. confirming a ₱0 visit)
    import json
    credited: dict[int, int] = {}
    already: dict[int, int] = {}
    for c in conn.all("SELECT employee_id, amount_cents, fixed_items FROM dentist_commissions WHERE invoice_id = ? AND status = 'valid'", (inv["id"],)):
        already[c["employee_id"]] = already.get(c["employee_id"], 0) + (c["amount_cents"] or 0)
        try:
            for k, v in (json.loads(c["fixed_items"]) if c["fixed_items"] else {}).items():
                credited[int(k)] = credited.get(int(k), 0) + int(v)
        except (ValueError, TypeError, AttributeError):
            pass
    free_names = no_commission_names(conn)
    installed = {r["id"]: bool(r["installed_on"]) for r in conn.all(
        "SELECT lc.id, lc.installed_on FROM lab_cases lc JOIN invoice_items ii ON ii.lab_case_id = lc.id WHERE ii.invoice_id = ?", (inv["id"],))}
    out: dict[int, dict] = {}
    rates: dict[int, tuple] = {}
    for l in lines:
        amt = max(0, l["amount_cents"])
        mode = l["commission_mode"] or "auto"
        fixed = mode == "amount" and l["commission_cents"] is not None
        # a free line (₱0, e.g. a cleaning included in braces) still earns a fixed amount typed on it
        if not l["dentist_id"] or l["xray"] == 1 or (not amt and not fixed) or line_no_commission(l, free_names):
            continue
        share = pay_cents * amt / tot if tot else 0
        lab = min(share, share * (l["lab_fee_cents"] or 0) / amt) if l["lab_fee_cents"] and amt else 0
        base = share - lab
        wait = False
        if fixed:
            bp, comm = None, 0.0
            fixed_c = max(0, l["commission_cents"] - credited.get(l["id"], 0))
            if fixed_c and l["lab_case_id"] and not installed.get(l["lab_case_id"], True):
                fixed_c, wait = 0, True
        else:
            if mode == "percent" and l["commission_bp"] is not None:
                bp = l["commission_bp"]
            else:
                if l["emp_id"] and l["emp_id"] not in rates:
                    r = dentist_rates(conn, l["emp_id"], today().isoformat())
                    svc = {x["service_id"]: x["commission_bp"] for x in conn.all("SELECT * FROM dentist_service_rates WHERE employee_id = ?", (l["emp_id"],))}
                    rates[l["emp_id"]] = ((r["commission_bp"] or 0) if r else 0, svc)
                default, svc = rates.get(l["emp_id"], (0, {}))
                bp = svc.get(l["service_id"], default)
            comm = base * bp / 10000
        row = out.setdefault(l["dentist_id"], {"user_id": l["dentist_id"], "name": l["dentist_name"], "emp_id": l["emp_id"], "lines": [],
                                               "base": 0.0, "amount": 0.0, "fixed": 0, "fixed_items": {}, "waiting": [],
                                               "already": already.get(l["emp_id"], 0), "bps": set()})
        row["lines"].append((l["description"] or "").split(" · ")[0] + (f" #{l['tooth']}" if l["tooth"] else ""))
        row["base"] += base
        row["amount"] += comm + (fixed_c if fixed else 0)
        row["fixed"] += fixed_c if fixed else 0
        if fixed and fixed_c:
            row["fixed_items"][str(l["id"])] = fixed_c
        if wait:
            row["waiting"].append(row["lines"][-1])
        row["bps"].add(bp)
    res = []
    for row in out.values():
        bps = row.pop("bps")
        res.append({**row, "base": round(row["base"]), "amount": round(row["amount"]), "bp": next(iter(bps)) if len(bps) == 1 else None})
    return sorted(res, key=lambda r: r["name"] or "")


def lab_share(payment_cents: int, lab_fee_cents: int, total_cents: int) -> int:
    """The part of a payment that goes to the lab fee (in proportion to the bill), never more than the payment."""
    if not lab_fee_cents or not total_cents:
        return 0
    return min(payment_cents, round(payment_cents * lab_fee_cents / total_cents))

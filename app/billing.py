"""Invoice arithmetic and numbering. Tax is off by default and fully configurable."""
from __future__ import annotations

from . import settings
from .util import today

CREDIT_METHOD = "account_credit"  # payments made from a patient's account credit (not new money received)

PAYMENT_METHODS = {
    "cash": "Cash", "gcash": "GCash", "maya": "Maya", "card": "Debit/credit card", "bank_transfer": "Bank transfer",
    "check": "Check", "hmo": "HMO / insurance", "other": "Other",
}

DEFAULT_BANKS = ["BDO", "BPI", "Security Bank", "RCBC", "AUB"]
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
    label = PAYMENT_METHODS.get(method, "Account credit" if method == CREDIT_METHOD else method)
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


def collections(conn, branch_ids: list[int], start: str, end: str) -> dict:
    """Money actually received in the period: payments (excluding account-credit applications) plus
    patient deposits, minus refunds of either. Account credit used on a bill is not counted twice."""
    if not branch_ids:
        return {"received": 0, "refunded": 0, "net": 0}
    marks = ",".join("?" for _ in branch_ids)
    pay = conn.one(
        "SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE 0 END),0) AS received, "
        "COALESCE(SUM(CASE WHEN kind='refund' THEN amount_cents ELSE 0 END),0) AS refunded FROM payments "
        f"WHERE status='valid' AND method != ? AND branch_id IN ({marks}) AND received_at BETWEEN ? AND ?",
        [CREDIT_METHOD, *branch_ids, start, end])
    dep = conn.one(
        "SELECT COALESCE(SUM(CASE WHEN kind='deposit' THEN amount_cents ELSE 0 END),0) AS received, "
        "COALESCE(SUM(CASE WHEN kind='refund' THEN amount_cents ELSE 0 END),0) AS refunded FROM patient_credits "
        f"WHERE status='valid' AND branch_id IN ({marks}) AND entry_date BETWEEN ? AND ?", [*branch_ids, start, end])
    received = pay["received"] + dep["received"]
    refunded = pay["refunded"] + dep["refunded"]
    return {"received": received, "refunded": refunded, "net": received - refunded, "deposits": dep["received"]}


def commission_dentists(conn) -> list[dict]:
    """Active dentists with their current usual commission % (for pre-filling the cashier's commission)."""
    from .payroll import dentist_rates
    from .util import today
    out = []
    for d in conn.all("SELECT u.id, u.name, e.id AS emp_id FROM users u LEFT JOIN employees e ON e.user_id = u.id "
                      "WHERE u.role = 'dentist' AND u.active = 1 ORDER BY u.name"):
        r = dentist_rates(conn, d["emp_id"], today().isoformat()) if d["emp_id"] else None
        out.append({"id": d["id"], "name": d["name"], "rate_bp": r["commission_bp"] if r else None, "has_employee": bool(d["emp_id"])})
    return out


def invoice_commission_info(conn, inv) -> dict:
    """The dentist most lines on this bill belong to (or the visit's dentist), and the bill's total lab fees."""
    row = conn.one("SELECT dentist_id, COUNT(*) AS n FROM invoice_items WHERE invoice_id = ? AND dentist_id IS NOT NULL "
                   "GROUP BY dentist_id ORDER BY n DESC LIMIT 1", (inv["id"],))
    dentist = row["dentist_id"] if row else None
    if not dentist and inv["appointment_id"]:
        a = conn.one("SELECT dentist_id FROM appointments WHERE id = ?", (inv["appointment_id"],))
        dentist = a["dentist_id"] if a else None
    lab = conn.scalar("SELECT COALESCE(SUM(lab_fee_cents), 0) FROM invoice_items WHERE invoice_id = ?", (inv["id"],)) or 0
    return {"dentist_id": dentist, "lab_fee_cents": int(lab)}


def lab_share(payment_cents: int, lab_fee_cents: int, total_cents: int) -> int:
    """The part of a payment that goes to the lab fee (in proportion to the bill), never more than the payment."""
    if not lab_fee_cents or not total_cents:
        return 0
    return min(payment_cents, round(payment_cents * lab_fee_cents / total_cents))

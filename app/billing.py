"""Invoice arithmetic and numbering. Tax is off by default and fully configurable."""
from __future__ import annotations

from . import settings
from .util import today

CREDIT_METHOD = "account_credit"  # payments made from a patient's account credit (not new money received)

PAYMENT_METHODS = {
    "cash": "Cash", "gcash": "GCash", "maya": "Maya", "card": "Debit/credit card", "bank_transfer": "Bank transfer",
    "check": "Check", "hmo": "HMO / insurance", "other": "Other",
}


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

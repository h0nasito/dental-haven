from test_app import Base


class TestOverpaymentToCredit(Base):
    def _bill(self, number, amount):
        from app.util import now_str
        mal = self.branch("malolos")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": number, "issued_at": "2026-11-18",
                                            "subtotal_cents": amount, "discount_cents": 0, "tax_cents": 0, "total_cents": amount, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Cleaning", "qty": 1, "unit_price_cents": amount,
                                           "discount_cents": 0, "amount_cents": amount})
        return inv, pid, mal

    def _credit(self, pid):
        return self.conn.scalar("SELECT COALESCE(SUM(CASE WHEN kind = 'deposit' THEN amount_cents WHEN kind = 'applied' THEN -amount_cents "
                                "ELSE -amount_cents END), 0) FROM patient_credits WHERE patient_id = ? AND status = 'valid'", (pid,))

    def test_extra_needs_the_tick_then_becomes_credit(self):
        inv, pid, mal = self._bill("OVR-1", 44720)
        before = self._credit(pid)
        a = self.login("admin")
        data = {"action": "multi", "method": "cash", "amount": "500", "received_at": "2026-11-18", "received_branch_id": mal,
                "not_signed_reason": "test"}
        page = a.post(f"/staff/invoices/{inv}/payments", data=data, follow_redirects=True).data.decode()
        self.assertIn("Keep the extra as the patient", page)
        self.assertIsNone(self.q("SELECT id FROM payments WHERE invoice_id = ?", (inv,)))
        a.post(f"/staff/invoices/{inv}/payments", data={**data, "extra_to_credit": "1"})
        self.assertEqual(self.conn.scalar("SELECT SUM(amount_cents) FROM payments WHERE invoice_id = ? AND status = 'valid'", (inv,)), 44720)
        c = self.q("SELECT * FROM patient_credits WHERE invoice_id = ? AND kind = 'deposit'", (inv,))
        self.assertEqual((c["amount_cents"], c["method"], c["branch_id"]), (5280, "cash", mal))
        self.assertEqual(self._credit(pid) - before, 5280)
        # the whole ₱500 cash counts in the day's cash for the deposit
        from app.cash_deposits import net_cash
        with self.app.app_context():
            self.assertGreaterEqual(net_cash(self.conn, mal, "2026-11-18", "2026-11-18"), 50000)

    def test_split_lines_fill_the_bill_first(self):
        inv, pid, mal = self._bill("OVR-2", 100000)
        a = self.login("admin")
        a.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash", "gcash"], "amount": ["800", "300"],
                                                        "received_at": "2026-11-18", "received_branch_id": mal, "not_signed_reason": "t",
                                                        "extra_to_credit": "1"})
        rows = self.conn.all("SELECT method, amount_cents FROM payments WHERE invoice_id = ? ORDER BY id", (inv,))
        self.assertEqual([(r["method"], r["amount_cents"]) for r in rows], [("cash", 80000), ("gcash", 20000)])
        c = self.q("SELECT method, amount_cents FROM patient_credits WHERE invoice_id = ? AND kind = 'deposit'", (inv,))
        self.assertEqual((c["method"], c["amount_cents"]), ("gcash", 10000))

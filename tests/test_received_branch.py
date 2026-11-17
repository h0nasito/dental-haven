from test_app import Base


class TestReceivedBranchChoice(Base):
    def setUp(self):
        super().setUp()
        self.conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES ('receptionist', 'payments.add')")
        self.conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES ('receptionist', 'billing.view')")

    def _bill(self, branch, amount=432100):
        from app.util import now_str
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (branch,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": branch, "patient_id": pid, "status": "issued", "number": f"RB-{amount}",
                                            "issued_at": "2026-11-02", "subtotal_cents": amount, "discount_cents": 0, "tax_cents": 0,
                                            "total_cents": amount, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Cleaning", "qty": 1, "unit_price_cents": amount,
                                           "discount_cents": 0, "amount_cents": amount})
        return inv

    def test_single_branch_cashier_sees_and_uses_the_choice(self):
        mal, boc, gui = self.branch("malolos"), self.branch("bocaue"), self.branch("guiguinto")
        inv = self._bill(mal)
        r = self.login("reception.malolos")
        page = r.get(f"/staff/invoices/{inv}").data.decode()
        self.assertIn("Received at (branch)", page)
        self.assertIn(f'value="{gui}"', page.split('name="received_branch_id"')[1].split("</select>")[0])
        r.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": "cash", "amount": "1234", "received_at": "2026-11-02",
                                                        "received_branch_id": gui, "not_signed_reason": "test"})
        self.assertEqual(self.q("SELECT branch_id FROM payments WHERE invoice_id = ? AND status = 'valid'", (inv,))["branch_id"], gui)

    def test_other_branch_cashier_defaults_to_own_branch(self):
        mal, boc = self.branch("malolos"), self.branch("bocaue")
        inv = self._bill(mal, 432200)
        r = self.login("reception.bocaue")
        sel = r.get(f"/staff/invoices/{inv}").data.decode().split('name="received_branch_id"')[1].split("</select>")[0]
        self.assertIn(f'value="{boc}" selected', sel)
        r.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": "cash", "amount": "1111", "received_at": "2026-11-02",
                                                        "not_signed_reason": "test"})
        self.assertEqual(self.q("SELECT branch_id FROM payments WHERE invoice_id = ? AND status = 'valid'", (inv,))["branch_id"], boc)

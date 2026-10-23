"""MyMedsPH bills -> real bills: status meanings chosen by an admin, paid/unpaid, branch, undo, auto-convert on re-import."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestLegacyBills(Base):
    def setUp(self):
        from app.util import now_str
        self.conn.execute("DELETE FROM payments WHERE invoice_id IN (SELECT id FROM invoices WHERE legacy = 1)")
        self.conn.execute("DELETE FROM invoice_items WHERE invoice_id IN (SELECT id FROM invoices WHERE legacy = 1)")
        self.conn.execute("UPDATE legacy_bills SET invoice_id = NULL")
        self.conn.execute("DELETE FROM invoices WHERE legacy = 1")
        self.conn.execute("DELETE FROM legacy_bills")
        self.conn.execute("DELETE FROM settings WHERE key LIKE 'legacy.%'")
        import secrets
        b, tag = self.branch("malolos"), secrets.token_hex(3)
        self.p1 = self.conn.insert("patients", {"first_name": "Oldbill", "last_name": "Mmqt", "chart_no": f"DH-MQ1{tag}", "preferred_branch_id": b,
                                                "created_at": now_str(), "updated_at": now_str()})
        self.p2 = self.conn.insert("patients", {"first_name": "Shared", "last_name": "Mmqt", "chart_no": f"DH-MQ2{tag}", "preferred_branch_id": None,
                                                "created_at": now_str(), "updated_at": now_str()})
        rows = [(self.p1, "2025-03-02", "Oral prophylaxis (Mild)", 1, 80000, 0, 80000, "4"),
                (self.p1, "2025-03-02", "Restoration", 2, 100000, 20000, 180000, "4"),
                (self.p1, "2025-04-10", "Orthodontic Treatment", 1, 4500000, 0, 4500000, "2"),
                (self.p2, "2025-05-01", "Consultation", 1, 50000, 0, 50000, "4"),
                (self.p1, "2025-06-01", "Cancelled thing", 1, 10000, 0, 10000, "9")]
        for i, (pid, d, svc, q, up, disc, tot, st) in enumerate(rows):
            self.conn.insert("legacy_bills", {"patient_id": pid, "bill_date": d, "service": svc, "qty": q, "unit_price_cents": up,
                                              "discount_cents": disc, "total_cents": tot, "status_code": st, "legacy_key": f"mmqt-{tag}-{i}"})

    def test_convert_paid_unpaid_and_undo(self):
        c = self.login("admin")
        page = c.get("/staff/admin/import/bills").data.decode()
        for code in ("m_2", "m_4", "m_9"):
            self.assertIn(f'name="{code}"', page)
        r = c.post("/staff/admin/import/bills", data={"action": "convert", "m_4": "paid", "m_2": "unpaid", "m_9": "history",
                                                      "branch_id": self.branch("guiguinto")})
        self.assertEqual(r.status_code, 302)
        invs = self.conn.all("SELECT * FROM invoices WHERE legacy = 1 ORDER BY issued_at")
        self.assertEqual([(i["patient_id"], i["issued_at"][:10], i["total_cents"]) for i in invs],
                         [(self.p1, "2025-03-02", 260000), (self.p1, "2025-04-10", 4500000), (self.p2, "2025-05-01", 50000)])
        self.assertEqual(invs[2]["branch_id"], self.branch("guiguinto"))      # shared patient -> chosen branch
        self.assertEqual(invs[0]["branch_id"], self.branch("malolos"))
        pays = {p["invoice_id"]: p for p in self.conn.all("SELECT * FROM payments WHERE invoice_id IN (?, ?, ?)", [i["id"] for i in invs])}
        self.assertEqual(pays[invs[0]["id"]]["amount_cents"], 260000)
        self.assertEqual(pays[invs[0]["id"]]["method"], "mymeds")
        self.assertNotIn(invs[1]["id"], pays)                                  # unpaid: balance to collect
        lines = self.conn.all("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invs[0]["id"],))
        self.assertEqual([(x["qty"], x["discount_cents"], x["amount_cents"], x["done_on"]) for x in lines],
                         [(1, 0, 80000, "2025-03-02"), (2, 20000, 180000, "2025-03-02")])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM legacy_bills WHERE invoice_id IS NULL")["n"], 1)   # status 9 stays history
        # the patient's Bills & Payment shows them; the history list only keeps the unconverted line
        page = c.get(f"/staff/patients/{self.p1}?tab=billing").data.decode()
        self.assertIn(invs[0]["number"], page)
        self.assertIn("Cancelled thing", page)
        self.assertNotIn(">Restoration<", page.split("Previous bills from MyMedsPH")[-1])
        # staff set a dentist on one bill; undo keeps that bill and removes the others
        doc = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        self.conn.execute("UPDATE invoice_items SET dentist_id = ? WHERE invoice_id = ?", (doc, invs[1]["id"]))
        c.post("/staff/admin/import/bills", data={"action": "undo"})
        left = [i["id"] for i in self.conn.all("SELECT id FROM invoices WHERE legacy = 1")]
        self.assertEqual(left, [invs[1]["id"]])
        self.assertIsNone(self.q("SELECT id FROM payments WHERE invoice_id = ?", (invs[0]["id"],)))
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM legacy_bills WHERE invoice_id IS NULL")["n"], 4)

    def test_later_import_converts_with_saved_choice(self):
        from app import legacy_billing as lb, settings
        settings.put(lb.MAP_KEY, {"4": "paid"}, None, self.conn)
        with self.app.app_context():
            from app.db import get_db
            with get_db().transaction():
                st = lb.convert(get_db(), lb.saved_map(get_db()), None, 1)
        self.assertEqual(st["bills"], 1)            # p1's paid bill; p2 has no branch and no default -> stays history
        self.assertEqual(st["no_branch"], 1)

"""Bank deposits: cash book (cash in minus cash out minus deposits), deposit slip upload, expected vs deposited, void, access."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestDeposits(Base):
    def setUp(self):
        super().setUp()
        from app import settings
        self.bid = self.branch("bocaue")
        self.conn.execute("DELETE FROM cash_deposit_photos WHERE deposit_id IN (SELECT id FROM cash_deposits WHERE branch_id = ?)", (self.bid,))
        self.conn.execute("DELETE FROM cash_deposits WHERE branch_id = ?", (self.bid,))
        with self.app.app_context():
            settings.put("deposits.since", "2026-01-01", None, self.conn)
        # synthetic cash movements on fixed past days (no patient details needed for the cash book)
        inv = self.q("SELECT id FROM invoices LIMIT 1")
        self.days = ("2026-02-02", "2026-02-03")
        self.conn.execute("DELETE FROM payments WHERE branch_id = ? AND substr(received_at, 1, 7) = '2026-02'", (self.bid,))
        self.conn.execute("DELETE FROM expenses WHERE branch_id = ? AND substr(expense_date, 1, 7) = '2026-02'", (self.bid,))
        for d, amt, method in ((self.days[0], 500000, "cash"), (self.days[0], 200000, "gcash"), (self.days[1], 300000, "cash")):
            self.conn.execute("INSERT INTO payments (invoice_id, branch_id, kind, amount_cents, method, received_at, status, created_at) "
                              "VALUES (?, ?, 'payment', ?, ?, ?, 'valid', ?)", (inv["id"], self.bid, amt, method, d + " 10:00:00", d + " 10:00:00"))
        self.conn.execute("INSERT INTO expenses (branch_id, expense_date, category, amount_cents, method, status, created_at) "
                          "VALUES (?, ?, 'Food & meals', 50000, 'cash', 'posted', ?)", (self.bid, self.days[0], self.days[0]))

    def test_cash_book_and_deposit(self):
        from app.cash_deposits import net_cash
        self.assertEqual(net_cash(self.conn, self.bid, *self.days), 750000)    # 5,000 + 3,000 cash - 500 cash expense; GCash not counted
        a = self.login("admin")
        page = a.get(f"/staff/deposits/?branch={self.bid}&from=2026-02-01&to=2026-02-28").data.decode()
        self.assertIn("Cash book", page)
        self.assertIn("₱7,500.00", page)
        jpg = io.BytesIO()
        from PIL import Image
        Image.new("RGB", (2400, 1800), (200, 200, 200)).save(jpg, "JPEG")
        jpg.seek(0)
        r = a.post("/staff/deposits/", data={"branch": self.bid, "deposit_date": "2026-02-04", "cash_from": self.days[0], "cash_to": self.days[1],
                                             "amount": "7,400", "bank": "BDO", "account": "••1234", "slip_no": "DS-001",
                                             "slip": (jpg, "slip.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        d = self.q("SELECT * FROM cash_deposits WHERE branch_id = ? ORDER BY id DESC LIMIT 1", (self.bid,))
        self.assertEqual((d["amount_cents"], d["expected_cents"]), (740000, 750000))
        self.assertTrue(d["slip_stored"].startswith("deposits/"))
        page = a.get(f"/staff/deposits/?branch={self.bid}&from=2026-02-01&to=2026-02-28").data.decode()
        self.assertIn("Short ₱100.00", page)
        self.assertEqual(a.get(f"/staff/deposits/{d['id']}/slip").status_code, 200)
        self.assertIn("slip-thumbs", page)
        # a second picture can be added later
        png = io.BytesIO()
        Image.new("RGB", (800, 600), (10, 10, 10)).save(png, "PNG")
        png.seek(0)
        a.post(f"/staff/deposits/{d['id']}/photos", data={"slip": (png, "validated.png")}, content_type="multipart/form-data")
        phs = self.conn.all("SELECT * FROM cash_deposit_photos WHERE deposit_id = ? ORDER BY id", (d["id"],))
        self.assertEqual(len(phs), 2)
        self.assertEqual(a.get(f"/staff/deposits/{d['id']}/slip/{phs[1]['id']}").status_code, 200)
        from app.cash_deposits import on_hand
        self.assertEqual(on_hand(self.conn, self.bid, "2026-02-28"), 10000)
        # void puts the cash back on hand
        a.post(f"/staff/deposits/{d['id']}/void", data={"reason": "Wrong amount"})
        self.assertEqual(on_hand(self.conn, self.bid, "2026-02-28"), 750000)
        csv = a.get(f"/staff/deposits/?branch={self.bid}&from=2026-02-01&to=2026-02-28&format=csv").data.decode()
        self.assertIn("DS-001", csv)

    def test_picture_required(self):
        a = self.login("admin")
        n = self.q("SELECT COUNT(*) AS n FROM cash_deposits")["n"]
        a.post("/staff/deposits/", data={"branch": self.bid, "deposit_date": "2026-02-04", "amount": "100", "bank": "Sample Bank"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM cash_deposits")["n"], n)

    def test_access(self):
        self.assertEqual(self.login("dentist.malolos").get("/staff/deposits/").status_code, 403)
        self.assertEqual(self.login("dentist.malolos").post("/staff/deposits/", data={"amount": "1"}).status_code, 403)


class TestFinancialReport(Base):
    def test_by_where_the_payment_went(self):
        from app import settings
        bid = self.branch("guiguinto")
        inv = self.q("SELECT id FROM invoices LIMIT 1")["id"]
        day = "2026-03-03"
        self.conn.execute("DELETE FROM payments WHERE branch_id = ? AND substr(received_at, 1, 10) = ?", (bid, day))
        for m, acc, amt in (("cash", "", 100000), ("gcash", "GCash", 50000), ("bank_transfer", "BDO", 70000), ("bank_transfer", "BPI", 30000),
                            ("card", "", 20000)):
            self.conn.execute("INSERT INTO payments (invoice_id, branch_id, kind, amount_cents, method, account, received_at, status, created_at) "
                              "VALUES (?, ?, 'payment', ?, ?, ?, ?, 'valid', ?)", (inv, bid, amt, m, acc, day + " 09:00:00", day))
        self.conn.execute("INSERT INTO cash_deposits (branch_id, deposit_date, bank, amount_cents, created_at) VALUES (?, ?, 'BDO', 90000, ?)",
                          (bid, day, day))
        with self.app.app_context():
            settings.put("finance.banks", ["BDO", "BPI", "Security Bank", "RCBC", "AUB"], None, self.conn)
        a = self.login("admin")
        page = a.get(f"/staff/reports/financial?branch={bid}&from={day}&to={day}").data.decode()
        for label in ("Cash", "GCash", "Bank transfer – BDO", "Bank transfer – BPI", "Debit/credit card", "Security Bank", "RCBC", "AUB"):
            self.assertIn(label, page)
        from app import finance_report
        rep = finance_report.build(self.conn, [{"id": bid}], day, day)
        acc = {x["name"]: x for x in rep["accounts"]}
        self.assertEqual((acc["BDO"]["direct"], acc["BDO"]["cash_deposited"], acc["BDO"]["total"]), (70000, 90000, 160000))
        self.assertEqual(acc["GCash"]["total"], 50000)
        self.assertEqual(rep["total"], 270000)
        self.assertEqual(rep["cash_net"] - rep["cash_deposited"], 10000)
        # the payment form offers "Bank transfer – BDO"; a bank transfer without a bank is refused
        self.assertIn('value="bank_transfer:BDO"', a.get(f"/staff/invoices/{inv}").data.decode())

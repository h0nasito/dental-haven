"""MyMedsPH billing reports -> dentist, paid and balance on the MyMedsPH bills (synthetic data only)."""
from __future__ import annotations

import io
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

HEAD = ["Date", "Patient", "Dentist", "Clinic/Lab", "Remarks", "Procedures", "Gross", "Discount", "Net", "Paid", "Balance"]


def workbook(rows):
    import openpyxl
    wb = openpyxl.Workbook()
    s = wb.active
    s.title = "Billing Summary"
    s.append(["Associates", "Clinic", "Laboratory", "Payment Status", "Date From", "Date To", "Gross Amount", "Discount Amount", "Net Amount",
              "Paid Amount", "Total Row"])
    r = wb.create_sheet("Billing Report")
    r.append(HEAD)
    for row in rows:
        r.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestBillingReport(Base):
    def setUp(self):
        from app import legacy_billing
        from app.util import now_str
        c = self.conn
        c.execute("DELETE FROM payments WHERE invoice_id IN (SELECT id FROM invoices WHERE legacy = 1)")
        c.execute("DELETE FROM invoice_items WHERE invoice_id IN (SELECT id FROM invoices WHERE legacy = 1)")
        c.execute("UPDATE legacy_bills SET invoice_id = NULL")
        c.execute("DELETE FROM invoices WHERE legacy = 1")
        c.execute("DELETE FROM legacy_bills")
        c.execute("DELETE FROM settings WHERE key LIKE 'legacy.%'")
        tag = secrets.token_hex(3)
        b = self.branch("malolos")
        self.pid = c.insert("patients", {"first_name": f"Rep{tag}", "last_name": "Billqt", "chart_no": f"DH-B{tag}", "preferred_branch_id": b,
                                         "created_at": now_str(), "updated_at": now_str()})
        self.name = f"Rep{tag} Billqt"
        lines = [("2026-10-01", "CBCT SCAN", 850000), ("2026-10-01", "Denture Impression", 3500000), ("2026-10-09", "IMPLANT", 55500000),
                 ("2026-10-13", "Extraction", 300000)]
        for i, (d, svc, tot) in enumerate(lines):
            c.insert("legacy_bills", {"patient_id": self.pid, "bill_date": d, "service": svc, "qty": 1, "unit_price_cents": tot, "total_cents": tot,
                                      "status_code": "2", "legacy_key": f"br-{tag}-{i}"})
        with self.app.app_context():
            legacy_billing.convert(c, {"2": "paid"}, b, None)      # status 2 = paid -> "Paid in MyMedsPH" payments of the full amount
        self.dentist = self.q("SELECT id, name FROM users WHERE email LIKE 'dentist.malolos@%'")
        dname = self.dentist["name"].replace("Dr. ", "")
        self.rows = [["Oct 01, 2026", self.name, dname, "Dental Haven Malolos ", "Progress Note", "CBCT SCAN, Denture Impression",
                      43500.0, 0.0, 43500.0, 43500.0, ""],
                     ["Oct 09, 2026", self.name, dname, "Dental Haven Malolos ", "Progress Note", "IMPLANT(#36)", 555000.0, 0.0, 555000.0, 300000.0, 255000.0],
                     ["Oct 13, 2026", self.name, dname, "Dental Haven Malolos ", "Progress Note", "Extraction (#14, 15)", 3000.0, 0.0, 3000.0, 0.0, 3000.0],
                     ["Oct 20, 2026", self.name, dname, "Dental Haven Malolos ", "Progress Note", "Braces Adjustment(#), Asepsis Fee", 5000.0, 0.0,
                      5000.0, 2000.0, 3000.0],
                     ["Oct 21, 2026", "Nobody Matches Here", dname, "Dental Haven Malolos ", "Progress Note", "OP", 1000.0, 0.0, 1000.0, 1000.0, ""]]

    def paid(self, day):
        return self.conn.scalar("SELECT COALESCE(SUM(p.amount_cents), 0) FROM payments p JOIN invoices i ON i.id = p.invoice_id "
                                "WHERE i.patient_id = ? AND substr(i.issued_at, 1, 10) = ? AND p.status = 'valid'", (self.pid, day))

    def test_report_sets_dentist_paid_and_missing_bills(self):
        c = self.login("admin")
        r = c.post("/staff/admin/import/billing-report", data={"files": [(io.BytesIO(workbook(self.rows)), "doc.xlsx")]},
                   content_type="multipart/form-data")
        page = r.data.decode()
        self.assertEqual(r.status_code, 200, page[:400])
        self.assertIn("Check the billing report", page)
        self.assertIn("Nobody Matches Here", page)
        token = page.split('name="token" value="')[1].split('"')[0]
        csv = c.post("/staff/admin/import/billing-report/confirm", data={"token": token, "action": "problems"}).data.decode()
        self.assertIn("name not matched", csv)
        c.post("/staff/admin/import/billing-report/confirm", data={"token": token, "action": "confirm"})
        # paid now matches MyMedsPH, bill by bill
        self.assertEqual([self.paid(d) for d in ("2026-10-01", "2026-10-09", "2026-10-13", "2026-10-20")], [4350000, 30000000, 0, 200000])
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM payments WHERE legacy_key LIKE 'mmbv:%' AND status = 'void'"), 3)
        # the missing bill was created with its procedures, shared amount and dentist
        mb = self.q("SELECT * FROM invoices WHERE patient_id = ? AND number LIKE 'MB-%'", (self.pid,))
        self.assertEqual((mb["total_cents"], mb["issued_at"][:10]), (500000, "2026-10-20"))
        items = self.conn.all("SELECT description, amount_cents, dentist_id, done_on FROM invoice_items WHERE invoice_id = ? ORDER BY id", (mb["id"],))
        self.assertEqual([(i["description"], i["amount_cents"], i["dentist_id"]) for i in items],
                         [("Braces Adjustment", 250000, self.dentist["id"]), ("Asepsis Fee", 250000, self.dentist["id"])])
        # dentist on the converted bills' lines
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id WHERE i.patient_id = ? "
                                          "AND i.number LIKE 'MM-%' AND ii.dentist_id = ?", (self.pid, self.dentist["id"])), 4)
        # imported visits (progress notes) of that day get the dentist too, and show the note once
        from app.util import now_str
        pr1 = self.conn.insert("procedures", {"patient_id": self.pid, "description": "Extraction\nNote of the visit", "status": "completed",
                                              "performed_at": "2026-10-13", "created_at": now_str(), "legacy_key": "pn-br-1"})
        pr2 = self.conn.insert("procedures", {"patient_id": self.pid, "description": "Asepsis Fee\nNote of the visit", "status": "completed",
                                              "performed_at": "2026-10-13", "created_at": now_str(), "legacy_key": "pn-br-2"})
        from app import legacy_billing_report as br
        with self.app.app_context():
            self.assertEqual(br.link_procedure_dentists(self.conn), 2)
        self.assertEqual(self.q("SELECT performed_by FROM procedures WHERE id = ?", (pr1,))["performed_by"], self.dentist["id"])
        notes = c.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertEqual(notes.count('<p class="pre pn-note">Note of the visit</p>'), 1)
        self.assertIn(self.dentist["name"], notes)
        # uploading again changes nothing
        before = self.conn.scalar("SELECT COUNT(*) FROM payments")
        r = c.post("/staff/admin/import/billing-report", data={"files": [(io.BytesIO(workbook(self.rows)), "doc.xlsx")]},
                   content_type="multipart/form-data")
        token = r.data.decode().split('name="token" value="')[1].split('"')[0]
        c.post("/staff/admin/import/billing-report/confirm", data={"token": token, "action": "confirm"})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM payments"), before)
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM invoices WHERE patient_id = ? AND number LIKE 'MB-%'", (self.pid,)), 1)
        # undo: back as before
        c.post("/staff/admin/import/billing-report/undo")
        self.assertEqual([self.paid(d) for d in ("2026-10-01", "2026-10-09", "2026-10-13")], [4350000, 55500000, 300000])
        self.assertIsNone(self.q("SELECT id FROM invoices WHERE patient_id = ? AND number LIKE 'MB-%'", (self.pid,)))
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM invoice_items WHERE legacy_dentist = 2"), 0)
        self.assertIsNone(self.q("SELECT performed_by FROM procedures WHERE id = ?", (pr1,))["performed_by"])

    def test_keeps_dated_payments(self):
        """A real payment (e.g. from a collection report) stays; only the missing amount is added."""
        from app.util import now_str
        inv = self.q("SELECT id, branch_id FROM invoices WHERE patient_id = ? AND substr(issued_at, 1, 10) = '2026-10-09'", (self.pid,))
        self.conn.execute("DELETE FROM payments WHERE invoice_id = ?", (inv["id"],))
        self.conn.insert("payments", {"invoice_id": inv["id"], "branch_id": inv["branch_id"], "kind": "payment", "amount_cents": 10000000,
                                      "method": "cash", "received_at": "2026-10-15 10:00:00", "status": "valid", "created_at": now_str(),
                                      "legacy_key": "mmc:test-dated"})
        from app import legacy_billing_report as br
        with self.app.app_context():
            from flask import g
            data = br.read_reports([("doc.xlsx", workbook(self.rows[1:2]))])
            br.apply(self.conn, data, None)
        self.assertEqual(self.paid("2026-10-09"), 30000000)       # 100,000 kept + 200,000 added
        self.assertTrue(self.q("SELECT id FROM payments WHERE legacy_key = 'mmc:test-dated' AND status = 'valid'"))

    def test_two_dentists_on_one_day(self):
        """One day, two MyMedsPH bills by two dentists, combined into one bill here: each line gets its own dentist,
        and a dentist an earlier upload put on every line is corrected."""
        from app import legacy_billing_report as br
        other = self.q("SELECT id, name FROM users WHERE role = 'dentist' AND id != ? ORDER BY id LIMIT 1", (self.dentist["id"],))
        inv = self.q("SELECT id FROM invoices WHERE patient_id = ? AND substr(issued_at, 1, 10) = '2026-10-01'", (self.pid,))
        # as an earlier upload left it: one dentist on every line of the day
        self.conn.execute("UPDATE invoice_items SET dentist_id = ?, legacy_dentist = 2 WHERE invoice_id = ?", (self.dentist["id"], inv["id"]))
        oname = "Doc " + other["name"].replace("Dr. ", "")
        rows = [["Oct 01, 2026", self.name, oname, "Dental Haven Malolos ", "", "CBCT SCAN", 8500.0, 0.0, 8500.0, 8500.0, ""],
                ["Oct 01, 2026", self.name, self.dentist["name"], "Dental Haven Malolos ", "", "Denture Impression", 35000.0, 0.0, 35000.0, 35000.0, ""]]
        with self.app.app_context():
            br.apply(self.conn, br.read_reports([("doc.xlsx", workbook(rows))]), None)
        got = {r["description"]: r["dentist_id"] for r in self.conn.all("SELECT description, dentist_id FROM invoice_items WHERE invoice_id = ?", (inv["id"],))}
        self.assertEqual(got, {"CBCT SCAN": other["id"], "Denture Impression": self.dentist["id"]})
        # a dentist not found here: only the other dentist's procedure gets a dentist, not the whole day
        self.conn.execute("UPDATE invoice_items SET dentist_id = NULL, legacy_dentist = 0 WHERE invoice_id = ?", (inv["id"],))
        rows[0][2] = "Unknown Person Here"
        with self.app.app_context():
            br.apply(self.conn, br.read_reports([("doc.xlsx", workbook(rows))]), None)
        got = {r["description"]: r["dentist_id"] for r in self.conn.all("SELECT description, dentist_id FROM invoice_items WHERE invoice_id = ?", (inv["id"],))}
        self.assertEqual(got, {"CBCT SCAN": None, "Denture Impression": self.dentist["id"]})

    def test_visit_dentist_from_bill_and_set_by_staff(self):
        from app.util import now_str
        inv = self.q("SELECT id FROM invoices WHERE patient_id = ? AND substr(issued_at, 1, 10) = '2026-10-13'", (self.pid,))
        self.conn.execute("UPDATE invoice_items SET dentist_id = ? WHERE invoice_id = ?", (self.dentist["id"], inv["id"]))
        pr = self.conn.insert("procedures", {"patient_id": self.pid, "description": "Extraction\nVisit text one", "status": "completed",
                                             "performed_at": "2026-10-13", "created_at": now_str(), "legacy_key": "pn-vd-1"})
        lone = self.conn.insert("procedures", {"patient_id": self.pid, "description": "Trial crown", "status": "completed",
                                               "performed_at": "2026-09-02", "created_at": now_str(), "legacy_key": "pn-vd-2"})
        c = self.login("admin")
        page = c.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        row = page.split("Visit text one")[0].rsplit("pn-date", 1)[1]
        self.assertIn(self.dentist["name"], row)            # shown from the bill, nothing saved yet
        self.assertIn("Set dentist", page)
        r = c.post(f"/staff/patients/{self.pid}/procedures/dentist", data={"ids": [lone], "dentist_id": self.dentist["id"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.q("SELECT performed_by FROM procedures WHERE id = ?", (lone,))["performed_by"], self.dentist["id"])
        # editing keeps the note's lines
        c.post(f"/staff/patients/{self.pid}/procedures/{pr}", data={"action": "edit", "description": "Extraction\r\nVisit text one\r\nLine 2",
                                                                    "tooth": "", "performed_at": "2026-10-13"})
        self.assertEqual(self.q("SELECT description FROM procedures WHERE id = ?", (pr,))["description"], "Extraction\nVisit text one\nLine 2")

    def test_not_a_billing_report(self):
        r = self.login("admin").post("/staff/admin/import/billing-report", data={"files": [(io.BytesIO(b"not excel"), "x.xlsx")]},
                                     content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("an Excel file MyMedsPH made", r.data.decode())

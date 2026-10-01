"""Fee schedule: the clinic's 216 billing prices by category, editing, Excel update, and use in progress notes / bills."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_employee_import import make_xlsx  # noqa: E402


class TestFees(Base):
    def test_loaded_and_categorized(self):
        from app.fee_schedule_data import CATEGORIES
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM fee_schedule")["n"], 216)
        cats = {r["category"] for r in self.conn.all("SELECT DISTINCT category FROM fee_schedule")}
        self.assertEqual(cats, set(CATEGORIES))
        row = self.q("SELECT * FROM fee_schedule WHERE name = 'JACKET CROWN - ZIRCONIA'")
        self.assertEqual((row["price_cents"], row["unit"], row["category"]), (2500000, "Per unit / Per tooth", "Crowns, Bridges & Veneers"))
        self.assertEqual(self.q("SELECT category FROM fee_schedule WHERE name = 'REBRACKET - ORDINARY'")["category"], "Braces, Aligners & Orthodontics")
        self.assertEqual(self.q("SELECT category FROM fee_schedule WHERE name = 'PEDIATRIC- SEALANT'")["category"], "Pediatric (Kids)")

    def test_admin_edit_add_import_and_access(self):
        admin = self.login("admin")
        page = admin.get("/staff/admin/fees/").data.decode()
        self.assertIn("Root Canal (Endodontics)", page)
        self.assertIn("ORAL PROPHYLAXIS (MILD)", page)
        f = self.q("SELECT * FROM fee_schedule WHERE name = 'NICOTINE STAIN'")
        admin.post("/staff/admin/fees/", data={"action": "save", "id": f["id"], "name": f["name"], "unit": "", "price": "550",
                                              "category": f["category"], "active": "1"})
        self.assertEqual(self.q("SELECT price_cents FROM fee_schedule WHERE id = ?", (f["id"],))["price_cents"], 55000)
        admin.post("/staff/admin/fees/", data={"action": "add", "name": "TEST FLUORIDE VARNISH", "unit": "Per visit", "price": "750"})
        self.assertEqual(self.q("SELECT category FROM fee_schedule WHERE name = 'TEST FLUORIDE VARNISH'")["category"], "Cleaning & Prevention")
        data = make_xlsx([["SERVICES/PROCEDURE", "UNIT", "PRICE"], ["CONSULTATION", "", "₱700.00"], ["TEST NEW ODONTECTOMY", "Per tooth", "12000"]])
        admin.post("/staff/admin/fees/import", data={"file": (io.BytesIO(data), "SERVICES.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(self.q("SELECT price_cents FROM fee_schedule WHERE name = 'CONSULTATION'")["price_cents"], 70000)
        self.assertEqual(self.q("SELECT category FROM fee_schedule WHERE name = 'TEST NEW ODONTECTOMY'")["category"], "Extraction & Oral Surgery")
        self.assertEqual(self.login("dentist.sjdm").get("/staff/admin/fees/").status_code, 403)
        self.conn.execute("UPDATE fee_schedule SET price_cents = 65000 WHERE name = 'CONSULTATION'")
        self.conn.execute("UPDATE fee_schedule SET price_cents = 50000 WHERE name = 'NICOTINE STAIN'")
        self.conn.execute("DELETE FROM fee_schedule WHERE name LIKE 'TEST %'")

    def test_progress_note_uses_fee_schedule(self):
        doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        admin = self.login("admin")
        page = admin.get(f"/staff/patients/{pid}?tab=notes").data.decode()
        self.assertIn('value="JACKET CROWN - ZIRCONIA"', page)
        self.assertIn("Crowns, Bridges &amp; Veneers · Per unit / Per tooth · ₱25,000.00", page)
        self.assertIn('value="PANORAMIC XRAY (No bite)"', page)   # duplicate names get their unit
        # per-arch item with teeth typed: quantity stays 1; per-tooth item: quantity = number of teeth
        admin.post(f"/staff/patients/{pid}/visit-note", data={
            "visit_date": "2025-09-01", "dentist_id": str(doc), "branch_id": str(self.branch("sjdm")), "body": "",
            "line_service_id": ["", ""], "line_desc": ["NIGHT GUARD", "JACKET CROWN - ZIRCONIA"], "line_tooth": ["16, 26", "11, 21"],
            "line_qty": ["", ""], "line_price": ["8500", "25000"], "line_disc": ["", ""], "bill_disc": "", "create_bill": "1",
            "action": "save"}, content_type="multipart/form-data")
        v = self.q("SELECT invoice_id FROM visit_notes WHERE patient_id = ? AND visit_date = '2025-09-01'", (pid,))
        items = {i["description"]: i["qty"] for i in self.conn.all("SELECT * FROM invoice_items WHERE invoice_id = ?", (v["invoice_id"],))}
        self.assertEqual(items, {"NIGHT GUARD": 1, "JACKET CROWN - ZIRCONIA": 2})

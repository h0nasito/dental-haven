"""My cases: type of case from fee schedule names / keywords; patients linked by the dentist on their bill lines."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402

from app.case_types import GENERAL, ORTHO, Classifier  # noqa: E402


class TestCaseTypes(Base):
    def test_names_and_keywords(self):
        k = Classifier(self.conn)
        cases = {
            "RESTORATION/PASTA- POSTERIOR/LIKOD": "Fillings & Restorations",      # exact fee schedule name
            "Restoration/Pasta- Posterior/Likod\nMO, light cure": "Fillings & Restorations",
            "BRACES INSTALL": ORTHO,
            "Braces adjustment (#16)": ORTHO,
            "DENTURE ADJUSTMENT": "Dentures",
            "Oral prophylaxis (Mild)": "Cleaning & Prevention",
            "Bunot - lower molar": "Extraction & Oral Surgery",
            "RCT - 2 CANALS": "Root Canal (Endodontics)",
            "Pediatric- Sealant": "Pediatric (Kids)",
            "HAWLEY RETAINER": "Retainers & Ortho Appliances",
            "JACKET CROWN- TEMPORARY": "Crowns, Bridges & Veneers",
            "PANORAMIC XRAY": GENERAL,
            "CONSULTATION": GENERAL,
            "Something unknown": GENERAL,
            "MM-000123 · Oral prophylaxis (Mild)": GENERAL,          # only the part before " · " counts
            "Oral prophylaxis (Mild) · Oral prophylaxis": "Cleaning & Prevention",
        }
        for text, want in cases.items():
            self.assertEqual(k(text), want, text)
        self.assertEqual(k("Visit", "Orthodontics & TMJ"), ORTHO)     # only the website service is known

    def test_bill_lines_alone_dont_add_the_patient(self):
        """A dentist named on a bill line doesn't get the patient in My cases unless the patient is assigned to them."""
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.conn.insert("patients", {"chart_no": "T-CT-1", "first_name": "Billline", "last_name": "Linked", "created_at": "2026-01-01 00:00:00"})
        branch = self.branch("malolos")
        inv = self.conn.insert("invoices", {"number": "T-CT-1", "branch_id": branch, "patient_id": pid, "status": "issued",
                                            "issued_at": "2026-03-01 12:00:00", "subtotal_cents": 300000, "discount_cents": 0, "tax_cents": 0,
                                            "total_cents": 300000, "created_at": "2026-03-01 12:00:00"})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "BRACES INSTALL", "qty": 1, "unit_price_cents": 200000,
                                           "discount_cents": 0, "amount_cents": 200000, "dentist_id": doc})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "ORAL PROPHYLAXIS (MILD)", "qty": 1, "unit_price_cents": 100000,
                                           "discount_cents": 0, "amount_cents": 100000})
        c = self.login("dentist.malolos")
        self.assertNotIn("Linked, Billline", c.get("/staff/my-cases/?q=billline").data.decode())
        # once assigned, the cases billed to them show
        self.conn.execute("INSERT INTO patient_assignments (patient_id, dentist_id, created_at) VALUES (?, ?, '2026-03-02 00:00:00')", (pid, doc))
        page = c.get("/staff/my-cases/?q=billline").data.decode()
        self.assertIn("Linked, Billline", page)
        self.assertIn("Braces, Aligners &amp; Orthodontics", page)
        self.assertNotIn("Cleaning &amp; Prevention</span>", page)          # that line isn't billed to this dentist
        self.assertEqual(c.get(f"/staff/my-cases/{pid}?type=Cleaning %26 Prevention").status_code, 404)

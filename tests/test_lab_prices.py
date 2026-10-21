"""Lab price list: DSDL prices loaded, only "Laboratory services & prices" (lab.prices) edits, branch staff view, pickers on the invoice."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_case_billing import TestLabCaseBilling  # noqa: E402


class TestLabPrices(TestLabCaseBilling):
    test_lab_sets_price_and_bills_branch = None
    test_bill_by_case_with_units_extras_and_less = None

    def test_dsdl_prices_loaded(self):
        n = self.q("SELECT COUNT(*) AS n FROM lab_price_items WHERE lab_id = ?", (self.lab,))["n"]
        self.assertEqual(n, 48)
        z = self.q("SELECT price_cents FROM lab_price_items WHERE lab_id = ? AND name = 'Zirconia premium'", (self.lab,))
        self.assertEqual(z["price_cents"], 550000)

    def test_lab_prices_permission_edits_and_branch_views(self):
        # lab billing alone doesn't edit the price list any more
        page = self.t.get("/staff/lab/prices").data.decode()
        self.assertNotIn("Save price list", page)
        self.assertEqual(self.t.post("/staff/lab/prices", data={"action": "add", "lab_id": self.lab, "name": "Nope", "price": "1"}).status_code, 403)
        uid = self.q("SELECT id FROM users WHERE email = ?", (f"labrec{id(self)}@dsdl.test",))["id"]
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'lab.prices', 1)", (uid,))
        page = self.t.get("/staff/lab/prices").data.decode()
        self.assertIn("Save price list", page)
        it = self.q("SELECT * FROM lab_price_items WHERE lab_id = ? AND name = 'Zirconia premium'", (self.lab,))
        r = self.t.post("/staff/lab/prices", data={"action": "save", f"name_{it['id']}": it["name"], f"price_{it['id']}": "5800",
                                                    f"unit_{it['id']}": "unit", f"note_{it['id']}": "", f"active_{it['id']}": "1"})
        self.assertIn(r.status_code, (200, 302))
        self.assertEqual(self.q("SELECT price_cents FROM lab_price_items WHERE id = ?", (it["id"],))["price_cents"], 580000)
        self.t.post("/staff/lab/prices", data={"action": "add", "lab_id": self.lab, "category": "Others", "name": "Test item X", "price": "123"})
        self.assertIsNotNone(self.q("SELECT id FROM lab_price_items WHERE name = 'Test item X'"))
        d = self.login("dentist.malolos")
        page = d.get("/staff/lab/prices").data.decode()
        self.assertIn("Zirconia premium", page)
        self.assertNotIn("Save price list", page)
        self.assertEqual(d.post("/staff/lab/prices", data={"action": "add", "lab_id": self.lab, "name": "Nope", "price": "1"}).status_code, 403)

    def test_picker_on_invoice(self):
        r = self.t.post(f"/staff/lab/cases/{self.case}/bill")
        page = self.t.get(r.headers["Location"]).data.decode()
        self.assertIn("data-price-pick", page)
        self.assertIn('data-price="5500.00"', page)




class TestLabClinicsAdd(TestLabCaseBilling):
    test_lab_sets_price_and_bills_branch = None
    test_bill_by_case_with_units_extras_and_less = None

    def test_add_outside_clinic(self):
        uid = self.q("SELECT id FROM users WHERE email = ?", (f"labrec{id(self)}@dsdl.test",))["id"]
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'lab.works', 1)", (uid,))
        self.assertIn("Add a clinic", self.t.get("/staff/lab/clients").data.decode())
        self.t.post("/staff/lab/clients", data={"action": "add", "kind": "outside", "clinic_name": "Smile QT Dental", "doctor": "Dr. QT", "contact_number": "0917"})
        c = self.q("SELECT * FROM lab_clients WHERE clinic_name = 'Smile QT Dental'")
        self.assertEqual((c["lab_id"], c["doctor"], c["branch_id"]), (self.lab, "Dr. QT", None))
        self.t.post("/staff/lab/clients", data={"action": "add", "kind": "outside", "clinic_name": "smile qt dental"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_clients WHERE lower(clinic_name) = 'smile qt dental'")["n"], 1)
        self.assertIn("Smile QT Dental", self.t.get("/staff/lab/works/new").data.decode())
        # the type must be chosen
        self.t.post("/staff/lab/clients", data={"action": "add", "clinic_name": "No Type QT"})
        self.assertIsNone(self.q("SELECT id FROM lab_clients WHERE clinic_name = 'No Type QT'"))
        # a Dental Haven branch: listed once per lab (adding it again updates it)
        page = self.t.get("/staff/lab/clients").data.decode()
        self.assertIn("Dental Haven branches", page)
        self.assertIn("Outside clinics", page)
        bid = self.branch("malolos")
        self.t.post("/staff/lab/clients", data={"action": "add", "kind": "branch", "branch_id": bid, "doctor": "Dr. Branch QT"})
        rows = self.conn.all("SELECT * FROM lab_clients WHERE lab_id = ? AND branch_id = ?", (self.lab, bid))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doctor"], "Dr. Branch QT")
        # an outside clinic can be changed to a branch only if that branch isn't listed yet
        self.t.post("/staff/lab/clients", data={"client_id": c["id"], "kind": "branch", "branch_id": bid, "clinic_name": "Smile QT Dental", "active": "1"})
        self.assertIsNone(self.q("SELECT branch_id FROM lab_clients WHERE id = ?", (c["id"],))["branch_id"])



class TestLabServices(TestLabCaseBilling):
    test_lab_sets_price_and_bills_branch = None
    test_bill_by_case_with_units_extras_and_less = None

    def test_lab_services_editable(self):
        admin = self.login("admin")
        page = admin.get("/staff/lab/services").data.decode()
        self.assertIn("Crown (PFM)", page)
        self.assertIn("Add a type of case", page)
        self.assertIn("E.max (lithium disilicate)", page)
        admin.post("/staff/lab/services", data={"action": "add", "name": "Crown (e.max QT)"})
        self.assertIn(">Crown (e.max QT)</option>", admin.get("/staff/lab/works/new").data.decode())
        row = self.q("SELECT * FROM lab_case_types WHERE name = 'Crown (e.max QT)'")
        admin.post("/staff/lab/services", data={"action": "rename", "id": row["id"], "name": "Crown (e.max) QT"})
        self.assertIsNotNone(self.q("SELECT id FROM lab_case_types WHERE name = 'Crown (e.max) QT'"))
        admin.post("/staff/lab/services", data={"action": "toggle", "id": row["id"]})
        self.assertNotIn(">Crown (e.max) QT</option>", admin.get("/staff/lab/works/new").data.decode())
        admin.post("/staff/lab/services", data={"action": "add", "name": "crown (pfm)"})          # duplicate
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_case_types WHERE lower(name) = 'crown (pfm)'")["n"], 1)
        # lab billing alone (no lab services & prices) can only view
        self.assertNotIn("Add a type of case", self.t.get("/staff/lab/services").data.decode())
        # materials list
        admin.post("/staff/lab/services", data={"list": "materials", "action": "add", "name": "Lithium QT"})
        self.assertIn(">Lithium QT</option>", admin.get("/staff/lab/works/new").data.decode())
        self.assertEqual(self.t.post("/staff/lab/services", data={"action": "add", "name": "Nope QT"}).status_code, 403)


del TestLabCaseBilling

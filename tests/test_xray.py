"""X-ray section: own records, receipts and payments; walk-ins; referring dentists' rebates (synthetic data only)."""
from __future__ import annotations

import io
import secrets
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class TestXray(Base):
    def setUp(self):
        from app.util import now_str
        self.b = self.branch("malolos")
        tag = secrets.token_hex(3)
        self.pid = self.conn.insert("patients", {"first_name": f"Xr{tag}", "last_name": "Patient", "chart_no": f"DH-X{tag}",
                                                 "preferred_branch_id": self.b, "created_at": now_str(), "updated_at": now_str()})
        self.chart = f"DH-X{tag}"
        self.pano = self.q("SELECT id FROM xray_types WHERE name = 'Panoramic'")["id"]
        self.peri = self.q("SELECT id FROM xray_types WHERE name = 'TMJ'")["id"]
        self.today = date.today().isoformat()

    def new(self, c, **data):
        base = {"branch_id": self.b, "taken_on": self.today, "type_0": self.pano, "price_0": "1000"}
        base.update(data)
        return c.post("/staff/xray/new", data=base, content_type="multipart/form-data")

    def last(self):
        return self.q("SELECT * FROM xrays ORDER BY id DESC LIMIT 1")

    def test_walkin_with_referral_payment_and_image(self):
        c = self.login("staff.malolos")
        procs = self.conn.scalar("SELECT COUNT(*) FROM procedures")
        invs = self.conn.scalar("SELECT COUNT(*) FROM invoices")
        r = self.new(c, walkin_name="Walk In Tester", walkin_phone="0917", requested="new", new_ref_name="Dr. Outside Demo",
                     new_ref_clinic="Smile Demo Clinic", type_1=self.peri, tooth_1="36", price_1="500", discount="100", rebate="150",
                     pay_amount="1000", pay_method="cash", files=[(io.BytesIO(PNG), "pano.png")])
        self.assertEqual(r.status_code, 302, r.data[:600])
        x = self.last()
        self.assertTrue(x["number"].startswith("XR-"))
        self.assertEqual((x["patient_id"], x["walkin_name"], x["subtotal_cents"], x["total_cents"], x["rebate_cents"]),
                         (None, "Walk In Tester", 150000, 140000, 15000))
        self.assertEqual(self.q("SELECT name FROM xray_referrers WHERE id = ?", (x["referrer_id"],))["name"], "Dr. Outside Demo")
        page = c.get(f"/staff/xray/{x['id']}").data.decode()
        self.assertIn("Walk In Tester (walk-in)", page)
        self.assertIn("₱400.00", page)                                   # balance
        f = self.q("SELECT id FROM xray_files WHERE xray_id = ?", (x["id"],))
        self.assertEqual(c.get(f"/staff/xray/files/{f['id']}").data, PNG)
        # not in progress notes or patient bills
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM procedures"), procs)
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM invoices"), invs)
        # pay the rest; receipt
        c.post(f"/staff/xray/{x['id']}/pay", data={"amount": "400", "method": "gcash"})
        self.assertIn("Paid", c.get(f"/staff/xray/{x['id']}").data.decode())
        self.assertIn(x["number"], c.get(f"/staff/xray/{x['id']}/receipt").data.decode())
        # another branch can't see it
        self.assertEqual(self.login("reception.bocaue").get(f"/staff/xray/{x['id']}").status_code, 404)
        self.assertEqual(self.login("reception.bocaue").get(f"/staff/xray/files/{f['id']}").status_code, 404)
        # staff can't void; admin voids payments then the X-ray
        self.assertEqual(c.post(f"/staff/xray/{x['id']}/void", data={"reason": "test"}).status_code, 403)
        a = self.login("admin")
        a.post(f"/staff/xray/{x['id']}/void", data={"reason": "wrong patient"})
        self.assertEqual(self.q("SELECT status FROM xrays WHERE id = ?", (x["id"],))["status"], "ok")   # payments first
        for p in self.conn.all("SELECT id FROM xray_payments WHERE xray_id = ?", (x["id"],)):
            a.post(f"/staff/xray/{x['id']}/payments/{p['id']}/void", data={"reason": "wrong patient"})
        a.post(f"/staff/xray/{x['id']}/void", data={"reason": "wrong patient"})
        self.assertEqual(self.q("SELECT status FROM xrays WHERE id = ?", (x["id"],))["status"], "void")

    def test_clinic_patient_tab_and_prices(self):
        a = self.login("admin")
        a.post("/staff/xray/prices", data={f"price_{self.pano}": "1200", f"active_{self.pano}": "1",
                                           **{f"active_{t['id']}": "1" for t in self.conn.all("SELECT id FROM xray_types")}})
        self.assertEqual(self.q("SELECT price_cents FROM xray_types WHERE id = ?", (self.pano,))["price_cents"], 120000)
        c = self.login("staff.malolos")
        dentist = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        r = self.new(c, chart_no=self.chart, price_0="", requested=f"d:{dentist}")
        self.assertEqual(r.status_code, 302, r.data[:600])
        x = self.last()
        self.assertEqual((x["patient_id"], x["total_cents"], x["requested_by"], x["rebate_cents"]), (self.pid, 120000, dentist, 0))
        tab = c.get(f"/staff/patients/{self.pid}?tab=xray").data.decode()
        self.assertIn(x["number"], tab)
        # a type without a price needs one
        r = self.new(c, chart_no=self.chart, type_0=self.peri, price_0="")
        self.assertIn("enter the price", r.data.decode())
        # a rebate only for outside dentists; unknown chart no. is an error
        self.assertIn("only for X-rays referred", self.new(c, chart_no=self.chart, rebate="50").data.decode())
        self.assertIn("No patient with chart no.", self.new(c, chart_no="NOPE-1").data.decode())
        # a dentist (view only) can see the list but not record
        d = self.login("dentist.malolos")
        self.assertEqual(d.get("/staff/xray/").status_code, 200)
        self.assertEqual(d.get("/staff/xray/new").status_code, 403)

    def test_periapical_is_not_an_xray_type(self):
        self.assertIsNone(self.q("SELECT id FROM xray_types WHERE name = 'Periapical' AND active = 1"))
        page = self.login("staff.malolos").get("/staff/xray/new").data.decode()
        self.assertNotRegex(page, r"<option[^>]*>Periapical")
        self.assertIn("Periapical X-rays are recorded in the progress notes", page)

    def test_rebate_rate_and_payout(self):
        a = self.login("admin")
        a.post("/staff/xray/rebates", data={"name": "Dr. Rebate Demo", "clinic": "Demo Clinic", "rate": "10"})
        ref = self.q("SELECT * FROM xray_referrers WHERE name = 'Dr. Rebate Demo'")
        self.assertEqual(ref["rebate_bp"], 1000)
        c = self.login("staff.malolos")
        self.new(c, walkin_name="Referred Walkin", requested=f"r:{ref['id']}", price_0="2000", pay_amount="2000", pay_method="cash")
        x = self.last()
        self.assertEqual(x["rebate_cents"], 20000)
        page = a.get(f"/staff/xray/rebates/{ref['id']}").data.decode()
        self.assertIn(x["number"], page)
        self.assertEqual(c.get("/staff/xray/rebates").status_code, 403)
        a.post(f"/staff/xray/rebates/{ref['id']}", data={"action": "payout", "ids": [x["id"]], "paid_on": self.today, "method": "cash"})
        po = self.q("SELECT * FROM xray_rebate_payouts WHERE referrer_id = ?", (ref["id"],))
        self.assertEqual(po["amount_cents"], 20000)
        self.assertEqual(self.q("SELECT rebate_payout_id FROM xrays WHERE id = ?", (x["id"],))["rebate_payout_id"], po["id"])
        # paid twice? no: nothing left to tick
        a.post(f"/staff/xray/rebates/{ref['id']}", data={"action": "payout", "ids": [x["id"]], "paid_on": self.today, "method": "cash"})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM xray_rebate_payouts WHERE referrer_id = ?", (ref["id"],)), 1)
        a.post(f"/staff/xray/rebates/payouts/{po['id']}/void", data={"reason": "wrong amount"})
        self.assertIsNone(self.q("SELECT rebate_payout_id FROM xrays WHERE id = ?", (x["id"],))["rebate_payout_id"])
        # report
        rep = a.get("/staff/xray/report").data.decode()
        self.assertIn("Dr. Rebate Demo", rep)

"""New-patient kiosk on a clinic tablet (synthetic data only)."""
import base64
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import PW, Base  # noqa: E402


def sig_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 20), (255, 255, 255)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class TestKiosk(Base):
    def form(self, **kw):
        d = {"first_name": "kiosk", "last_name": "demopatient", "birth_date": "1990-04-02", "phone": "09171234567",
             "email": "", "address": "Demo street", "emergency_contact": "Demo Contact", "emergency_relation": "Sister",
             "emergency_phone": "09181234567", "conditions": ["Diabetes"], "allergies": ["Latex"], "medications": "Metformin",
             "reason": "Cleaning", "consent_privacy": "1", "signature": sig_png()}
        d.update(kw)
        return d

    def test_kiosk_flow_review_and_accept(self):
        bid = self.branch("malolos")
        c = self.login("reception.malolos")
        c.post("/staff/kiosk/start", data={"branch_id": bid})
        # locked: any other page goes back to the form
        r = c.get("/staff/patients")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/kiosk", r.headers["Location"])
        self.assertIn("Welcome! Please tell us about yourself", c.get("/kiosk").data.decode())
        # missing consent / signature: refused
        page = c.post("/kiosk", data=self.form(consent_privacy="", signature="")).data.decode()
        self.assertIn("agree to the privacy notice", page)
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM kiosk_registrations"), 0)
        r = c.post("/kiosk", data=self.form())
        self.assertIn("/kiosk/done", r.headers["Location"])
        reg = self.q("SELECT * FROM kiosk_registrations ORDER BY id DESC")
        self.assertEqual((reg["status"], reg["first_name"], reg["branch_id"]), ("pending", "Kiosk", bid))
        self.assertTrue(reg["signature_name"])
        # leaving kiosk mode needs the password
        c.post("/kiosk/exit", data={"password": "wrong"})
        self.assertEqual(c.get("/staff/patients").status_code, 302)
        c.post("/kiosk/exit", data={"password": PW})
        self.assertEqual(c.get("/staff/patients/").status_code, 200)
        # review and create the patient
        self.assertIn("Kiosk", c.get("/staff/registrations").data.decode())
        page = c.get(f"/staff/registrations/{reg['id']}").data.decode()
        self.assertIn("Diabetes", page)
        r = c.post(f"/staff/registrations/{reg['id']}", data={"action": "accept"})
        self.assertEqual(r.status_code, 302)
        p = self.q("SELECT * FROM patients WHERE last_name = 'Demopatient'")
        self.assertEqual((p["phone"], p["consent_privacy"], p["source"], p["preferred_branch_id"]), ("09171234567", 1, "kiosk", bid))
        h = self.q("SELECT * FROM patient_history WHERE patient_id = ?", (p["id"],))
        self.assertIn("Diabetes", h["medical_conditions"])
        self.assertIn("Latex", h["allergies"])
        self.assertIsNotNone(self.q("SELECT id FROM patient_documents WHERE patient_id = ? AND category = 'consent_form'", (p["id"],)))
        self.assertEqual(self.q("SELECT status FROM kiosk_registrations WHERE id = ?", (reg["id"],))["status"], "accepted")

    def test_minor_needs_guardian_link_and_discard(self):
        bid = self.branch("malolos")
        c = self.login("reception.malolos")
        c.post("/staff/kiosk/start", data={"branch_id": bid})
        page = c.post("/kiosk", data=self.form(birth_date="2018-05-05")).data.decode()
        self.assertIn("parent or guardian", page)
        c.post("/kiosk", data=self.form(birth_date="2018-05-05", guardian_name="Demo Parent", guardian_relation="Mother"))
        c.post("/kiosk/exit", data={"password": PW})
        reg = self.q("SELECT * FROM kiosk_registrations ORDER BY id DESC")
        self.assertTrue(json.loads(reg["data_json"])["minor"])
        # an existing patient with the same mobile: link instead of a second record
        ex = self.q("SELECT * FROM patients WHERE preferred_branch_id = ? LIMIT 1", (bid,))
        self.conn.execute("UPDATE patients SET phone = '09171234567' WHERE id = ?", (ex["id"],))
        self.assertIn(ex["chart_no"], c.get(f"/staff/registrations/{reg['id']}").data.decode())
        c.post(f"/staff/registrations/{reg['id']}", data={"action": "link", "patient_id": ex["id"]})
        self.assertEqual(self.q("SELECT patient_id FROM kiosk_registrations WHERE id = ?", (reg["id"],))["patient_id"], ex["id"])
        # discard deletes the details
        c.post("/staff/kiosk/start", data={"branch_id": bid})
        c.post("/kiosk", data=self.form(first_name="Test", last_name="Entry"))
        c.post("/kiosk/exit", data={"password": PW})
        reg2 = self.q("SELECT * FROM kiosk_registrations ORDER BY id DESC")
        c.post(f"/staff/registrations/{reg2['id']}", data={"action": "reject", "reason": "Test entry"})
        r2 = self.q("SELECT * FROM kiosk_registrations WHERE id = ?", (reg2["id"],))
        self.assertEqual((r2["status"], r2["data_json"], r2["signature_name"]), ("rejected", "{}", ""))
        # other branches' staff can't see it
        self.assertEqual(self.login("reception.bocaue").get(f"/staff/registrations/{reg['id']}").status_code, 404)

from test_app import Base

SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


class TestConsentForms(Base):
    def setUp(self):
        super().setUp()
        self.mal = self.branch("malolos")
        self.pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? AND birth_date < '2000-01-01' LIMIT 1", (self.mal,))["id"]
        self.form = self.q("SELECT * FROM consent_templates WHERE code = 'extraction'")
        self.dentist = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos%'")["id"]

    def _sign(self, client, **kw):
        data = {"form": self.form["id"], "dentist_id": self.dentist, "procedure": "Removal of tooth (demo 5521)", "teeth": "38",
                "signed_by_name": "Demo Signer", "understood": "1", "signature": SIG}
        data.update(kw)
        return client.post(f"/staff/patients/{self.pid}/consents/new", data=data, follow_redirects=True)

    def test_drafts_need_a_dentists_approval(self):
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM consent_templates"), 4)
        self.assertIsNone(self.form["approved_at"])
        r = self.login("reception.malolos")
        before = self.conn.scalar("SELECT COUNT(*) FROM patient_consents")
        self._sign(r)
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM patient_consents"), before)
        self.assertIn("not approved yet", r.get(f"/staff/patients/{self.pid}?tab=consents").data.decode())
        # a receptionist can't approve
        self.assertEqual(r.post(f"/staff/admin/consent-forms/{self.form['id']}", data={"action": "approve"}).status_code, 403)
        d = self.login("dentist.malolos")
        d.post(f"/staff/admin/consent-forms/{self.form['id']}", data={"action": "approve"})
        self.assertIsNotNone(self.q("SELECT approved_at FROM consent_templates WHERE id = ?", (self.form["id"],))["approved_at"])

    def test_sign_view_and_void(self):
        self.conn.execute("UPDATE consent_templates SET approved_at = '2026-11-26 10:00:00', approved_by = ?", (self.dentist,))
        r = self.login("reception.malolos")
        page = self._sign(r, understood="").data.decode()
        self.assertIn("tick that they read", page)
        page = self._sign(r).data.decode()
        c = self.q("SELECT * FROM patient_consents WHERE patient_id = ? AND template_id = ? ORDER BY id DESC", (self.pid, self.form["id"]))
        self.assertIn("demo 5521", c["body"])
        self.assertNotIn("{patient}", c["body"])
        self.assertIn("Demo Signer", page)
        self.assertEqual(r.get(f"/staff/consents/{c['id']}/signature").status_code, 200)
        self.assertIn("Removal of tooth (demo 5521)", r.get(f"/staff/patients/{self.pid}?tab=consents").data.decode())
        # editing the wording keeps the signed copy as it was and clears the approval
        a = self.login("admin")
        a.post(f"/staff/admin/consent-forms/{self.form['id']}", data={"title": self.form["title"], "body": "Changed wording {patient}", "active": "1"})
        self.assertIsNone(self.q("SELECT approved_at FROM consent_templates WHERE id = ?", (self.form["id"],))["approved_at"])
        self.assertIn("demo 5521", self.q("SELECT body FROM patient_consents WHERE id = ?", (c["id"],))["body"])
        self.assertEqual(r.post(f"/staff/consents/{c['id']}/void", data={"reason": "x"}).status_code, 403)
        a.post(f"/staff/consents/{c['id']}/void", data={"reason": "Wrong procedure"})
        self.assertEqual(self.q("SELECT status FROM patient_consents WHERE id = ?", (c["id"],))["status"], "void")

    def test_ortho_uses_clinic_wording_with_address(self):
        from app.consent_ortho import BODY
        t = self.q("SELECT * FROM consent_templates WHERE code = 'ortho'")
        self.assertEqual(t["body"], BODY)
        self.conn.execute("UPDATE consent_templates SET approved_at = '2026-11-26 10:00:00' WHERE id = ?", (t["id"],))
        self.conn.execute("UPDATE patients SET address = '12 Demo St., Sample City' WHERE id = ?", (self.pid,))
        self._sign(self.login("reception.malolos"), form=t["id"], procedure="")
        c = self.q("SELECT body FROM patient_consents WHERE patient_id = ? AND template_id = ? ORDER BY id DESC", (self.pid, t["id"]))
        self.assertIn("residing at 12 Demo St., Sample City, have read all the terms", c["body"])
        self.assertIn("Rebonded Ordinary Bracket: ₱200.00", c["body"])
        self.assertNotIn("{", c["body"])

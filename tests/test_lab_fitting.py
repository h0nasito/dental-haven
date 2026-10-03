"""Trial fitting agreement on a lab case: patient and dentist sign that the case may go on to final processing."""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402
from test_patient_profile import PNG  # noqa: E402

SIG = "data:image/png;base64," + PNG


class TestLabFitting(Base):
    def setUp(self):
        super().setUp()
        self.doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        self.pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (self.doc,))["id"]
        self.lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        self.d = self.login("dentist.malolos")
        r = self.d.post("/staff/lab/new", data={"patient_id": self.pid, "lab_id": self.lab, "branch_id": self.branch("malolos"),
                                                "dentist_id": self.doc, "case_type": "Crown (zirconia / all-ceramic)", "teeth": "36",
                                                "shade": "A2", "sent_on": date.today().isoformat(), "due_on": "", "lab_fee": "",
                                                "material": "", "instructions": "x"})
        self.assertEqual(r.status_code, 302, r.data[:300])
        self.case = int(r.headers["Location"].rstrip("/").split("/")[-1])

    def _fit(self, client=None, **extra):
        data = {"result": "approved", "fitted_on": date.today().isoformat(), "dentist_id": self.doc, "checks": ["Fit", "Bite"],
                "notes": "", "agreement": "", "signer_name": "", "signer_relation": "patient",
                "patient_signature": SIG, "dentist_signature": SIG, "not_signed_reason": ""}
        data.update(extra)
        return (client or self.d).post(f"/staff/lab/{self.case}/fitting", data=data, follow_redirects=True)

    def fittings(self):
        return self.conn.all("SELECT * FROM lab_case_fittings WHERE case_id = ? ORDER BY id", (self.case,))

    def test_case_page_shows_the_agreement_with_case_details(self):
        page = self.d.get(f"/staff/lab/{self.case}").data.decode()
        self.assertIn('id="fitting"', page)
        self.assertIn("Record trial fitting", page)
        self.assertIn("Crown (zirconia / all-ceramic)", page)
        self.assertNotIn("{case_type}", page)
        self.assertEqual(page.count("data-sig-out"), 2)

    def test_approved_needs_both_signatures(self):
        self._fit(dentist_signature="")
        self.assertEqual(self.fittings(), [])
        self._fit(patient_signature="")
        self.assertEqual(self.fittings(), [])
        r = self._fit()
        self.assertIn(b"The lab has been told to proceed", r.data)
        f = self.fittings()
        self.assertEqual(len(f), 1)
        self.assertTrue(f[0]["patient_signature"] and f[0]["dentist_signature"])
        self.assertIn("Crown (zirconia / all-ceramic)", f[0]["agreement_text"])
        self.assertIn("Checked: Fit, Bite", f[0]["notes"])

    def test_patient_who_cant_sign_needs_a_reason(self):
        self._fit(patient_signature="", not_signed_reason="")
        self.assertEqual(self.fittings(), [])
        self._fit(patient_signature="", not_signed_reason="Under anesthesia; mother will sign at pickup", signer_relation="parent")
        f = self.fittings()[0]
        self.assertIsNone(f["patient_signature"])
        self.assertEqual(f["signer_relation"], "parent")

    def test_adjust_needs_notes_and_future_date_refused(self):
        self._fit(result="adjust", notes="")
        self._fit(fitted_on=(date.today() + timedelta(days=2)).isoformat())
        self.assertEqual(self.fittings(), [])
        self._fit(result="adjust", notes="Shorten the margin on the distal side", dentist_signature="")
        self.assertEqual(self.fittings()[0]["result"], "adjust")

    def test_remake_sets_case_status_and_lab_is_notified(self):
        a = self.login("admin")
        a.post("/staff/admin/users/new", data={"name": "DSDL Tech", "email": "tech@dsdl.test", "role": "staff",
                                               "labs": [str(self.lab)], "position": "Technician"})
        tech = self.q("SELECT id FROM users WHERE email = 'tech@dsdl.test'")["id"]
        self._fit(result="remake", notes="Shade too light")
        self.assertEqual(self.q("SELECT status FROM lab_cases WHERE id = ?", (self.case,))["status"], "remake")
        n = self.q("SELECT * FROM notifications WHERE user_id = ? AND kind = 'lab_case_fitting'", (tech,))
        self.assertIsNotNone(n)
        self.assertNotIn(b"Shade", (n["title"] or "").encode())

    def test_print_page_and_signatures_are_private(self):
        self._fit(notes="Patient happy with the shade")
        fid = self.fittings()[0]["id"]
        page = self.d.get(f"/staff/lab/fitting/{fid}/print").data.decode()
        self.assertIn("Trial Fitting Agreement", page)
        self.assertIn("laboratory may proceed", page)
        r = self.d.get(f"/staff/lab/fitting/{fid}/signature/patient")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r.headers["Cache-Control"])
        self.assertEqual(self.d.get(f"/staff/lab/fitting/{fid}/signature/other").status_code, 404)
        # a lab-only account sees the case but not the signed agreement
        a = self.login("admin")
        r = a.post("/staff/admin/users/new", data={"name": "DSDL Tech", "email": "tech2@dsdl.test", "role": "staff",
                                                   "labs": [str(self.lab)], "position": "Technician"})
        temp = re.search(rb'id="temp-pw"[^>]*>([^<]+)<', r.data).group(1).decode()
        t = self.app.test_client()
        t.post("/staff/login", data={"email": "tech2@dsdl.test", "password": temp})
        t.post("/staff/account/password", data={"current_password": temp, "new_password": "LabTech-2026x",
                                                "confirm_password": "LabTech-2026x"})
        self.assertEqual(t.get(f"/staff/lab/{self.case}").status_code, 200)
        self.assertEqual(t.get(f"/staff/lab/fitting/{fid}/print").status_code, 403)
        self.assertEqual(t.get(f"/staff/lab/fitting/{fid}/signature/patient").status_code, 403)
        self.assertEqual(t.post(f"/staff/lab/{self.case}/fitting", data={"result": "approved"}).status_code, 403)

    def test_agreement_wording_is_editable_and_kept_per_copy(self):
        a = self.login("admin")
        page = a.get("/staff/admin/system").data.decode()
        self.assertIn("lab.fitting_agreement", page)
        self._fit(agreement="Custom wording for this patient.")
        self.assertEqual(self.fittings()[0]["agreement_text"], "Custom wording for this patient.")


class TestLabWorkload(Base):
    """Dentists and receptionists follow the lab workload of every branch; other branches' cases are view only."""

    def setUp(self):
        super().setUp()
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        d = self.login("dentist.malolos")
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "case_type": "Bridge", "teeth": "14-16", "shade": "A3",
                                           "sent_on": (date.today() - timedelta(days=9)).isoformat(),
                                           "due_on": (date.today() - timedelta(days=1)).isoformat(), "lab_fee": "", "material": "",
                                           "instructions": "x"})
        self.case = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.other = self.q("SELECT u.email FROM users u WHERE u.role = 'dentist' AND u.id NOT IN "
                            "(SELECT user_id FROM user_branches WHERE branch_id = ?) LIMIT 1", (self.branch("malolos"),))

    def test_other_branch_dentist_sees_case_and_workload_but_cannot_update(self):
        self.assertIsNotNone(self.other)
        c = self.login(self.other["email"].replace(DOMAIN, ""))
        page = c.get("/staff/lab/").data.decode()
        self.assertIn("Lab workload", page)
        self.assertIn("Bridge", page)
        self.assertIn("Overdue", page)
        r = c.get(f"/staff/lab/{self.case}")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"Update status", r.data)
        self.assertNotIn(b"Record trial fitting", r.data)
        self.assertEqual(c.post(f"/staff/lab/{self.case}", data={"status": "ready"}).status_code, 403)
        # branch filter
        bocaue = c.get(f"/staff/lab/?branch={self.branch('bocaue')}").data.decode()
        self.assertNotIn("14-16", bocaue)
        self.assertIn("14-16", c.get(f"/staff/lab/?branch={self.branch('malolos')}").data.decode())

    def test_receptionist_sees_all_branches(self):
        email = self.q("SELECT email FROM users WHERE role = 'receptionist' AND active = 1 LIMIT 1")
        if not email:
            self.skipTest("no receptionist in demo data")
        c = self.login(email["email"].replace(DOMAIN, ""))
        self.assertIn(b"14-16", c.get("/staff/lab/").data)

    def test_without_permission_only_own_branches(self):
        self.conn.execute("DELETE FROM role_permissions WHERE role = 'dentist' AND permission = 'lab.all_branches'")
        c = self.login(self.other["email"].replace(DOMAIN, ""))
        self.assertNotIn(b"14-16", c.get("/staff/lab/").data)
        self.assertEqual(c.get(f"/staff/lab/{self.case}").status_code, 404)


class TestLabStages(TestLabFitting):
    """Lab stages: Accepted → Setting → Designing → Fabricating → Trimming → Polishing → Quality control → Ready → Delivered."""

    def test_stages_and_try_in(self):
        page = self.d.get(f"/staff/lab/{self.case}").data.decode()
        for label in ("Accepted", "Setting", "Designing", "Fabricating / production", "Trimming", "Polishing", "Quality control",
                      "Ready / packed", "Out for trial fitting", "On hold", "What each status means"):
            self.assertIn(label, page)
        self.d.post(f"/staff/lab/{self.case}", data={"status": "designing", "note": ""})
        self.assertIn("Designing", self.d.get("/staff/lab/").data.decode().split("Lab workload")[1].split("</table>")[0])
        self.d.post(f"/staff/lab/{self.case}", data={"status": "try_in", "note": "Wax try-in"})
        self._fit(notes="")
        self.assertEqual(self.q("SELECT status FROM lab_cases WHERE id = ?", (self.case,))["status"], "accepted")
        self.assertEqual(self.d.post(f"/staff/lab/{self.case}", data={"status": "in_progress"}).status_code, 400)

    def test_overdue_ignores_ready_and_try_in(self):
        self.conn.execute("UPDATE lab_cases SET due_on = ?, status = 'try_in' WHERE id = ?",
                          ((date.today() - timedelta(days=3)).isoformat(), self.case))
        self.assertNotIn("Overdue", self._row())
        self.conn.execute("UPDATE lab_cases SET status = 'polishing' WHERE id = ?", (self.case,))
        self.assertIn("Overdue", self._row())

    def _row(self):
        page = self.d.get("/staff/lab/").data.decode()
        return next(tr for tr in page.split("<tr>") if f'href="/staff/lab/{self.case}"' in tr)


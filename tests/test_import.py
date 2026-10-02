"""MyMedsPH import tests using SYNTHETIC files in the MyMedsPH export layout (no real data)."""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402

PAT_COLS = ['PATIENT ID', 'FIRSTNAME', 'MIDDLENAME', 'LASTNAME', 'BIRTHDAY', 'GENDER', 'MOBILE', 'EMAIL', 'ADDRESS', 'SCHOOL',
            'OCCUPATION', 'CIVIL STATUS', 'PERSON TO CONTACT', 'EMERGENCY NUMBER', 'MEDICAL CONDITION', 'PREVIOUS HOSPITALIZATION',
            'MEDICATIONS', 'ALLEGIES', 'MEDICAL CONCERNS', 'FAMILY MEDICAL CONCERNS', "FATHER'S NAME", "FATHER'S OCCUPATION",
            "FATHER'S EMPLOYER", "FATHER'S MOBILE", "FATHER'S EMAIL", "MOTHER'S NAME", "MOTHER'S OCCUPATION", "MOTHER'S EMPLOYER",
            "MOTHER'S MOBILE", "MOTHER'S EMAIL", 'PHYSICIAN', 'PHYSICIAN CONTACT', 'CONSULTATION REASON', 'DENTAL EXPERIENCE',
            'BRUSHING DIFFICULTY', 'FLUORIDE DETAILS', 'CHILD DIET', 'LAST RECALL', 'LAST RECALL SUMMARY']
PROG_COLS = ['patient_id', 'firstname', 'middlename', 'lastname', 'recall_datetime', 'service', 'tooth_no', 'cost', 'unit_price',
             'discount_amount', 'discount_percent', 'sub_total', 'progress_notes', 'followup_date', 'followup_time', 'followup_reason', 'remarks']
BILL_COLS = ['patient_id', 'firstname', 'middlename', 'lastname', 'bill_dt', 'service_type', 'item', 'qty', 'unit', 'unit_price',
             'discount_amount', 'discount_percentage', 'total_amount', 'remarks', 'status']
PLAN_COLS = ['patient_id', 'firstname', 'middlename', 'lastname', 'datetime', 'plan_procedure', 'tooth_no', 'cost', 'unit_price',
             'service_discount_amount', 'service_discount_percent', 'appt_no', 'remarks']
NOTE_COLS = ['PATIENT ID', 'FIRSTNAME', 'MIDDLENAME', 'LASTNAME', 'Date/Time', 'Note']
RX_COLS = ['patient_id', 'firstname', 'middlename', 'lastname', 'prescribed_date', 'medicine', 'dosage', 'quantity', 'remarks']


def _csv(cols, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue().encode("utf-8")


def synthetic_export(mobile_for_first="09170000001"):
    future = (date.today() + timedelta(days=10)).isoformat()
    pats = [
        {"PATIENT ID": "900001", "FIRSTNAME": "Testa", "MIDDLENAME": "Q", "LASTNAME": "Sample", "BIRTHDAY": "1990-05-01", "GENDER": "female",
         "MOBILE": mobile_for_first, "EMAIL": "", "ADDRESS": "Synthetic St.", "CIVIL STATUS": "single", "ALLEGIES": "Penicillin",
         "MEDICATIONS": "none", "CONSULTATION REASON": "Toothache", "LAST RECALL": "2026-01-10"},
        {"PATIENT ID": "9000002", "FIRSTNAME": "Demo", "LASTNAME": "Person", "BIRTHDAY": "0000-00-00", "GENDER": "male",
         "MOBILE": "'+639170000002", "LAST RECALL": "0000-00-00"},
        {"PATIENT ID": "", "FIRSTNAME": "No", "LASTNAME": "Id"},  # invalid row
    ]
    prog = [
        {"patient_id": "900001", "recall_datetime": "2025-03-02", "service": "Oral prophylaxis (Mild)", "tooth_no": "", "cost": "800.00",
         "sub_total": "0.00", "remarks": "ok"},
        {"patient_id": "900001", "recall_datetime": "2025-04-02", "service": "Restoration/Pasta- Posterior/Likod", "tooth_no": "36, 37",
         "cost": "1500.00", "followup_date": future, "followup_time": "14:00:00", "followup_reason": "Check filling"},
        {"patient_id": "9000002", "recall_datetime": "2024-11-20", "service": "Consultation", "cost": "500.00"},
        {"patient_id": "123", "recall_datetime": "2024-11-20", "service": "Orphan"},  # unknown patient
    ]
    bills = [
        {"patient_id": "900001", "bill_dt": "2025-03-02", "service_type": "Oral prophylaxis (Mild)", "qty": "1", "unit": "pcs",
         "unit_price": "800.00", "discount_amount": "0.00", "discount_percentage": "0.00", "total_amount": "800", "status": "4"},
        {"patient_id": "9000002", "bill_dt": "2024-11-20", "service_type": "Consultation", "qty": "1", "unit": "pcs",
         "unit_price": "500.00", "discount_amount": "0.00", "discount_percentage": "0.00", "total_amount": "500", "status": "2"},
    ]
    plans = [{"patient_id": "900001", "datetime": "2025-04-02 10:00:00", "plan_procedure": "Crown", "tooth_no": "36", "cost": "8000.00",
              "appt_no": "1", "remarks": "after RCT"}]
    notes = [{"PATIENT ID": "900001", "Date/Time": "2025-04-02 10:00:00", "Note": "Synthetic note"}]
    rx = [{"patient_id": "900001", "prescribed_date": "2025-04-02", "medicine": "Amoxicillin", "dosage": "500mg", "quantity": "21"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("patients.csv", _csv(PAT_COLS, pats))
        zf.writestr("progress_notes.csv", _csv(PROG_COLS, prog))
        zf.writestr("bills.csv", _csv(BILL_COLS, bills))
        zf.writestr("treatment_plans.csv", _csv(PLAN_COLS, plans))
        zf.writestr("notes.csv", _csv(NOTE_COLS, notes))
        zf.writestr("prescriptions.csv", _csv(RX_COLS, rx))
        zf.writestr("export_errors.csv", b"Sheet,Error\n")
    return buf.getvalue()


class TestMyMedsImport(Base):
    def _upload(self, c, data, branch):
        return c.post("/staff/admin/import", data={"branch_id": str(branch), "files": (io.BytesIO(data), "mymedsph_export.zip")},
                      content_type="multipart/form-data")

    def test_only_super_admin(self):
        c = self.login("staff.malolos")
        self.assertEqual(c.get("/staff/admin/import").status_code, 403)

    def test_preview_then_import_then_reimport(self):
        c = self.login("admin")
        branch = self.branch("bocaue")
        r = self._upload(c, synthetic_export(), branch)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Nothing has been saved yet", r.data)
        self.assertIsNone(self.q("SELECT id FROM patients WHERE legacy_id = '900001'"))  # preview writes nothing
        token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
        r = c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"}, follow_redirects=True)
        self.assertIn(b"Import finished: 2 new patients", r.data)
        p = self.q("SELECT * FROM patients WHERE legacy_id = '900001'")
        self.assertEqual((p["first_name"], p["middle_name"], p["chart_no"], p["preferred_branch_id"]), ("Testa", "Q", "MM-900001", branch))
        self.assertEqual(p["alert_flag"], "Allergy: Penicillin")
        self.assertEqual(p["consent_privacy"], 0)
        h = self.q("SELECT * FROM patient_history WHERE patient_id = ?", (p["id"],))
        self.assertEqual(h["medications"], "")  # "none" is treated as empty
        self.assertIn("Toothache", h["dental_history"])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM procedures WHERE patient_id = ?", (p["id"],))["n"], 2)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM follow_ups WHERE patient_id = ? AND status='open'", (p["id"],))["n"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM clinical_notes WHERE patient_id = ?", (p["id"],))["n"], 1)
        self.assertEqual(self.q("SELECT i.medicine FROM prescriptions r JOIN prescription_items i ON i.prescription_id = r.id "
                                "WHERE r.patient_id = ?", (p["id"],))["medicine"], "Amoxicillin")
        self.assertEqual(self.q("SELECT total_cents FROM legacy_bills WHERE patient_id = ?", (p["id"],))["total_cents"], 80000)
        p2 = self.q("SELECT * FROM patients WHERE legacy_id = '9000002'")
        self.assertIsNone(p2["birth_date"])
        self.assertEqual(p2["phone"], "+639170000002")
        self.assertIsNone(self.q("SELECT id FROM patients WHERE first_name = 'No' AND last_name = 'Id'"))
        # imported bills stay out of the new invoices/sales
        self.assertIsNone(self.q("SELECT id FROM invoices WHERE patient_id = ?", (p["id"],)))
        # patient page shows history for billing users
        page = self.login("staff.bocaue").get(f"/staff/patients/{p['id']}?tab=billing")
        self.assertIn(b"Previous bills from MyMedsPH", page.data)
        # staff edits history in Dental Haven; re-import with a changed mobile must not duplicate or overwrite it
        self.conn.execute("UPDATE patient_history SET allergies = 'Penicillin, latex (confirmed)' WHERE patient_id = ?", (p["id"],))
        r = self._upload(c, synthetic_export(mobile_for_first="09179999999"), self.branch("malolos"))
        token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
        r = c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"}, follow_redirects=True)
        self.assertIn(b"0 new patients, 1 updated", r.data)
        p = self.q("SELECT * FROM patients WHERE legacy_id = '900001'")
        self.assertEqual(p["phone"], "09179999999")
        self.assertEqual(p["preferred_branch_id"], branch)  # branch kept
        self.assertEqual(self.q("SELECT allergies FROM patient_history WHERE patient_id = ?", (p["id"],))["allergies"], "Penicillin, latex (confirmed)")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM procedures WHERE patient_id = ?", (p["id"],))["n"], 2)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM legacy_bills WHERE patient_id = ?", (p["id"],))["n"], 1)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM import_runs WHERE status = 'done' AND filename = 'mymedsph_export.zip'")["n"], 2)
        # uploaded files are not kept
        self.assertFalse(list(Path(self.app.config["IMPORT_DIR"]).glob("*.upload")))

    def test_bad_file(self):
        c = self.login("admin")
        r = c.post("/staff/admin/import", data={"branch_id": str(self.branch("malolos")), "files": (io.BytesIO(b"hello"), "x.zip")},
                   content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"could not be opened", r.data)

    def test_shared_import_of_separate_csv_files(self):
        """A clinic-wide export: several CSV files uploaded together, patients shared by all branches."""
        c = self.login("admin")
        future = (date.today() + timedelta(days=5)).isoformat()
        pats = [{"PATIENT ID": "950001", "FIRSTNAME": "Shared", "LASTNAME": "Synthetic", "BIRTHDAY": "1985-02-03", "GENDER": "male",
                 "MOBILE": "09175550001"}]
        prog = [{"patient_id": "950001", "recall_datetime": "2025-01-05", "service": "Consultation", "cost": "500.00",
                 "followup_date": future, "followup_time": "10:00:00", "followup_reason": "Recall"}]
        bills = [{"patient_id": "950001", "bill_dt": "2025-01-05", "service_type": "Consultation", "qty": "1", "unit": "pcs",
                  "unit_price": "500.00", "total_amount": "500", "status": "4"}]
        files = [(io.BytesIO(_csv(PAT_COLS, pats)), "patients.csv"), (io.BytesIO(_csv(PROG_COLS, prog)), "progress_notes.csv"),
                 (io.BytesIO(_csv(BILL_COLS, bills)), "bills.csv"), (io.BytesIO(b"Sheet,Error\n"), "export_errors.csv")]
        r = c.post("/staff/admin/import", data={"branch_id": "all", "files": files}, content_type="multipart/form-data")
        self.assertIn(b"all branches (shared)", r.data)
        token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
        r = c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"}, follow_redirects=True)
        self.assertIn(b"Import finished: 1 new patients", r.data)
        self.assertIn(b"All branches", c.get("/staff/admin/import").data)
        p = self.q("SELECT * FROM patients WHERE legacy_id = '950001'")
        self.assertEqual((p["shared"], p["preferred_branch_id"]), (1, None))
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM procedures WHERE patient_id = ?", (p["id"],))["n"], 1)
        self.assertEqual(self.q("SELECT total_cents FROM legacy_bills WHERE patient_id = ?", (p["id"],))["total_cents"], 50000)
        # staff of any branch can open the patient and see the recall follow-up
        for who in ("reception.malolos", "reception.sjdm"):
            s = self.login(who)
            self.assertEqual(s.get(f"/staff/patients/{p['id']}").status_code, 200, who)
            self.assertIn(b"Synthetic", s.post("/staff/patients/", data={"q": "Shared"}, follow_redirects=True).data, who)
            self.assertIn(b"Recall", s.get("/staff/followups?view=upcoming").data, who)
        self.assertIn(b"All branches", self.login("reception.sjdm").post("/staff/patients/", data={"q": "Shared"}, follow_redirects=True).data)
        # dentists (their role can view patients) see it too; lab-only roles can't
        self.assertEqual(self.login("dentist.sjdm").get(f"/staff/patients/{p['id']}").status_code, 200)
        # every patient is visible in every branch, not only imported ones
        other = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? AND shared = 0 LIMIT 1", (self.branch("malolos"),))
        self.assertEqual(self.login("reception.sjdm").get(f"/staff/patients/{other['id']}").status_code, 200)

    def test_identical_rows_are_all_imported_and_problem_list(self):
        """Two identical bill lines (same service twice on the same day) are both kept; re-import adds nothing;
        skipped rows can be downloaded with file, line, patient ID and reason only."""
        c = self.login("admin")
        pats = [{"PATIENT ID": "960001", "FIRSTNAME": "Twin", "LASTNAME": "Rows", "BIRTHDAY": "1990-01-01", "GENDER": "female"}]
        bill = {"patient_id": "960001", "bill_dt": "2025-02-02", "service_type": "Restoration", "qty": "1", "unit": "pcs",
                "unit_price": "1000.00", "total_amount": "1000", "status": "4"}
        bills = [bill, dict(bill), {**bill, "patient_id": "999999"}, {**bill, "bill_dt": "0000-00-00"}]
        files = lambda: [(io.BytesIO(_csv(PAT_COLS, pats)), "patients.csv"), (io.BytesIO(_csv(BILL_COLS, bills)), "bills.csv")]  # noqa: E731
        r = c.post("/staff/admin/import", data={"branch_id": "all", "files": files()}, content_type="multipart/form-data")
        html = r.data.decode()
        self.assertIn("bills.csv: patient ID not found in patients file - skipped", html)
        self.assertIn("bills.csv: invalid bill date - skipped", html)
        token = re.search(r'name="token" value="([^"]+)"', html).group(1)
        csv_resp = c.post("/staff/admin/import/problems", data={"token": token})
        body = csv_resp.data.decode("utf-8-sig")
        self.assertIn("File,Line in file,MyMedsPH patient ID,Problem", body)
        self.assertIn("bills.csv,4,999999,patient ID not found", body)
        self.assertNotIn("Twin", body)
        c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"})
        p = self.q("SELECT id FROM patients WHERE legacy_id = '960001'")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM legacy_bills WHERE patient_id = ?", (p["id"],))["n"], 2)
        # importing the same files again adds nothing
        r = c.post("/staff/admin/import", data={"branch_id": "all", "files": files()}, content_type="multipart/form-data")
        token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
        c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM legacy_bills WHERE patient_id = ?", (p["id"],))["n"], 2)

    def test_rich_text_notes_become_plain_text(self):
        """MyMedsPH notes saved as HTML (<ul><li><strong>, &amp;) are imported as clean text with line breaks;
        visits imported earlier with the HTML codes are fixed when the export is imported again."""
        from app.util import html_to_text
        self.assertEqual(html_to_text("<ul><li><strong>TOOTH 26 IRRIGATION &amp; ENLARGE</strong></li><li>26(D)</li></ul><p><br></p><ul><li>26(M)</li><li><stron"),
                         "• TOOTH 26 IRRIGATION & ENLARGE\n• 26(D)\n\n• 26(M)")
        self.assertEqual(html_to_text("Oral prophylaxis (Mild)"), "Oral prophylaxis (Mild)")
        c = self.login("admin")
        pats = [{"PATIENT ID": "970001", "FIRSTNAME": "Rich", "LASTNAME": "Text", "BIRTHDAY": "1990-01-01", "GENDER": "male"}]
        html_note = "<ul><li><strong>TOOTH NO. 26 (3 CANALS) IRRIGATION &amp; CANAL ENLARGE</strong></li><li><strong>WL- 20mm</strong></li></ul>"
        prog = [{"patient_id": "970001", "recall_datetime": "2025-07-23", "service": "Root Canal Treatment", "tooth_no": "26",
                 "progress_notes": html_note}]
        files = lambda: [(io.BytesIO(_csv(PAT_COLS, pats)), "patients.csv"), (io.BytesIO(_csv(PROG_COLS, prog)), "progress_notes.csv")]  # noqa: E731
        r = c.post("/staff/admin/import", data={"branch_id": "all", "files": files()}, content_type="multipart/form-data")
        token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
        c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"})
        p = self.q("SELECT id FROM patients WHERE legacy_id = '970001'")
        proc = self.q("SELECT * FROM procedures WHERE patient_id = ?", (p["id"],))
        self.assertEqual(proc["description"], "Root Canal Treatment\n• TOOTH NO. 26 (3 CANALS) IRRIGATION & CANAL ENLARGE\n• WL- 20mm")
        # simulate a visit imported by the old version (HTML codes, cut off), then import again: it gets fixed
        self.conn.execute("UPDATE procedures SET description = ? WHERE id = ?", ("Root Canal Treatment - " + html_note[:60], proc["id"]))
        r = c.post("/staff/admin/import", data={"branch_id": "all", "files": files()}, content_type="multipart/form-data")
        token = re.search(rb'name="token" value="([^"]+)"', r.data).group(1).decode()
        c.post("/staff/admin/import/confirm", data={"token": token, "action": "confirm"})
        self.assertEqual(self.q("SELECT description FROM procedures WHERE id = ?", (proc["id"],))["description"],
                         "Root Canal Treatment\n• TOOTH NO. 26 (3 CANALS) IRRIGATION & CANAL ENLARGE\n• WL- 20mm")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM procedures WHERE patient_id = ?", (p["id"],))["n"], 1)
        page = c.get(f"/staff/patients/{p['id']}?tab=notes").data.decode()
        self.assertNotIn("&lt;strong&gt;", page)
        self.assertIn("IRRIGATION &amp; CANAL ENLARGE", page)

    def test_startup_cleans_html_in_records_already_imported(self):
        from app.seed import seed_base
        from app.util import now_str
        pid = self.q("SELECT id FROM patients ORDER BY id LIMIT 1")["id"]
        author = self.q("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1")["id"]
        nid = self.conn.insert("clinical_notes", {"patient_id": pid, "author_id": author, "body": "<p>Pain on <strong>36</strong> &amp; 37</p>",
                                                  "created_at": now_str(), "legacy_key": "cleanup-test-1"})
        self.conn.execute("DELETE FROM settings WHERE key = 'seed.html_cleanup_v1'")
        with self.app.app_context():
            seed_base(self.conn)
        self.assertEqual(self.q("SELECT body FROM clinical_notes WHERE id = ?", (nid,))["body"], "Pain on 36 & 37")

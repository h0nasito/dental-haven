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
        page = self.login("staff.bocaue").get(f"/staff/patients/{p['id']}")
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
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM import_runs WHERE status = 'done'")["n"], 2)
        # uploaded files are not kept
        self.assertFalse(list(Path(self.app.config["IMPORT_DIR"]).glob("*.upload")))

    def test_bad_file(self):
        c = self.login("admin")
        r = c.post("/staff/admin/import", data={"branch_id": str(self.branch("malolos")), "files": (io.BytesIO(b"hello"), "x.zip")},
                   content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"could not be opened", r.data)

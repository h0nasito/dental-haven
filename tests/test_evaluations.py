"""Staff evaluation forms: open/close by the admin, answer only with access, results."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestEvaluations(Base):
    def setUp(self):
        super().setUp()
        self.conn.execute("UPDATE evaluation_forms SET status = 'closed'")
    def _form(self):
        return self.q("SELECT * FROM evaluation_forms WHERE title = 'Assistant Checklist'")

    def _answers(self, f, no=(), na=()):
        import json
        data = {}
        for i in json.loads(f["questions_json"]):
            if "q" in i:
                data[f"q{i['n']}"] = "no" if i["n"] in no else ("na" if i["n"] in na else "yes")
        return data

    def test_checklist_seeded_closed_with_70_questions(self):
        import json
        f = self._form()
        self.assertEqual(f["status"], "closed")
        items = json.loads(f["questions_json"])
        self.assertEqual(sum(1 for i in items if "q" in i), 70)
        self.assertEqual(sum(1 for i in items if "section" in i), 4)

    def test_open_answer_close_and_results(self):
        f = self._form()
        admin = self.login("admin")
        emp = self.q("SELECT id FROM employees WHERE active = 1 AND position = 'Dental assistant' LIMIT 1")["id"]
        # closed: even someone with access sees "closed"
        page = admin.get(f"/staff/evaluations/f/{f['slug']}").data.decode()
        self.assertIn("This form is closed", page)
        admin.post(f"/staff/evaluations/{f['id']}/status", data={"action": "open"})
        self.assertEqual(self._form()["status"], "open")
        # an account without the permission can't answer
        front = self.login("staff.malolos")
        r = front.get(f"/staff/evaluations/f/{f['slug']}")
        self.assertEqual(r.status_code, 403)
        self.assertIn("can't answer this form", r.data.decode())
        self.assertEqual(front.post(f"/staff/evaluations/f/{f['slug']}", data={"subject_employee_id": emp}).status_code, 403)
        # signed out: sent to sign in, then back to the form
        anon = self.app.test_client().get(f"/staff/evaluations/f/{f['slug']}")
        self.assertIn("/staff/login", anon.headers["Location"])
        self.assertIn(f"evaluations/f/{f['slug']}", anon.headers["Location"].replace("%2F", "/"))
        # with access (admin): an incomplete answer is refused
        page = admin.get(f"/staff/evaluations/f/{f['slug']}").data.decode()
        self.assertIn("Naka-full uniform ba?", page)
        partial = self._answers(f)
        partial.pop("q70")
        admin.post(f"/staff/evaluations/f/{f['slug']}", data={"subject_employee_id": emp, "eval_date": "2025-07-01", **partial})
        self.assertIsNone(self.q("SELECT id FROM evaluation_responses WHERE form_id = ?", (f["id"],)))
        r = admin.post(f"/staff/evaluations/f/{f['slug']}", data={"subject_employee_id": emp, "eval_date": "2025-07-01",
                                                                  "remarks": "Good work", **self._answers(f, no=(2, 15), na=(49,))})
        self.assertEqual(r.status_code, 302)
        resp = self.q("SELECT * FROM evaluation_responses WHERE form_id = ?", (f["id"],))
        self.assertEqual((resp["yes_count"], resp["no_count"], resp["na_count"], resp["subject_employee_id"]), (67, 2, 1, emp))
        res = admin.get(f"/staff/evaluations/{f['id']}/results").data.decode()
        self.assertIn("97%", res)   # 67 / 69
        csv_text = admin.get(f"/staff/evaluations/{f['id']}/results.csv").data.decode("utf-8-sig")
        self.assertIn("Good work", csv_text)
        self.assertIn("2. Naka-make up ba?", csv_text)
        # close: no new answers
        admin.post(f"/staff/evaluations/{f['id']}/status", data={"action": "close"})
        admin.post(f"/staff/evaluations/f/{f['slug']}", data={"subject_employee_id": emp, "eval_date": "2025-07-02", **self._answers(f)})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM evaluation_responses WHERE form_id = ?", (f["id"],))["n"], 1)
        # new link: old one stops working
        admin.post(f"/staff/evaluations/{f['id']}/status", data={"action": "new_link"})
        self.assertEqual(admin.get(f"/staff/evaluations/f/{f['slug']}").status_code, 404)
        # people without access can't see results
        self.assertEqual(front.get(f"/staff/evaluations/{f['id']}/results").status_code, 403)

    def test_access_given_through_role_access(self):
        f = self._form()
        admin = self.login("admin")
        admin.post(f"/staff/evaluations/{f['id']}/status", data={"action": "open"})
        # dentists can answer by default
        self.assertIsNotNone(self.q("SELECT 1 AS x FROM role_permissions WHERE role = 'dentist' AND permission = 'evaluations.answer'"))
        # give the general Staff role access, then the front-desk account can answer
        self.conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES ('staff', 'evaluations.answer')")
        front = self.login("staff.malolos")
        self.assertEqual(front.get(f"/staff/evaluations/f/{self._form()['slug']}").status_code, 200)
        self.conn.execute("DELETE FROM role_permissions WHERE role = 'staff' AND permission = 'evaluations.answer'")

    def test_admin_creates_and_edits_form(self):
        admin = self.login("admin")
        admin.post("/staff/evaluations/new", data={"title": "Cashier Checklist", "questions": "## Opening\nNaka-uniform ba?\nNaka-on ba ang computer?",
                                                  "allow_na": "1", "target": ["Cashier", "Nonsense"]})
        f = self.q("SELECT * FROM evaluation_forms WHERE title = 'Cashier Checklist'")
        self.assertEqual(f["status"], "closed")
        self.assertIn("Naka-on ba ang computer?", f["questions_json"])
        self.assertEqual(f["target_positions"], "Cashier")

    def test_dentist_evaluates_one_receptionist(self):
        import json
        f = self.q("SELECT * FROM evaluation_forms WHERE title = 'Receptionist Checklist'")
        self.assertEqual(f["target_positions"], "Receptionist")
        self.assertEqual(sum(1 for i in json.loads(f["questions_json"]) if "q" in i), 53)
        self.assertEqual(self._form()["target_positions"], "Dental Assistant")
        self.login("admin").post(f"/staff/evaluations/{f['id']}/status", data={"action": "open"})
        f = self.q("SELECT * FROM evaluation_forms WHERE id = ?", (f["id"],))
        doc = self.login("dentist.sjdm")
        rec = self.q("SELECT id FROM employees WHERE position = 'Receptionist' AND active = 1 AND primary_branch_id = ? LIMIT 1",
                     (self.branch("sjdm"),))["id"]
        other_branch = self.q("SELECT id FROM employees WHERE position = 'Receptionist' AND active = 1 AND primary_branch_id = ? LIMIT 1",
                              (self.branch("malolos"),))["id"]
        assistant = self.q("SELECT id FROM employees WHERE position = 'Dental assistant' AND active = 1 LIMIT 1")["id"]
        # the evaluation list shows each receptionist with an Evaluate button
        idx = doc.get("/staff/evaluations/").data.decode()
        self.assertIn(f"staff={rec}", idx)
        self.assertNotIn(f"staff={other_branch}\"", idx)   # the SJDM dentist only sees SJDM staff
        self.assertNotIn(f"staff={assistant}\"", idx.split("Receptionist Checklist")[1]) if "Receptionist Checklist" in idx else None
        page = doc.get(f"/staff/evaluations/f/{f['slug']}?staff={rec}").data.decode()
        self.assertRegex(page, f'<option value="{rec}" data-branch="\\d*" selected>')
        self.assertNotIn(f'<option value="{assistant}"', page)
        self.assertIn("Nakakapag-reply ba ng 3–5 minutes?", page)
        answers = self._answers(f, no=(1,))
        # an assistant can't be evaluated with the receptionist form
        doc.post(f"/staff/evaluations/f/{f['slug']}", data={"subject_employee_id": assistant, "eval_date": "2025-08-01", **answers})
        self.assertIsNone(self.q("SELECT id FROM evaluation_responses WHERE form_id = ?", (f["id"],)))
        doc.post(f"/staff/evaluations/f/{f['slug']}", data={"subject_employee_id": rec, "eval_date": "2025-08-01", **answers})
        r = self.q("SELECT * FROM evaluation_responses WHERE form_id = ?", (f["id"],))
        self.assertEqual((r["subject_employee_id"], r["yes_count"], r["no_count"]), (rec, 52, 1))
        evaluator = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        self.assertEqual(r["evaluator_id"], evaluator)
        self.assertIn("You last evaluated", doc.get("/staff/evaluations/").data.decode())
        # the dentist can't see the results page (admin only)
        self.assertEqual(doc.get(f"/staff/evaluations/{f['id']}/results").status_code, 403)

    def test_head_staff_form(self):
        import json
        f = self.q("SELECT * FROM evaluation_forms WHERE title = 'Head Staff Evaluation'")
        self.assertEqual((f["target_positions"], f["status"]), ("Head Staff", "closed"))
        items = json.loads(f["questions_json"])
        self.assertEqual((sum(1 for i in items if "q" in i), sum(1 for i in items if "section" in i)), (30, 5))
        from app.evaluation_content import matches_target
        self.assertTrue(matches_target("Head Staff", f["target_positions"]))
        self.assertFalse(matches_target("Receptionist", f["target_positions"]))
        self.assertFalse(matches_target("Dental assistant", "Receptionist"))

    def test_role_clarity_forms_and_who_answers(self):
        from app.util import now_str
        forms = {r["title"]: r for r in self.conn.all("SELECT * FROM evaluation_forms")}
        expected = {"Dental Assistant Evaluation": ("Dental Assistant", "dentists"), "Dental Receptionist Evaluation": ("Receptionist", "dentists"),
                    "Dental Laboratory Receptionist Evaluation": ("Lab Receptionist", "management"),
                    "Head Receptionist Evaluation": ("Head Receptionist", "management"), "Head Staff Evaluation": ("Head Staff", "dentists"),
                    "Dental Staff Consultant Evaluation": ("Dental Staff Consultant", "head_dentist"),
                    "Associate Dentist Evaluation": ("Associate Dentist", "head_dentist"), "Head Dentist Evaluation": ("Head Dentist", "management"),
                    "Finance Officer Evaluation": ("Finance Officer", "management"),
                    "Digital Content Associate Evaluation": ("Digital Content Associate", "management"),
                    "Dental Technician (RPD) Evaluation": ("Dental Technician (RPD)", "dentists"),
                    "Dental Technician (FPD / CAD-CAM) Evaluation": ("Dental Technician (FPD)", "dentists")}
        for title, (target, who) in expected.items():
            self.assertIn(title, forms)
            self.assertEqual((forms[title]["target_positions"], forms[title]["answered_by"], forms[title]["status"]), (target, who, "closed"))
        admin = self.login("admin")
        for title in ("Associate Dentist Evaluation", "Finance Officer Evaluation", "Dental Assistant Evaluation"):
            admin.post(f"/staff/evaluations/{forms[title]['id']}/status", data={"action": "open"})
        # an ordinary dentist: can answer the assistant form, not the management or head-dentist forms
        doc = self.login("dentist.sjdm")
        idx = doc.get("/staff/evaluations/").data.decode()
        self.assertIn("Dental Assistant Evaluation", idx)
        self.assertNotIn("Finance Officer Evaluation", idx)
        self.assertNotIn("Associate Dentist Evaluation", idx)
        r = doc.get(f"/staff/evaluations/f/{forms['Finance Officer Evaluation']['slug']}")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Management", r.data.decode())
        self.assertEqual(doc.get(f"/staff/evaluations/f/{forms['Associate Dentist Evaluation']['slug']}").status_code, 403)
        # make another dentist the Head Dentist and an employee an Associate Dentist
        head = self.q("SELECT u.id FROM users u WHERE u.email = 'dentist.malolos@demo.dentalhaven.test'")
        emp = self.q("SELECT id FROM employees WHERE user_id = ?", (head["id"],))
        self.conn.execute("UPDATE employees SET position = 'Head Dentist' WHERE id = ?", (emp["id"],))
        assoc = self.conn.insert("employees", {"full_name": "Test Associate (demo)", "position": "Associate Dentist", "employment_type": "regular",
                                               "primary_branch_id": self.branch("malolos"), "active": 1, "created_at": now_str()})
        hd = self.login("dentist.malolos")
        page = hd.get(f"/staff/evaluations/f/{forms['Associate Dentist Evaluation']['slug']}").data.decode()
        self.assertIn("Test Associate (demo)", page)
        self.assertIn("Are patient records completed immediately after every procedure?", page)
        self.conn.execute("UPDATE employees SET position = 'Dentist' WHERE id = ?", (emp["id"],))
        self.conn.execute("UPDATE employees SET active = 0 WHERE id = ?", (assoc,))

    def test_rpd_technician_counts_as_technician(self):
        import json
        from app.evaluation_content import matches_target
        f = self.q("SELECT * FROM evaluation_forms WHERE title = 'Dental Technician (RPD) Evaluation'")
        self.assertEqual(sum(1 for i in json.loads(f["questions_json"]) if "q" in i), 21)
        fpd = self.q("SELECT * FROM evaluation_forms WHERE title = 'Dental Technician (FPD / CAD-CAM) Evaluation'")
        self.assertEqual(sum(1 for i in json.loads(fpd["questions_json"]) if "q" in i), 19)
        self.assertTrue(matches_target("Dental Technician (RPD)", f["target_positions"]))
        self.assertFalse(matches_target("Technician", f["target_positions"]))
        from app.util import now_str
        eid = self.conn.insert("employees", {"full_name": "RPD Tech (demo)", "position": "Dental Technician (RPD)", "employment_type": "regular",
                                             "active": 1, "created_at": now_str()})
        from app.lab_commission import technicians
        self.assertIn(eid, [t["id"] for t in technicians(self.conn)])
        # dentists answer it and see lab technicians even when they're not in the dentist's branch
        self.login("admin").post(f"/staff/evaluations/{f['id']}/status", data={"action": "open"})
        page = self.login("dentist.sjdm").get("/staff/evaluations/").data.decode()
        self.assertIn("RPD Tech (demo)", page)
        self.conn.execute("UPDATE employees SET active = 0 WHERE id = ?", (eid,))

"""Import employees from Excel or CSV: preview, then add/update; real names come only from the clinic's own file."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


def make_xlsx(rows):
    """A minimal real .xlsx (inline strings) like Excel would save."""
    def cell(ref, v):
        return f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>'
    sheet_rows = "".join(f'<row r="{i + 1}">' + "".join(cell(f"{chr(65 + j)}{i + 1}", v) for j, v in enumerate(r)) + "</row>"
                         for i, r in enumerate(rows))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/worksheets/sheet1.xml",
                   '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + sheet_rows + "</sheetData></worksheet>")
    return buf.getvalue()


class TestEmployeeImport(Base):
    def test_preview_then_import_xlsx(self):
        admin = self.login("admin")
        page = admin.get("/staff/employees/import")
        self.assertEqual(page.status_code, 200)
        data = make_xlsx([["Name", "Position", "Branch", "Type"],
                          ["Test Person One", "Dental Assistant", "Malolos", "Regular"],
                          ["Test Person Two", "dental technician (fpd)", "", "Probationary"],
                          ["Test Person Three", "Astronaut", "Bocaue", ""],
                          ["Test Person Four", "Receptionist", "Nowhere", ""],
                          ["Bocaue Dental Assistant (demo)", "Head Staff", "Bocaue", ""]])
        r = admin.post("/staff/employees/import", data={"action": "preview", "file": (io.BytesIO(data), "staff.xlsx")},
                       content_type="multipart/form-data")
        html = r.data.decode()
        self.assertIn("Check before importing", html)
        self.assertIn("unknown position “Astronaut”", html)
        self.assertIn("unknown branch “Nowhere”", html)
        self.assertIn("position Dental assistant → Head Staff", html)
        self.assertIsNone(self.q("SELECT id FROM employees WHERE full_name = 'Test Person One'"))   # nothing saved yet
        import html as h, re
        payload = h.unescape(re.search(r'<textarea name="rows_json" hidden>(.*?)</textarea>', html, re.S).group(1))
        admin.post("/staff/employees/import", data={"action": "import", "rows_json": payload})
        one = self.q("SELECT * FROM employees WHERE full_name = 'Test Person One'")
        two = self.q("SELECT * FROM employees WHERE full_name = 'Test Person Two'")
        self.assertEqual((one["position"], one["primary_branch_id"], one["employment_type"]), ("Dental Assistant", self.branch("malolos"), "regular"))
        self.assertEqual((two["position"], two["primary_branch_id"], two["employment_type"]), ("Dental Technician (FPD)", None, "probationary"))
        self.assertIsNone(self.q("SELECT id FROM employees WHERE full_name = 'Test Person Three'"))
        self.assertEqual(self.q("SELECT position FROM employees WHERE full_name = 'Bocaue Dental Assistant (demo)'")["position"], "Head Staff")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM employees WHERE full_name = 'Bocaue Dental Assistant (demo)'")["n"], 1)
        self.conn.execute("UPDATE employees SET position = 'Dental assistant' WHERE full_name = 'Bocaue Dental Assistant (demo)'")
        self.conn.execute("UPDATE employees SET active = 0 WHERE full_name LIKE 'Test Person %'")

    def test_csv_template_and_access(self):
        admin = self.login("admin")
        t = admin.get("/staff/employees/import/template.csv").data.decode("utf-8-sig")
        self.assertTrue(t.startswith("Name,Position,Branch,Type"))
        csv_data = "Name,Position,Branch\r\nCsv Person,Receptionist,SJDM\r\n".encode()
        r = admin.post("/staff/employees/import", data={"action": "preview", "file": (io.BytesIO(csv_data), "list.csv")},
                       content_type="multipart/form-data")
        self.assertIn("Csv Person", r.data.decode())
        bad = admin.post("/staff/employees/import", data={"action": "preview", "file": (io.BytesIO(b"x"), "list.xls")},
                         content_type="multipart/form-data")
        self.assertIn("Old Excel (.xls)", bad.data.decode())
        doc = self.login("dentist.sjdm")
        self.assertEqual(doc.get("/staff/employees/import").status_code, 403)

    def test_users_have_positions_and_logins_from_employees(self):
        admin = self.login("admin")
        bid = self.branch("guiguinto")
        # a new user needs a position
        r = admin.post("/staff/admin/users/new", data={"name": "No Position", "email": "nopos@clinic.test", "role": "receptionist",
                                                       "branches": [str(bid)]})
        self.assertIn("Choose the position.", r.data.decode())
        self.assertIsNone(self.q("SELECT id FROM users WHERE email = 'nopos@clinic.test'"))
        admin.post("/staff/admin/users/new", data={"name": "Has Position", "email": "haspos@clinic.test", "role": "staff",
                                                   "branches": [str(bid)], "position": "Dental Assistant"})
        u = self.q("SELECT id FROM users WHERE email = 'haspos@clinic.test'")
        self.assertEqual(self.q("SELECT position FROM employees WHERE user_id = ?", (u["id"],))["position"], "Dental Assistant")
        # changing the position on the user updates the employee
        admin.post(f"/staff/admin/users/{u['id']}", data={"name": "Has Position", "email": "haspos@clinic.test", "role": "staff",
                                                          "branches": [str(bid)], "position": "Head Staff", "active": "1"})
        self.assertEqual(self.q("SELECT position FROM employees WHERE user_id = ?", (u["id"],))["position"], "Head Staff")
        self.assertIn("Head Staff", admin.get("/staff/admin/users?tab=staff").data.decode())
        # create logins for employees without one (email from the imported list)
        from app.util import now_str
        e1 = self.conn.insert("employees", {"full_name": "Login Person One", "position": "Receptionist", "primary_branch_id": bid,
                                            "email": "login.one@clinic.test", "active": 1, "created_at": now_str()})
        e2 = self.conn.insert("employees", {"full_name": "Login Person Two", "position": "Dental Technician (FPD)", "primary_branch_id": None,
                                            "active": 1, "created_at": now_str()})
        page = admin.get("/staff/admin/users/from-employees").data.decode()
        self.assertIn("Login Person One", page)
        self.assertRegex(page, rf'name="role_{e1}"[^>]*>.*?<option value="receptionist" selected>')
        lab = self.q("SELECT id FROM laboratories WHERE active = 1 LIMIT 1")
        r = admin.post("/staff/admin/users/from-employees", data={
            f"make_{e1}": "1", f"email_{e1}": "login.one@clinic.test", f"role_{e1}": "receptionist",
            f"make_{e2}": "1", f"email_{e2}": "login.two@clinic.test", f"role_{e2}": "technician", f"lab_{e2}": str(lab["id"]) if lab else ""})
        html = r.data.decode()
        self.assertIn("2 login(s) created", html)
        self.assertIn("Temporary password", html)
        one = self.q("SELECT u.* FROM users u JOIN employees e ON e.user_id = u.id WHERE e.id = ?", (e1,))
        self.assertEqual((one["email"], one["access_role"], one["must_change_password"]), ("login.one@clinic.test", "receptionist", 1))
        two = self.q("SELECT u.* FROM users u JOIN employees e ON e.user_id = u.id WHERE e.id = ?", (e2,))
        self.assertEqual(two["access_role"], "technician")
        # a dentist who works in two branches gets both
        malolos, bocaue = self.branch("malolos"), self.branch("bocaue")
        e4 = self.conn.insert("employees", {"full_name": "Rotating Dentist", "position": "Associate Dentist", "primary_branch_id": malolos,
                                            "active": 1, "created_at": now_str()})
        page = admin.get("/staff/admin/users/from-employees").data.decode()
        self.assertRegex(page, rf'name="branches_{e4}" value="{malolos}" checked')
        self.assertNotRegex(page, rf'name="branches_{e4}" value="{bocaue}" checked')
        r = admin.post("/staff/admin/users/from-employees", data={
            f"make_{e4}": "1", f"email_{e4}": "rotating@clinic.test", f"role_{e4}": "dentist",
            f"branches_shown_{e4}": "1", f"branches_{e4}": [str(malolos), str(bocaue)]})
        self.assertIn("1 login(s) created", r.data.decode())
        four = self.q("SELECT id FROM users WHERE email = 'rotating@clinic.test'")
        got = {x["branch_id"] for x in self.conn.all("SELECT branch_id FROM user_branches WHERE user_id = ?", (four["id"],))}
        self.assertEqual(got, {malolos, bocaue})
        # unticking every branch is refused
        e5 = self.conn.insert("employees", {"full_name": "No Branch Ticked", "position": "Receptionist", "primary_branch_id": malolos,
                                            "active": 1, "created_at": now_str()})
        r = admin.post("/staff/admin/users/from-employees", data={
            f"make_{e5}": "1", f"email_{e5}": "nobranch@clinic.test", f"role_{e5}": "receptionist", f"branches_shown_{e5}": "1"})
        self.assertIn("Assign at least one branch", r.data.decode())
        self.assertIsNone(self.q("SELECT id FROM users WHERE email = 'nobranch@clinic.test'"))
        # only the super admin can do this
        self.assertEqual(self.login("staff.malolos").get("/staff/admin/users/from-employees").status_code, 403)
        # a super admin can't be created here
        e3 = self.conn.insert("employees", {"full_name": "Login Person Three", "position": "Staff", "primary_branch_id": bid,
                                            "active": 1, "created_at": now_str()})
        admin.post("/staff/admin/users/from-employees", data={f"make_{e3}": "1", f"email_{e3}": "three@clinic.test", f"role_{e3}": "super_admin"})
        self.assertIsNone(self.q("SELECT id FROM users WHERE email = 'three@clinic.test'"))
        for e in (e1, e2, e3, e4, e5):
            self.conn.execute("UPDATE employees SET active = 0 WHERE id = ?", (e,))

    def test_users_lists_and_quick_deactivate(self):
        admin = self.login("admin")
        assoc = admin.get("/staff/admin/users").data.decode()
        self.assertIn("License no.", assoc)
        self.assertIn("dentist.sjdm@demo.dentalhaven.test", assoc)
        self.assertNotIn("reception.bocaue@demo.dentalhaven.test", assoc)
        staff = admin.get("/staff/admin/users?tab=staff").data.decode()
        self.assertIn("reception.bocaue@demo.dentalhaven.test", staff)
        self.assertNotIn("dentist.sjdm@demo.dentalhaven.test", staff)
        found = admin.get("/staff/admin/users?tab=staff&q=bocaue").data.decode()
        self.assertIn("reception.bocaue@demo.dentalhaven.test", found)
        self.assertNotIn("reception.malolos@demo.dentalhaven.test", found)
        # mobile and specialization saved on the user
        u = self.q("SELECT * FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")
        emp = self.q("SELECT position FROM employees WHERE user_id = ?", (u["id"],))
        admin.post(f"/staff/admin/users/{u['id']}", data={"name": u["name"], "email": u["email"], "role": "dentist", "active": "1",
                                                          "branches": [str(self.branch("sjdm"))], "position": "Associate Dentist",
                                                          "mobile": "0917 000 0000", "specialization": "Orthodontics"})
        u2 = self.q("SELECT mobile, specialization FROM users WHERE id = ?", (u["id"],))
        self.assertEqual((u2["mobile"], u2["specialization"]), ("0917 000 0000", "Orthodontics"))
        self.assertIn("Orthodontics", admin.get("/staff/admin/users").data.decode())
        self.conn.execute("UPDATE employees SET position = ? WHERE user_id = ?", (emp["position"], u["id"]))
        # deactivate / activate from the list
        rec = self.q("SELECT id FROM users WHERE email = 'reception.guiguinto@demo.dentalhaven.test'")["id"]
        admin.post(f"/staff/admin/users/{rec}/active", data={"tab": "staff"})
        self.assertEqual(self.q("SELECT active FROM users WHERE id = ?", (rec,))["active"], 0)
        admin.post(f"/staff/admin/users/{rec}/active", data={"tab": "staff"})
        self.assertEqual(self.q("SELECT active FROM users WHERE id = ?", (rec,))["active"], 1)
        # can't deactivate yourself; non-admins can't use it
        me = self.q("SELECT id FROM users WHERE email = 'admin@demo.dentalhaven.test'")["id"]
        admin.post(f"/staff/admin/users/{me}/active")
        self.assertEqual(self.q("SELECT active FROM users WHERE id = ?", (me,))["active"], 1)
        self.assertEqual(self.login("staff.malolos").post(f"/staff/admin/users/{rec}/active").status_code, 403)

    def test_clinic_list_format(self):
        """A list like the clinic's: headings in column B/D, 'Assistant', 'Technician (RPD)', 'Receptionist / Cashier', lowercase names,
        no Branch column (allowed for the super admin), and a name that already has a login."""
        from app.util import now_str
        admin = self.login("admin")
        uid = self.conn.insert("users", {"email": "linkme@clinic.test", "name": "Link Me Person", "password_hash": "x", "role": "dentist",
                                         "access_role": "dentist", "active": 1, "must_change_password": 1, "created_at": now_str()})
        data = make_xlsx([["", "Name", "", "Position"], ["", "zz lower case", "", "Assistant"], ["", "ZZ Tech One", "", "Technician (RPD)"],
                          ["", "ZZ Tech Two", "", "Technician (FPD)"], ["", "ZZ Front Desk", "", "Receptionist / Cashier"],
                          ["", "ZZ Lab Desk", "", "Laboratory Receptionist"], ["", "Link Me Person", "", "Head Dentist"]])
        r = admin.post("/staff/employees/import", data={"action": "preview", "file": (io.BytesIO(data), "employee.xlsx")},
                       content_type="multipart/form-data")
        html = r.data.decode()
        self.assertNotIn("badge-red", html)
        self.assertIn("Zz Lower Case", html)
        self.assertIn("linked to their existing login", html)
        import html as h, re
        payload = h.unescape(re.search(r'<textarea name="rows_json" hidden>(.*?)</textarea>', html, re.S).group(1))
        admin.post("/staff/employees/import", data={"action": "import", "rows_json": payload})
        got = {e["full_name"]: (e["position"], e["user_id"]) for e in self.conn.all("SELECT * FROM employees WHERE full_name LIKE 'Z%' OR full_name = 'Link Me Person'")}
        self.assertEqual(got["Zz Lower Case"][0], "Dental Assistant")
        self.assertEqual(got["ZZ Tech One"][0], "Dental Technician (RPD)")
        self.assertEqual(got["ZZ Tech Two"][0], "Dental Technician (FPD)")
        self.assertEqual(got["ZZ Front Desk"][0], "Receptionist")
        self.assertEqual(got["ZZ Lab Desk"][0], "Lab Receptionist")
        self.assertEqual(got["Link Me Person"], ("Head Dentist", uid))
        self.conn.execute("UPDATE employees SET active = 0 WHERE full_name LIKE 'Z%' OR full_name = 'Link Me Person'")

"""Lab works report: works and branch cases with technician, dates and payment."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_works as base  # noqa: E402


class TestLabWorksReport(base.TestLabWorks):
    pass


# run only the tests below, not the inherited ones
for _name in [n for n in dir(base.TestLabWorks) if n.startswith("test_")]:
    setattr(TestLabWorksReport, _name, None)


def test_report(self):
    from app import lab_works_report as wr
    from app.util import now_str, today
    self.grant("lab.works", "lab.billing")
    c = self.tech()
    t = today().isoformat()
    # a technician (employee) for the commission
    emp = self.conn.insert("employees", {"full_name": "Report Tech (demo)", "position": "Dental Technician", "active": 1, "created_at": now_str()})
    paid_w = self.new_work(c, clinic_name="Report Clinic A", case_type="Complete denture", units="1", price="4000")
    open_w = self.new_work(c, clinic_name="Report Clinic B", case_type="Retainer", units="2", price="1500")
    admin = self.login("admin")
    admin.post("/staff/lab/commission", data={"work_id": paid_w["id"], "employee_id": emp, "amount": "300"})
    iid = int(c.post(f"/staff/lab/works/{paid_w['id']}/bill").headers["Location"].rstrip("/").split("/")[-1])
    c.post(f"/staff/lab/invoices/{iid}", data={"action": "issue"})
    c.post(f"/staff/lab/invoices/{iid}", data={"action": "pay", "amount": "4000", "method": "cash", "received_on": ""})
    self.conn.execute("UPDATE lab_works SET status = 'delivered', delivered_on = ? WHERE id = ?", (t, paid_w["id"]))

    rep = wr.build(self.conn, [self.lab], t, t)
    rows = {r["ref"]: r for r in rep["rows"]}
    a, b = rows[paid_w["number"]], rows[open_w["number"]]
    self.assertEqual((a["payment"], a["amount"], a["paid"], a["tech_names"]), ("paid", 400000, 400000, "Report Tech (demo)"))
    self.assertEqual(a["delivered"], t)
    self.assertEqual(a["days"], 0)
    self.assertEqual(b["payment"], "unbilled")
    self.assertIn("Retainer", b["what"])
    techs = dict(rep["by_tech"])
    self.assertEqual(techs["Report Tech (demo)"]["commission"], 30000)

    # filters
    only = wr.build(self.conn, [self.lab], t, t, technician=emp)
    self.assertEqual([r["ref"] for r in only["rows"]], [paid_w["number"]])
    self.assertEqual([r["ref"] for r in wr.build(self.conn, [self.lab], t, t, payment="unbilled")["rows"] if r["ref"] == paid_w["number"]], [])
    self.assertEqual([r["ref"] for r in wr.build(self.conn, [self.lab], t, t, basis="delivered")["rows"] if r["ref"] == open_w["number"]], [])

    page = c.get(f"/staff/lab/works-report?from={t}&to={t}").data.decode()
    self.assertIn("Lab works report", page)
    self.assertIn("Report Clinic A", page)
    self.assertIn("Report Tech (demo)", page)
    csv = c.get(f"/staff/lab/works-report?from={t}&to={t}&format=csv").data.decode()
    self.assertIn("Complete denture", csv)
    self.assertIn("Paid", csv)
    # technicians without lab billing can't open it
    self.revoke()
    self.grant("lab.works")
    self.assertEqual(self.tech().get("/staff/lab/works-report").status_code, 403)


TestLabWorksReport.test_report = test_report

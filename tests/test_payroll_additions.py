"""Payroll additions (allowances, quota hit, incentives, bonuses) and deductions, regular allowances, printable payslips."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_payroll_rules import TestPayrollRules  # noqa: E402


class TestPayrollAdditions(TestPayrollRules):
    for _n in [n for n in dir(TestPayrollRules) if n.startswith("test_")]:
        locals()[_n] = None

    def test_additions_deductions_allowance_payslip(self):
        admin = self.login("admin")
        eid, bid = self._employee("Additions Test Assistant")
        for day in ("2025-06-02", "2025-06-03", "2025-06-04"):
            self._record(admin, eid, bid, day, "08:00", "17:00")
        # regular allowance: ₱50 per day present
        admin.post(f"/staff/employees/{eid}", data={"action": "allowance_add", "name": "Transportation allowance", "amount": "50", "basis": "per_day"})
        r = admin.post("/staff/payroll", data={"start_date": "2025-06-01", "end_date": "2025-06-15", "branch_id": bid, "name": "Jun 1-15 add"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        auto = self.q("SELECT * FROM payroll_items WHERE period_id = ? AND employee_id = ?", (pid, eid))
        self.assertEqual((auto["name"], auto["amount_cents"], auto["kind"]), ("Transportation allowance", 15000, "addition"))
        admin.post(f"/staff/payroll/{pid}/items", data={"employee_id": eid, "name": "Quota hit", "amount": "1,000", "note": "June quota"})
        admin.post(f"/staff/payroll/{pid}/items", data={"employee_id": eid, "name": "Bonus", "amount": "500"})
        admin.post(f"/staff/payroll/{pid}/items", data={"employee_id": eid, "name": "Cash advance", "amount": "300"})
        admin.post(f"/staff/payroll/{pid}/items", data={"employee_id": eid, "name": "Not a type", "amount": "300"})   # refused
        items = self.conn.all("SELECT kind, name, amount_cents FROM payroll_items WHERE period_id = ? AND employee_id = ? ORDER BY id", (pid, eid))
        self.assertEqual(len(items), 4)
        self.assertEqual([i["kind"] for i in items], ["addition", "addition", "addition", "deduction"])
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, eid))
        from app.payroll import net_pay, period_items
        it = period_items(self.conn, pid)[eid]
        self.assertEqual(net_pay(line, it), line["estimate_cents"] + 15000 + 100000 + 50000 - 30000)
        # recalculating keeps manual items and refreshes the automatic allowance
        admin.post(f"/staff/payroll/{pid}", data={"action": "rebuild"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM payroll_items WHERE period_id = ? AND employee_id = ?", (pid, eid))["n"], 4)
        page = admin.get(f"/staff/payroll/{pid}").data.decode()
        self.assertIn("Additions &amp; deductions", page)
        self.assertIn("Quota hit", page)
        slip = admin.get(f"/staff/payroll/{pid}/payslip/{eid}").data.decode()
        for part in ("PAYSLIP", "Additions Test Assistant", "Quota hit", "June quota", "Cash advance", "Transportation allowance", "NET PAY",
                     f"{net_pay(line, it) / 100:,.2f}"):
            self.assertIn(part, slip)
        self.assertEqual(admin.get(f"/staff/payroll/{pid}/payslips").status_code, 200)
        self.assertIn("Net pay (PHP)", admin.get(f"/staff/payroll/{pid}/export.csv").data.decode())
        # removing an item; HR without compensation access can't print payslips
        cash = self.q("SELECT id FROM payroll_items WHERE period_id = ? AND name = 'Cash advance'", (pid,))
        admin.post(f"/staff/payroll/{pid}/items", data={"action": "remove", "item_id": cash["id"]})
        self.assertIsNone(self.q("SELECT id FROM payroll_items WHERE id = ?", (cash["id"],)))
        self.assertIn(self.login("reception.malolos").get(f"/staff/payroll/{pid}/payslip/{eid}").status_code, (403, 302))

    def test_regular_deductions_and_loan(self):
        admin = self.login("admin")
        eid, bid = self._employee("Deductions Test Assistant")
        for day in ("2025-07-01", "2025-07-02", "2025-07-16"):
            self._record(admin, eid, bid, day, "08:00", "17:00")
        admin.post(f"/staff/employees/{eid}", data={"action": "deduction_add", "name": "SSS", "amount": "450", "schedule": "second"})
        admin.post(f"/staff/employees/{eid}", data={"action": "deduction_add", "name": "PhilHealth", "amount": "250.01", "schedule": "split"})
        admin.post(f"/staff/employees/{eid}", data={"action": "deduction_add", "name": "Pag-IBIG", "amount": "200", "schedule": "first"})
        admin.post(f"/staff/employees/{eid}", data={"action": "deduction_add", "name": "SSS loan", "amount": "1000", "schedule": "every",
                                                    "loan_total": "1500", "reference": "LN-1"})
        r = admin.post("/staff/payroll", data={"start_date": "2025-07-01", "end_date": "2025-07-15", "branch_id": bid, "name": "Jul A ded"})
        p1 = int(r.headers["Location"].rsplit("/", 1)[1])
        got = {i["name"]: i["amount_cents"] for i in self.conn.all("SELECT * FROM payroll_items WHERE period_id = ? AND employee_id = ?", (p1, eid))}
        self.assertEqual(got, {"PhilHealth": 12500, "Pag-IBIG": 20000, "SSS loan": 100000})
        r = admin.post("/staff/payroll", data={"start_date": "2025-07-16", "end_date": "2025-07-31", "branch_id": bid, "name": "Jul B ded"})
        p2 = int(r.headers["Location"].rsplit("/", 1)[1])
        got = {i["name"]: i["amount_cents"] for i in self.conn.all("SELECT * FROM payroll_items WHERE period_id = ? AND employee_id = ?", (p2, eid))}
        self.assertEqual(got, {"SSS": 45000, "PhilHealth": 12501, "SSS loan": 50000})    # loan: only the ₱500 balance left
        page = admin.get(f"/staff/employees/{eid}").data.decode()
        self.assertIn("fully paid", page)
        self.assertIn("Deductions to remit", admin.get(f"/staff/payroll/{p2}").data.decode())
        # cancelling the first period gives the loan balance back
        admin.post(f"/staff/payroll/{p1}", data={"action": "cancel"})
        admin.post(f"/staff/payroll/{p2}", data={"action": "rebuild"})
        self.assertEqual(self.q("SELECT amount_cents FROM payroll_items WHERE period_id = ? AND name = 'SSS loan'", (p2,))["amount_cents"], 100000)


del TestPayrollRules

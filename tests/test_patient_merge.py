from test_app import Base


class TestPatientMerge(Base):
    def test_merge_two_records(self):
        from app.util import now_str
        mal = self.branch("malolos")
        common = {"last_name": "Mergetest", "first_name": "Demo", "active": 1, "created_at": now_str()}
        keep = self.conn.insert("patients", {**common, "chart_no": "MRG-1", "preferred_branch_id": mal, "consent_privacy": 1, "consent_privacy_at": now_str()})
        dup = self.conn.insert("patients", {**common, "chart_no": "MRG-2", "shared": 1, "legacy_id": "777001", "address": "Demo address 9"})
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": dup, "status": "issued", "number": "MRG-INV", "issued_at": "2026-11-01",
                                            "subtotal_cents": 12300, "discount_cents": 0, "tax_cents": 0, "total_cents": 12300, "created_at": now_str()})
        self.assertEqual(self.login("reception.malolos").post("/staff/patients/merge", data={"a": keep, "b": dup, "keep": keep}).status_code, 403)
        a = self.login("admin")
        page = a.get(f"/staff/patients/merge?a={keep}&b={dup}").data.decode()
        self.assertIn("MRG-1", page)
        self.assertIn("Bills 1", page)
        a.post("/staff/patients/merge", data={"a": keep, "b": dup, "keep": keep})
        self.assertEqual(self.q("SELECT patient_id FROM invoices WHERE id = ?", (inv,))["patient_id"], keep)
        k = self.q("SELECT * FROM patients WHERE id = ?", (keep,))
        self.assertEqual((k["legacy_id"], k["address"], k["shared"]), ("777001", "Demo address 9", 1))
        self.assertIn("MRG-2", k["admin_notes"])
        d = self.q("SELECT * FROM patients WHERE id = ?", (dup,))
        self.assertEqual((d["active"], d["deleted_reason"]), (0, "Merged into MRG-1"))

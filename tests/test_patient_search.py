"""Patient search: words in any order, spaces / ñ / commas ignored, suggestions while typing, branch scope respected."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestPatientSearch(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from app.util import now_str
        b = cls.conn.one("SELECT preferred_branch_id AS b FROM patients WHERE active = 1 AND preferred_branch_id IS NOT NULL LIMIT 1")["b"]
        cls.pid = cls.conn.insert("patients", {"first_name": "Juanito", "middle_name": "Santos", "last_name": "Dela Peña QT", "chart_no": "QT-778",
                                               "preferred_branch_id": b, "active": 1, "created_at": now_str(), "updated_at": now_str()})

    def found(self, c, q):
        return c.post("/staff/patients/suggest", data={"q": q}).get_json()["results"]

    def test_words_any_order_and_suggestions(self):
        c = self.login("admin")
        for q in ("juanito dela", "dela pena juanito", "delapena", "Dela Peña, Juanito", "qt-778", "pena qt juan s", "QT-778"):
            ids = [r["id"] for r in self.found(c, q)]
            self.assertIn(self.pid, ids, q)
        r = self.found(c, "delapena")[0]
        self.assertEqual(r["name"], "Dela Peña QT, Juanito S.")
        self.assertEqual(r["url"], f"/staff/patients/{self.pid}")
        self.assertNotIn(self.pid, [r["id"] for r in self.found(c, "juanito reyes")])
        self.assertEqual(self.found(c, "j"), [])
        # the full list search uses the same matching
        page = c.post("/staff/patients/", data={"q": "pena juanito"}).data.decode()
        self.assertIn("Juanito", page)
        # suggestions are POST only (names stay out of web addresses)
        self.assertEqual(c.get("/staff/patients/suggest?q=dela").status_code, 405)

    def test_needs_login(self):
        r = self.app.test_client().post("/staff/patients/suggest", data={"q": "delapena"})
        self.assertNotEqual(r.status_code, 200)

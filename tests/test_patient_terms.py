import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_app import Base  # noqa: E402


class TestPatientTerms(Base):
    REQ = "/staff/requests"
    def test_common_term_shown_and_saved(self):
        c = self.app.test_client()
        b = self.branch("guiguinto")
        svc = self.q("SELECT id FROM services WHERE slug='general-dentistry'")["id"]
        self.conn.execute("UPDATE services SET patient_terms = ? WHERE id = ?", ("Pasta (tooth filling)\nBunot (tooth extraction)", svc))
        page = c.get("/book").data.decode()
        self.assertIn('data-term="Pasta (tooth filling)"', page)
        self.assertIn("Other / not sure", page)
        day = self.next_weekday(1)
        slots = c.get(f"/book/slots?branch_id={b}&service_id={svc}&date={day.isoformat()}").get_json()["slots"]
        c.post("/book", data={"branch_id": b, "service_id": svc, "service_detail": "Pasta (tooth filling)", "date": day.isoformat(),
                              "time": slots[0], "full_name": "Term Person", "phone": "0900 999 0002", "consent_privacy": "1", "started": "0"})
        req = self.q("SELECT * FROM booking_requests WHERE full_name = 'Term Person'")
        self.assertEqual(req["service_detail"], "Pasta (tooth filling)")
        a = self.login("admin")
        self.assertIn("Pasta (tooth filling)", a.get(f"{self.REQ}/{req['id']}").data.decode())
        self.assertIn("Patient chose: Pasta (tooth filling)", a.get(f"{self.REQ}/{req['id']}").data.decode())
        # a term that isn't listed under the service is dropped
        c.post("/book", data={"branch_id": b, "service_id": svc, "service_detail": "Something else", "date": day.isoformat(),
                              "time": slots[-1], "full_name": "Term Person Two", "phone": "0900 999 0003", "consent_privacy": "1", "started": "0"})
        self.assertEqual(self.q("SELECT service_detail FROM booking_requests WHERE full_name = 'Term Person Two'")["service_detail"], "")


if __name__ == "__main__":
    unittest.main()

from test_app import DOMAIN, Base


class TestCalendarLabels(Base):
    def test_first_name_initial_and_specific_procedure(self):
        c = self.login("reception.malolos")
        malolos = self.branch("malolos")
        dentist = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        day = self.next_weekday(0, weeks=5)
        p = self.q("SELECT * FROM patients WHERE preferred_branch_id = ? LIMIT 1", (malolos,))
        svc = self.q("SELECT * FROM services WHERE slug = 'general-dentistry'")
        self.conn.execute("UPDATE services SET patient_terms = ? WHERE id = ?", ("Braces adjustment\nCheck-up", svc["id"]))
        r = c.post("/staff/appointments/new", data={"patient_id": p["id"], "branch_id": malolos, "service_id": svc["id"], "dentist_id": dentist,
                                                    "date": day.isoformat(), "time": "10:00", "status": "confirmed", "source": "phone",
                                                    "service_detail": "Braces adjustment"})
        self.assertEqual(r.status_code, 302)
        a = self.q("SELECT * FROM appointments WHERE dentist_id = ? AND start_at = ?", (dentist, f"{day.isoformat()} 10:00"))
        self.assertEqual(a["service_detail"], "Braces adjustment")
        page = c.get(f"/staff/calendar?date={day.isoformat()}&view=day").data.decode()
        self.assertIn(f"{p['first_name']} {p['last_name'][:1]}.", page)
        self.assertIn("Braces adjustment", page)
        # a term from another service is not kept
        c.post("/staff/appointments/new", data={"patient_id": p["id"], "branch_id": malolos, "service_id": svc["id"], "dentist_id": dentist,
                                                "date": day.isoformat(), "time": "11:30", "status": "confirmed", "source": "phone",
                                                "service_detail": "Teeth whitening"})
        b = self.q("SELECT service_detail FROM appointments WHERE dentist_id = ? AND start_at = ?", (dentist, f"{day.isoformat()} 11:30"))
        self.assertEqual(b["service_detail"], "")

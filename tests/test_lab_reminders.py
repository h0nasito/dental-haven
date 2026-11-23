from datetime import timedelta

from test_app import Base


class TestLabReminders(Base):
    def _case(self, **kw):
        from app.util import now_str
        mal = self.branch("malolos")
        lab = self.q("SELECT id FROM laboratories ORDER BY id LIMIT 1")["id"]
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        row = {"lab_id": lab, "branch_id": mal, "patient_id": pid, "case_type": "Reminder demo crown", "status": "fabricating",
               "sent_on": "2026-01-02", "created_at": now_str()}
        row.update(kw)
        return self.conn.insert("lab_cases", row)

    def test_reminders_two_days_before(self):
        from app.util import today
        t = today()
        d = lambda n: (t + timedelta(days=n)).isoformat()
        self.conn.execute("UPDATE lab_cases SET status = 'cancelled'")          # only this test's cases
        late = self._case(due_on=d(-3), case_type="RemOverdue")
        self._case(due_on=d(0), case_type="RemToday")
        self._case(due_on=d(2), case_type="RemSoon")
        self._case(due_on=d(3), case_type="RemLater")                           # 3 days away: not yet
        self._case(due_on=d(1), status="ready", case_type="RemReadyDone")       # finished: no reminder
        self._case(due_on=d(5), install_on=d(1), case_type="RemInstallNotReady")
        self._case(status="ready", try_in_on=d(2), case_type="RemFitReady")
        a = self.login("admin")
        page = a.get("/staff/lab/").data.decode()
        rem = page.split('aria-label="Reminders"')[1].split("</section>")[0]
        for word in ("RemOverdue", "RemToday", "RemSoon", "RemInstallNotReady", "RemFitReady", "3 days late", "Not ready yet", "tomorrow"):
            self.assertIn(word, rem)
        self.assertNotIn("RemLater", rem)
        self.assertNotIn("RemReadyDone", rem)
        self.assertIn(f"/staff/lab/{late}", rem)

    def test_branch_staff_see_their_branch_reminders(self):
        from app.util import today
        d = lambda n: (today() + timedelta(days=n)).isoformat()
        self.conn.execute("UPDATE lab_cases SET status = 'cancelled'")
        other_dentist = self.q("SELECT id FROM users WHERE email LIKE 'admin%'")["id"]
        self._case(due_on=d(1), case_type="RemMalolosCase", dentist_id=other_dentist)
        self._case(due_on=d(1), case_type="RemBocaueCase", branch_id=self.branch("bocaue"))
        for who in ("reception.malolos", "dentist.malolos"):
            c = self.login(who)
            for url in ("/staff/lab/", "/staff/"):
                page = c.get(url).data.decode()
                self.assertIn('aria-label="Reminders"', page, (who, url))
                rem = page.split('aria-label="Reminders"')[1].split("</section>")[0]
                self.assertIn("RemMalolosCase", rem, (who, url))
                self.assertNotIn("RemBocaueCase", rem, (who, url))
        c = self.login("reception.bocaue")
        rem = c.get("/staff/").data.decode().split('aria-label="Reminders"')[1].split("</section>")[0]
        self.assertIn("RemBocaueCase", rem)
        self.assertNotIn("RemMalolosCase", rem)

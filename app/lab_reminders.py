"""Lab reminders for the Laboratory page: what has to be finished, starting 2 days (REMIND_DAYS) before the target date.

- Overdue: still being made (or not accepted yet) and the due date has passed.
- Due today, and due in the next 2 days.
- Patient coming in the next 2 days (trial fitting or installation date) while the case isn't ready yet, plus those that are ready.
Outside-clinic works (lab_works) are included for people who work at the lab and can see them.
"""
from __future__ import annotations

from datetime import timedelta

from .lab_status import LATE, REMIND_DAYS, sql_list
from .util import today


def build(conn, frag: str, params: list, work_lab_ids: list[int] | None = None) -> dict:
    t = today()
    day, until = t.isoformat(), (t + timedelta(days=REMIND_DAYS)).isoformat()
    sel = ("SELECT c.id, c.case_type, c.units, c.teeth, c.status, c.due_on, c.try_in_on, c.install_on, c.no_try_in, c.installed_on, "
           "p.last_name, p.first_name, b.name AS branch, u.name AS dentist, l.name AS lab FROM lab_cases c "
           "JOIN patients p ON p.id = c.patient_id JOIN branches b ON b.id = c.branch_id JOIN laboratories l ON l.id = c.lab_id "
           "LEFT JOIN users u ON u.id = c.dentist_id ")
    due = [dict(r, kind="case") for r in conn.all(
        sel + f"WHERE {frag} AND c.status IN {sql_list(LATE)} AND c.due_on IS NOT NULL AND c.due_on <= ? ORDER BY c.due_on, c.id",
        [*params, until])]
    if work_lab_ids:
        m = ",".join("?" for _ in work_lab_ids)
        due += [dict(r, kind="work") for r in conn.all(
            "SELECT w.id, w.number, w.case_type, w.units, w.status, w.due_on, w.clinic_name, w.doctor, l.name AS lab FROM lab_works w "
            f"JOIN laboratories l ON l.id = w.lab_id WHERE w.lab_id IN ({m}) AND w.status IN {sql_list(LATE)} "
            "AND w.due_on IS NOT NULL AND w.due_on <= ? ORDER BY w.due_on, w.id", [*work_lab_ids, until])]
    due.sort(key=lambda r: (r["due_on"], r["kind"], r["id"]))
    for r in due:
        r["days"] = (_d(r["due_on"]) - t).days
    # the patient's trial fitting or installation is coming: the case has to be at the clinic by then
    visits = []
    for r in conn.all(sel + f"WHERE {frag} AND c.installed_on IS NULL AND c.status NOT IN ('delivered', 'cancelled') AND "
                      "((c.try_in_on BETWEEN ? AND ? AND COALESCE(c.no_try_in, 0) = 0 AND c.status != 'try_in') OR c.install_on BETWEEN ? AND ?) "
                      "ORDER BY COALESCE(c.try_in_on, c.install_on), c.id", [*params, day, until, day, until]):
        r = dict(r, kind="case")
        fit = r["try_in_on"] if (r["try_in_on"] and day <= r["try_in_on"] <= until and not r["no_try_in"] and r["status"] != "try_in") else None
        r["visit"], r["visit_on"] = ("Trial fitting", fit) if fit else ("Installation", r["install_on"])
        r["days"] = (_d(r["visit_on"]) - t).days
        r["not_ready"] = r["status"] in LATE
        visits.append(r)
    visits.sort(key=lambda r: (not r["not_ready"], r["visit_on"], r["id"]))
    return {"days": REMIND_DAYS, "today": day,
            "overdue": [r for r in due if r["days"] < 0],
            "due_today": [r for r in due if r["days"] == 0],
            "due_soon": [r for r in due if r["days"] > 0],
            "visits": visits}


def _d(s):
    from datetime import date
    return date.fromisoformat(s[:10])

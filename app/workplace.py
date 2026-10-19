"""Where an employee works: a clinic branch, or the laboratory (DSDL). The lab is its own group for payroll and HR.

Form values: "<branch id>" for a branch, "lab:<lab id>" for a laboratory.
"""
from __future__ import annotations


def labs_for(conn, user) -> list:
    """Laboratories this user can manage people of: super admins, people who cover every branch (e.g. HR), and people
    assigned to the lab."""
    labs = conn.all("SELECT * FROM laboratories WHERE active = 1 ORDER BY name")
    if user.is_super_admin or covers_all_branches(conn, user):
        return labs
    mine = {r["lab_id"] for r in conn.all("SELECT lab_id FROM user_labs WHERE user_id = ?", (user.id,))}
    return [l for l in labs if l["id"] in mine]


def covers_all_branches(conn, user) -> bool:
    active = {r["id"] for r in conn.all("SELECT id FROM branches WHERE active = 1")}
    return bool(active) and active.issubset(set(user.branch_ids))


def parse(conn, user, raw) -> tuple[int | None, int | None, str | None]:
    """(branch_id, lab_id, error) from a form value."""
    raw = (raw or "").strip()
    if raw.startswith("lab:"):
        try:
            lid = int(raw[4:])
        except ValueError:
            return None, None, "Choose a branch or the laboratory."
        if lid not in {l["id"] for l in labs_for(conn, user)}:
            return None, None, "You can't add people to that laboratory."
        return None, lid, None
    try:
        bid = int(raw)
    except ValueError:
        return None, None, "Choose a branch or the laboratory."
    if not user.in_branch(bid):
        return None, None, "Choose one of your branches."
    return bid, None, None


def label(lab_name: str | None) -> str:
    return f"{lab_name} (laboratory)" if lab_name else ""

"""Combining two records of the same patient (e.g. one from the MyMedsPH import and one registered at a branch).

Everything that points to the duplicate (bills, payments, progress notes, appointments, X-rays, lab cases, uploads, consents…)
moves to the record that is kept. Empty profile fields of the kept record are filled from the duplicate. The duplicate is not
erased: it is archived (deleted from the lists, reason "Merged into …"), so the history stays traceable.
"""
from __future__ import annotations

_REFS: list[tuple[str, str]] | None = None

# Profile fields copied from the duplicate when the kept record has them empty.
FILL = ("middle_name", "birth_date", "sex", "phone", "email", "address", "occupation", "civil_status", "emergency_contact",
        "emergency_phone", "alert_flag", "legacy_id", "photo", "preferred_branch_id", "preferred_channel")


def refs(conn) -> list[tuple[str, str]]:
    """Every (table, column) that refers to patients.id."""
    global _REFS
    if _REFS is None:
        out = []
        for t in conn.all("SELECT name FROM sqlite_master WHERE type = 'table'"):
            for fk in conn.all(f"PRAGMA foreign_key_list('{t['name']}')"):
                if fk["table"] == "patients":
                    out.append((t["name"], fk["from"]))
        _REFS = sorted(set(out))
    return _REFS


def counts(conn, pid: int) -> dict[str, int]:
    """How many records of each kind the patient has (only kinds that have some)."""
    out = {}
    for t, c in refs(conn):
        n = conn.scalar(f"SELECT COUNT(*) FROM {t} WHERE {c} = ?", (pid,)) or 0
        if n:
            out[t] = n
    return out


def merge(conn, src: int, dst: int, user_id: int, now: str) -> None:
    """Move everything from patient src to dst, fill dst's empty fields from src, then archive src."""
    s = conn.one("SELECT * FROM patients WHERE id = ?", (src,))
    d = conn.one("SELECT * FROM patients WHERE id = ?", (dst,))
    for t, c in refs(conn):
        # a row that can exist only once per patient (e.g. a dentist assignment) stays with the archived duplicate
        conn.execute(f"UPDATE OR IGNORE {t} SET {c} = ? WHERE {c} = ?", (dst, src))
    upd = {k: s[k] for k in FILL if (d[k] in (None, "")) and s[k] not in (None, "")}
    if s["consent_privacy"] and not d["consent_privacy"]:
        upd.update(consent_privacy=s["consent_privacy"], consent_privacy_at=s["consent_privacy_at"])
    if s["shared"] and not d["shared"]:
        upd["shared"] = 1
    note = f"Merged with chart no. {s['chart_no']}" + (f" (MyMedsPH #{s['legacy_id']})" if s["legacy_id"] and s["legacy_id"] != d["legacy_id"] else "")
    upd["admin_notes"] = ((d["admin_notes"] or "").rstrip() + "\n" + note).strip()
    upd["updated_at"] = now
    if "legacy_id" in upd:      # one MyMedsPH number per patient: it moves from the archived duplicate
        conn.execute("UPDATE patients SET legacy_id = NULL WHERE id = ?", (src,))
    sets = ", ".join(f"{k} = ?" for k in upd)
    conn.execute(f"UPDATE patients SET {sets} WHERE id = ?", (*upd.values(), dst))
    conn.execute("UPDATE patients SET active = 0, deleted_at = ?, deleted_by = ?, deleted_reason = ?, updated_at = ? WHERE id = ?",
                 (now, user_id, f"Merged into {d['chart_no']}", now, src))

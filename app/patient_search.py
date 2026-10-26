"""Finding patients by name the way people type them.

- Each word can be anywhere and in any order: "juan cruz", "cruz juan" and "dela cruz j" all find Juan Dela Cruz.
- The chart number matches when typed as one piece (e.g. "DH-000123" or "000123").
- Spaces don't matter: "delacruz" finds "Dela Cruz" and "dela cruz" finds "Delacruz".
- Capitals, ñ/n, commas and dots don't matter: "pena" finds "Peña", "Cruz, Juan" works too.
Only SQL that runs on both SQLite and PostgreSQL is used.
"""
from __future__ import annotations

import re

# The searchable text of a patient: first, middle and last name, lower case, ñ as n. (The chart number is matched as typed, whole.)
_HAY = ("replace(replace(lower(COALESCE({a}.first_name, '') || ' ' || COALESCE({a}.middle_name, '') || ' ' || COALESCE({a}.last_name, '')), "
        "'ñ', 'n'), 'Ñ', 'n')")


def words(q: str) -> list[str]:
    q = (q or "").lower().replace("ñ", "n").replace("Ñ", "n")
    q = re.sub(r"[,.;:()]+", " ", q)
    return [w for w in q.split() if w][:6]


def _esc(w: str) -> str:
    return w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def name_match(q: str, alias: str = "p") -> tuple[str, list]:
    """SQL condition (and its parameters) for "this patient matches what was typed". Empty query -> always true."""
    ws = words(q)
    if not ws:
        return "1 = 1", []
    hay = _HAY.format(a=alias)
    every = " AND ".join(f"{hay} LIKE ? ESCAPE '\\'" for _ in ws)
    joined = "".join(ws)
    sql = f"(({every}) OR replace({hay}, ' ', '') LIKE ? ESCAPE '\\' OR lower({alias}.chart_no) LIKE ? ESCAPE '\\')"
    return sql, [f"%{_esc(w)}%" for w in ws] + [f"%{_esc(joined)}%", f"%{_esc(q.strip().lower())}%"]


def best_first(q: str, alias: str = "p") -> tuple[str, list]:
    """ORDER BY: last names, then first names, starting with the first word typed come first."""
    ws = words(q)
    if not ws:
        return f"{alias}.last_name, {alias}.first_name", []
    w = f"{_esc(ws[0])}%"
    return (f"CASE WHEN lower({alias}.last_name) LIKE ? ESCAPE '\\' THEN 0 WHEN lower({alias}.first_name) LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END, "
            f"{alias}.last_name, {alias}.first_name"), [w, w]


def close_matches(conn, q: str, limit: int = 10) -> list:
    """When nothing matches exactly: patients whose name is spelled similarly (e.g. "Jazper Estrada" finds "Jasper
    Estrada"). Candidates share the first 3 letters of a word with the first or last name; the closest come first."""
    from difflib import SequenceMatcher
    ws = [w for w in words(q) if len(w) >= 3]
    if not ws:
        return []
    conds, params = [], []
    for w in ws:
        conds.append("lower(p.last_name) LIKE ? OR lower(p.first_name) LIKE ?")
        params += [f"{_esc(w[:3])}%"] * 2
    rows = conn.all(f"SELECT p.id, p.chart_no, p.first_name, p.middle_name, p.last_name FROM patients p WHERE p.active = 1 AND p.deleted_at IS NULL "
                    f"AND ({' OR '.join(conds)}) LIMIT 2000", params)
    target = " ".join(sorted(ws))

    def score(r):
        full = words(f"{r['first_name']} {r['middle_name'] or ''} {r['last_name']}")
        a = SequenceMatcher(None, target, " ".join(sorted(full))).ratio()
        b = SequenceMatcher(None, target, " ".join(sorted(words(f"{r['first_name']} {r['last_name']}")))).ratio()
        return max(a, b)
    scored = sorted(((score(r), r) for r in rows), key=lambda x: -x[0])
    return [r for s, r in scored if s >= 0.6][:limit]

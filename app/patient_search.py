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

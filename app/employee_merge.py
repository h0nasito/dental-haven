"""Removing duplicate employee records: delete ones that have no records yet, or merge a duplicate into the right one.

Merging moves everything that points to the duplicate (time records, pay rates, payroll lines, commissions, leave…) to the
employee that is kept, gives it the duplicate's login if it has none, then deletes the duplicate.
"""
from __future__ import annotations

_REFS: list[tuple[str, str]] | None = None

# Tables where one employee can have only one row per day / period / service: both records can't be merged blindly.
UNIQUE_KEYS = {
    "time_records": ("work_date", "a time record on"),
    "payroll_lines": ("period_id", "a line in payroll period #"),
    "dentist_service_rates": ("service_id", "a commission rate for service #"),
    "late_warnings": ("month", "a late warning for"),
    "duty_assignments": ("work_date", "a duty assignment on"),
}


def refs(conn) -> list[tuple[str, str]]:
    """Every (table, column) that refers to employees.id."""
    global _REFS
    if _REFS is None:
        out = []
        if getattr(conn.database, "is_postgres", False):  # pragma: no cover - production may run PostgreSQL
            out = [(r["table_name"], r["column_name"]) for r in conn.all(
                "SELECT kcu.table_name, kcu.column_name FROM information_schema.referential_constraints rc "
                "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = rc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = rc.unique_constraint_name "
                "WHERE ccu.table_name = 'employees'")]
        else:
            for t in conn.all("SELECT name FROM sqlite_master WHERE type = 'table'"):
                for fk in conn.all(f"PRAGMA foreign_key_list('{t['name']}')"):
                    if fk["table"] == "employees":
                        out.append((t["name"], fk["from"]))
        _REFS = sorted(set(out))
    return _REFS


def record_count(conn, emp_id: int) -> int:
    return sum(conn.scalar(f"SELECT COUNT(*) FROM {t} WHERE {c} = ?", (emp_id,)) or 0 for t, c in refs(conn))


def conflicts(conn, src: int, dst: int) -> list[str]:
    """Rows both employees have that can exist only once (e.g. a time record on the same day)."""
    out = []
    for table, (key, label) in UNIQUE_KEYS.items():
        if (table, "employee_id") not in refs(conn):
            continue
        both = conn.all(f"SELECT a.{key} AS k FROM {table} a JOIN {table} b ON b.{key} = a.{key} "
                        f"WHERE a.employee_id = ? AND b.employee_id = ?" + (" AND a.branch_id = b.branch_id" if table == "duty_assignments" else ""),
                        (src, dst))
        out += [f"{label} {r['k']}" for r in both[:5]]
    return out


def merge(conn, src: int, dst: int) -> None:
    """Move everything from employee src to dst, then delete src. Check conflicts() first."""
    s = conn.one("SELECT * FROM employees WHERE id = ?", (src,))
    d = conn.one("SELECT * FROM employees WHERE id = ?", (dst,))
    for t, c in refs(conn):
        conn.execute(f"UPDATE {t} SET {c} = ? WHERE {c} = ?", (dst, src))
    if s["user_id"] and not d["user_id"]:
        conn.execute("UPDATE employees SET user_id = NULL WHERE id = ?", (src,))
        conn.execute("UPDATE employees SET user_id = ? WHERE id = ?", (s["user_id"], dst))
    conn.execute("DELETE FROM employees WHERE id = ?", (src,))

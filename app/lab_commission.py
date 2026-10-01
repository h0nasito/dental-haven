"""Technician commissions: added by hand on an outside-clinic lab work or a branch lab case, counted in the payroll
cutoff when that work leaves the laboratory (status Delivered: lab_works.delivered_on / lab_cases.completed_on)."""
from __future__ import annotations


def technicians(conn):
    return conn.all("SELECT e.id, e.full_name FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.active = 1 "
                    "AND (lower(e.position) LIKE '%technician%' OR u.access_role = 'technician') ORDER BY e.full_name")


def entries(conn, work_id=None, case_id=None):
    col, val = ("work_id", work_id) if work_id else ("case_id", case_id)
    return conn.all(f"SELECT c.*, e.full_name, u.name AS by_name FROM lab_commissions c JOIN employees e ON e.id = c.employee_id "
                    f"LEFT JOIN users u ON u.id = c.created_by WHERE c.{col} = ? ORDER BY c.id", (val,))


def for_period(conn, employee_id: int, start: str, end: str):
    """Commission entries whose work left the lab (delivered) within the period."""
    return conn.all(
        "SELECT c.*, 'work' AS src, w.number AS ref, w.case_type, w.clinic_name AS source_name, w.delivered_on AS out_on "
        "FROM lab_commissions c JOIN lab_works w ON w.id = c.work_id "
        "WHERE c.employee_id = ? AND w.status = 'delivered' AND w.delivered_on BETWEEN ? AND ? "
        "UNION ALL "
        "SELECT c.*, 'case' AS src, '#' || lc.id AS ref, lc.case_type, b.name AS source_name, lc.completed_on AS out_on "
        "FROM lab_commissions c JOIN lab_cases lc ON lc.id = c.case_id JOIN branches b ON b.id = lc.branch_id "
        "WHERE c.employee_id = ? AND lc.status = 'delivered' AND lc.completed_on BETWEEN ? AND ? ORDER BY out_on",
        (employee_id, start, end, employee_id, start, end))

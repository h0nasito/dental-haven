"""Roles, permission catalog and access-scope helpers.

Exactly four roles exist. super_admin implicitly holds every permission. The other
roles hold whatever is stored in role_permissions (seeded from ROLE_DEFAULTS and
editable only by a super admin). Permissions in LOCKED can never be granted to a
non-super-admin role, so only super admins can manage users, roles and access.
"""
from __future__ import annotations

from dataclasses import dataclass

ROLES = {
    "super_admin": "Super admin",
    "dentist": "Dentist",
    "staff": "Staff",
    "receptionist": "Receptionist",
}


@dataclass(frozen=True)
class Perm:
    key: str
    label: str
    group: str
    sensitive: bool = False


CATALOG: list[Perm] = [
    # Groups and wording follow MyMedsPH so staff recognise them.
    Perm("dashboard.view", "View dashboard", "Dashboard privileges"),
    Perm("dashboard.balances", "View patients with balance", "Dashboard privileges", True),
    # Calendar
    Perm("appointments.view", "View Calendar & Appointments", "Calendar"),
    Perm("calendar.associates", "View Associates (other dentists' appointments)", "Calendar"),
    Perm("calendar.birthdays", "View Birthdays", "Calendar"),
    Perm("followups.view", "View Follow-ups", "Calendar"),
    Perm("calendar.events", "View Events/Schedules (dentist schedules)", "Calendar"),
    Perm("bookings.view", "View Online Bookings", "Calendar"),
    # Appointments (booking workflow)
    Perm("appointments.manage", "Book, confirm, reschedule and cancel appointments", "Appointments"),
    Perm("appointments.complete", "Check in, complete and mark no-show", "Appointments"),
    Perm("bookings.manage", "Confirm or decline online bookings", "Appointments"),
    Perm("followups.manage", "Create and complete follow-ups", "Appointments"),
    # Patients
    Perm("patients.view", "View patient list and profiles", "Patients"),
    Perm("patients.contact", "View patient contact number, email address and home address", "Patients", True),
    Perm("patients.manage", "Edit patient data", "Patients"),
    Perm("patients.delete", "Can delete patients", "Patient privileges", True),
    # Progress notes / clinical record
    Perm("clinical.view", "View only progress notes (read-only clinical record)", "Progress notes", True),
    Perm("progress.add", "Add new progress note", "Progress notes", True),
    Perm("progress.actions", "View progress notes list actions (edit/delete entries)", "Progress notes", True),
    Perm("clinical.edit", "Edit medical & dental history and alert flag", "Progress notes", True),
    # Treatment plans
    Perm("plans.delete", "Delete treatment plan", "Patient treatment plans", True),
    Perm("plans.edit", "Edit existing treatment plan", "Patient treatment plans", True),
    Perm("plans.add", "Add new treatment plan", "Patient treatment plans", True),
    Perm("plans.generate", "Generate Progress Note (from a plan item)", "Patient treatment plans", True),
    # Charting
    Perm("chart.edit", "Update patient chart", "Patient charting", True),
    Perm("chart.delete", "Delete patient chart", "Patient charting", True),
    # Bills / payments
    Perm("billing.view", "View bills and payments", "Patient bills/payments"),
    Perm("billing.manage", "Add bill", "Patient bills/payments"),
    Perm("bills.edit", "Edit Patient bill", "Patient bills/payments"),
    Perm("payments.add", "Add Payment (and patient deposits)", "Patient bills/payments"),
    Perm("credit.apply", "Apply Account Credit", "Patient bills/payments"),
    Perm("billing.void", "Delete patient bill (void) and refunds", "Patient bills/payments", True),
    # Quotations
    Perm("quotes.view", "View price quotations", "Price quotations"),
    Perm("quotes.manage", "Create and edit price quotations", "Price quotations"),
    # Prescriptions
    Perm("rx.delete", "Delete patient prescription", "Patient prescriptions", True),
    Perm("rx.create", "Create patient prescription", "Patient prescriptions", True),
    Perm("rx.edit", "Edit patient prescription", "Patient prescriptions", True),
    # Attachments
    Perm("documents.upload", "Upload attachments / lab results", "Upload attachments / lab results", True),
    Perm("documents.delete", "Delete patient attachment", "Upload attachments / lab results", True),
    # Certificates
    Perm("cert.delete", "Delete patient certificate", "Patient certificates", True),
    Perm("cert.create", "Create patient certificate", "Patient certificates", True),
    Perm("cert.edit", "Edit patient certificate", "Patient certificates", True),
    # Laboratory
    Perm("lab.view", "View lab cases", "Laboratory"),
    Perm("lab.manage", "Create and update lab cases", "Laboratory"),
    # Expenses
    Perm("expenses.view", "View Expenses", "Expenses", True),
    Perm("expenses.post", "Post Expenses", "Expenses", True),
    Perm("expenses.add", "Add Expenses", "Expenses"),
    # Report cards
    Perm("reportcards.generate", "Generate patient report cards", "Report cards", True),
    Perm("reportcards.review", "Review and approve patient report cards", "Report cards", True),
    # Front desk
    Perm("leads.view", "View lead inbox", "Leads & reminders"),
    Perm("leads.manage", "Create, assign and convert leads", "Leads & reminders"),
    Perm("reminders.view", "View reminder outbox", "Leads & reminders"),
    Perm("reminders.send", "Generate reminders and record manual sends", "Leads & reminders"),
    Perm("templates.manage", "Edit message and response templates", "Leads & reminders"),
    # Reports
    Perm("reports.sales", "View sales, collections and balances reports", "Reports"),
    Perm("reports.operations", "View appointment, lead and visit reports", "Reports"),
    Perm("reports.export", "Export authorised reports to CSV", "Reports"),
    # People
    Perm("attendance.view", "View attendance (DTR)", "Staff & payroll"),
    Perm("attendance.manage", "Record, import and correct attendance", "Staff & payroll", True),
    Perm("compensation.manage", "View and edit compensation settings", "Staff & payroll", True),
    Perm("payroll.prepare", "Prepare draft payroll summaries", "Staff & payroll", True),
    Perm("payroll.approve", "Approve payroll summaries", "Staff & payroll", True),
    # Configuration
    Perm("content.manage", "Edit public website content", "Configuration"),
    Perm("settings.manage", "Edit branches, services, hours, rooms and schedules", "Configuration"),
    # Super admin only (never grantable)
    Perm("users.manage", "Create users and assign roles/branches/labs", "Super admin only", True),
    Perm("roles.manage", "Grant or change role access", "Super admin only", True),
    Perm("audit.view", "View audit trail", "Super admin only", True),
    Perm("system.settings", "Change system settings and import data", "Super admin only", True),
]

PERM_KEYS = {p.key for p in CATALOG}
LOCKED = {"users.manage", "roles.manage", "audit.view", "system.settings"}

_CLINICAL_WRITE = {"progress.add", "progress.actions", "plans.add", "plans.edit", "plans.generate", "chart.edit",
                   "rx.create", "rx.edit", "cert.create", "cert.edit"}
ROLE_DEFAULTS: dict[str, set[str]] = {
    "dentist": {
        "dashboard.view", "appointments.view", "appointments.complete", "calendar.birthdays", "calendar.events",
        "followups.view", "followups.manage", "patients.view", "clinical.view", "clinical.edit", *_CLINICAL_WRITE,
        "documents.upload", "lab.view", "lab.manage", "reportcards.generate", "reportcards.review",
        "quotes.view", "quotes.manage",
    },
    "staff": {
        "dashboard.view", "dashboard.balances", "appointments.view", "calendar.associates", "calendar.birthdays",
        "calendar.events", "bookings.view", "appointments.manage", "appointments.complete", "bookings.manage",
        "patients.view", "patients.contact", "patients.manage", "documents.upload",
        "leads.view", "followups.view", "followups.manage", "reminders.view", "reminders.send",
        "billing.view", "billing.manage", "bills.edit", "payments.add", "credit.apply",
        "expenses.view", "expenses.add", "lab.view", "reports.operations", "attendance.view",
        "quotes.view", "quotes.manage",
    },
    "receptionist": {
        "dashboard.view", "appointments.view", "calendar.associates", "calendar.birthdays", "calendar.events",
        "bookings.view", "appointments.manage", "appointments.complete", "bookings.manage",
        "patients.view", "patients.contact", "patients.manage", "documents.upload",
        "leads.view", "leads.manage", "followups.view", "followups.manage", "reminders.view", "reminders.send",
        "quotes.view", "quotes.manage",
    },
}

assert all(p in PERM_KEYS for perms in ROLE_DEFAULTS.values() for p in perms)
assert not any(LOCKED & perms for perms in ROLE_DEFAULTS.values())


def grantable(role: str, perm: str) -> bool:
    return role in ROLES and role != "super_admin" and perm in PERM_KEYS and perm not in LOCKED


def load_role_permissions(conn, role: str) -> set[str]:
    if role == "super_admin":
        return set(PERM_KEYS)
    rows = conn.all("SELECT permission FROM role_permissions WHERE role = ?", (role,))
    return {r["permission"] for r in rows if r["permission"] in PERM_KEYS and r["permission"] not in LOCKED}


# ---------------------------------------------------------------------------
# Scope helpers. Each returns (sql_fragment, params) to AND into a WHERE clause.
# ---------------------------------------------------------------------------

def branch_filter(user, column: str, branch_ids: list[int] | None = None):
    """Restrict a branch_id column to the user's current branch selection."""
    ids = branch_ids if branch_ids is not None else user.scope_branch_ids
    if not ids:
        return "1 = 0", []
    marks = ",".join("?" for _ in ids)
    return f"{column} IN ({marks})", list(ids)


def patient_scope(user, alias: str = "p"):
    """Which patients a user may see at all.

    - super_admin: every patient
    - dentist: patients assigned to them (assignment is created when an appointment
      with that dentist is booked, or granted explicitly by a super admin)
    - staff/receptionist: patients whose preferred branch, or any appointment/invoice,
      is in the user's branches
    """
    if user.role == "super_admin" and not user.branch_selected:
        return "1 = 1", []
    if user.role == "dentist":
        return (
            f"{alias}.id IN (SELECT patient_id FROM patient_assignments WHERE dentist_id = ?)",
            [user.id],
        )
    ids = user.scope_branch_ids
    if not ids:
        return "1 = 0", []
    marks = ",".join("?" for _ in ids)
    frag = (
        f"({alias}.preferred_branch_id IN ({marks})"
        f" OR {alias}.id IN (SELECT patient_id FROM appointments WHERE branch_id IN ({marks}))"
        f" OR {alias}.id IN (SELECT patient_id FROM invoices WHERE branch_id IN ({marks})))"
    )
    return frag, list(ids) * 3


def can_see_patient(conn, user, patient_id: int) -> bool:
    frag, params = patient_scope(user, "p")
    # Branch switcher narrows lists, but direct access uses all of the user's branches.
    if user.role not in ("super_admin", "dentist"):
        ids = user.branch_ids
        if not ids:
            return False
        marks = ",".join("?" for _ in ids)
        frag = (
            f"(p.preferred_branch_id IN ({marks})"
            f" OR p.id IN (SELECT patient_id FROM appointments WHERE branch_id IN ({marks}))"
            f" OR p.id IN (SELECT patient_id FROM invoices WHERE branch_id IN ({marks})))"
        )
        params = list(ids) * 3
    elif user.role == "super_admin":
        frag, params = "1 = 1", []
    row = conn.one(f"SELECT p.id FROM patients p WHERE p.id = ? AND {frag}", [patient_id, *params])
    return row is not None


def can_see_clinical(conn, user, patient_id: int) -> bool:
    return user.can("clinical.view") and can_see_patient(conn, user, patient_id)

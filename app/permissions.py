"""Roles, permission catalog and access-scope helpers.

Access roles: Super admin, Dentist, and Staff (Receptionist, Cashier, Technician, HR, Supervisor, or plain Staff).
super_admin implicitly holds every permission. The other access roles hold whatever is stored in
role_permissions (seeded from ROLE_DEFAULTS and editable only by a super admin). Permissions in LOCKED can never be granted to a
non-super-admin role, so only super admins can manage users, roles and access.
"""
from __future__ import annotations

from dataclasses import dataclass

ROLES = {  # access roles, in the order shown when creating an account
    "super_admin": "Super admin",
    "dentist": "Dentist",
    "receptionist": "Staff – Receptionist",
    "hr": "Staff – HR",
    "supervisor": "Staff – Supervisor",
    "cashier": "Staff – Cashier",
    "technician": "Staff – Technician",
    "staff": "Staff",
}
# Employee positions (job titles). Only a super admin assigns access roles; HR can set positions.
POSITIONS = ["Head Dentist", "Associate Dentist", "Dentist", "Head Staff", "Dental Staff Consultant", "Head Receptionist", "Receptionist",
             "Lab Receptionist", "Dental Assistant", "Finance Officer", "Digital Content Associate", "Dental Technician (RPD)", "Dental Technician (FPD)", "Cashier", "Technician", "HR",
             "Supervisor", "Staff"]
POSITION_FOR_ROLE = {"receptionist": "Receptionist", "cashier": "Cashier", "technician": "Technician", "staff": "Staff",
                     "dentist": "Dentist", "hr": "HR", "supervisor": "Supervisor"}
# Suggested access role when a login is created for an employee, by position (the super admin can change it).
ACCESS_FOR_POSITION = {
    "Head Dentist": "dentist", "Associate Dentist": "dentist", "Dentist": "dentist",
    "Head Receptionist": "receptionist", "Receptionist": "receptionist", "Lab Receptionist": "staff",
    "Cashier": "cashier", "Finance Officer": "cashier", "HR": "hr", "Supervisor": "supervisor", "Head Staff": "supervisor",
    "Technician": "technician", "Dental Technician (RPD)": "technician", "Dental Technician (FPD)": "technician",
    "Dental Assistant": "staff", "Dental Staff Consultant": "staff", "Digital Content Associate": "staff", "Staff": "staff",
}
# users.role keeps the base role (what the rest of the system checks); users.access_role picks the permission set.
BASE_ROLE = {"hr": "staff", "supervisor": "staff", "cashier": "staff", "technician": "staff"}


def base_role(access_role: str) -> str:
    return BASE_ROLE.get(access_role, access_role)


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
    Perm("commission.record", "Record dentist commission on payments", "Patient bills/payments"),
    Perm("fees.manage", "Edit the fee schedule (billing prices)", "Patient bills/payments"),
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
    Perm("lab.all_branches", "View lab cases and lab workload of all branches (view only; updates stay with each branch)", "Laboratory"),
    Perm("lab.manage", "Create and update lab cases", "Laboratory"),
    Perm("lab.works", "Outside-clinic lab works: add, edit and update works from other clinics (for users assigned to the lab)", "Laboratory"),
    Perm("lab.billing", "Lab invoices, discounts and payment receipts for outside clinics", "Laboratory", True),
    Perm("lab.commission", "Add technician commissions on lab works and cases", "Laboratory", True),
    # Inventory
    Perm("evaluations.answer", "Answer staff evaluation forms (through the form link, while the form is open)", "Staff evaluations"),
    Perm("evaluations.manage", "Manage evaluation forms: open/close, edit questions, see all answers and results", "Staff evaluations"),
    Perm("inventory.view", "View inventory (stock, expiry, history)", "Inventory"),
    Perm("inventory.manage", "Update inventory: stock counts, receive and use items, edit items and prices", "Inventory"),
    Perm("inventory.order", "Make the monthly order list for their branch (before month end)", "Inventory"),
    Perm("inventory.order_approve", "Approve order lists, mark them ordered and received (adds to stock)", "Inventory", True),
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
    Perm("attendance.clock", "Time in / time out with a selfie and location check", "Staff & payroll"),
    Perm("overtime.approve", "Approve overtime (only approved overtime is paid)", "Staff & payroll", True),
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
        "documents.upload", "lab.view", "lab.all_branches", "lab.manage", "reportcards.generate", "reportcards.review",
        "quotes.view", "quotes.manage", "attendance.clock", "evaluations.answer",
    },
    "staff": {
        "dashboard.view", "dashboard.balances", "appointments.view", "calendar.associates", "calendar.birthdays",
        "calendar.events", "bookings.view", "appointments.manage", "appointments.complete", "bookings.manage",
        "patients.view", "patients.contact", "patients.manage", "documents.upload",
        "leads.view", "followups.view", "followups.manage", "reminders.view", "reminders.send",
        "billing.view", "billing.manage", "bills.edit", "payments.add", "credit.apply", "commission.record",
        "expenses.view", "expenses.add", "lab.view", "reports.operations", "attendance.view",
        "quotes.view", "quotes.manage", "inventory.view", "inventory.order", "attendance.clock",
    },
    "hr": {
        "dashboard.view", "attendance.view", "attendance.manage", "attendance.clock", "overtime.approve", "compensation.manage",
        "payroll.prepare", "reports.operations", "calendar.birthdays", "calendar.events",
    },
    "supervisor": {
        "dashboard.view", "dashboard.balances", "appointments.view", "calendar.associates", "calendar.birthdays", "calendar.events",
        "bookings.view", "appointments.manage", "appointments.complete", "bookings.manage", "patients.view", "patients.contact",
        "patients.manage", "documents.upload", "leads.view", "leads.manage", "followups.view", "followups.manage", "reminders.view",
        "reminders.send", "billing.view", "quotes.view", "lab.view", "lab.all_branches", "reports.operations", "attendance.view", "attendance.manage",
        "attendance.clock", "overtime.approve", "inventory.view", "inventory.order", "inventory.order_approve",
    },
    "technician": {
        "dashboard.view", "lab.view", "attendance.clock", "inventory.view",
    },
    "cashier": {
        "dashboard.view", "dashboard.balances", "appointments.view", "calendar.associates", "patients.view", "patients.contact",
        "billing.view", "billing.manage", "bills.edit", "payments.add", "credit.apply", "commission.record", "quotes.view", "reports.sales",
        "expenses.view", "expenses.add", "attendance.clock",
    },
    "receptionist": {
        "dashboard.view", "appointments.view", "calendar.associates", "calendar.birthdays", "calendar.events",
        "bookings.view", "appointments.manage", "appointments.complete", "bookings.manage",
        "patients.view", "patients.contact", "patients.manage", "documents.upload",
        "leads.view", "leads.manage", "followups.view", "followups.manage", "reminders.view", "reminders.send",
        "quotes.view", "quotes.manage", "attendance.clock", "lab.view", "lab.all_branches",
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


def user_overrides(conn, user_id: int) -> dict[str, bool]:
    """Individual access for one user: {permission: True (added) / False (removed)}, on top of their role."""
    return {r["permission"]: bool(r["granted"]) for r in conn.all("SELECT permission, granted FROM user_permissions WHERE user_id = ?",
                                                                   (user_id,))
            if r["permission"] in PERM_KEYS and r["permission"] not in LOCKED}


def load_user_permissions(conn, user_id: int, role: str) -> set[str]:
    """The role's access, plus permissions added for this user, minus permissions removed for this user.
    Super admins always have everything; super-admin-only permissions can never be added to anyone else."""
    perms = load_role_permissions(conn, role)
    if role == "super_admin":
        return perms
    for perm, on in user_overrides(conn, user_id).items():
        if on:
            perms.add(perm)
        else:
            perms.discard(perm)
    return perms


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
    """Which patients a user may see.

    Dental Haven keeps one patient list for all branches (like MyMedsPH): anyone whose access role has
    "patients.view" sees every patient, in every branch. What they can do with a patient (edit details, clinical
    records, billing, ...) is controlled by the other permissions of their role. Roles without "patients.view",
    and lab-only accounts with no branch, see no patients.
    """
    if user.role == "super_admin":
        return "1 = 1", []
    # Lab-only accounts (a laboratory but no branch) never see patient records, whatever their role allows.
    if user.can("patients.view") and user.branch_ids:
        return "1 = 1", []
    return "1 = 0", []


def can_see_patient(conn, user, patient_id: int) -> bool:
    frag, params = patient_scope(user, "p")
    row = conn.one(f"SELECT p.id FROM patients p WHERE p.id = ? AND {frag}", [patient_id, *params])
    return row is not None


def can_see_clinical(conn, user, patient_id: int) -> bool:
    return user.can("clinical.view") and can_see_patient(conn, user, patient_id)

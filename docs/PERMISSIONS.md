# Roles and permissions

Dental Haven has exactly four roles: **Super admin**, **Dentist**, **Staff** and **Receptionist**.

## How access is enforced
- **On the server, for every request.** Each staff route is protected by `@require(<permission>)` (`app/auth.py`). Hiding a link in the interface is only for convenience and is never the control.
- **By role.** Each role carries a set of permissions, which a super admin edits on the **Role access** page. The permissions *users.manage*, *roles.manage*, *audit.view* and *system.settings* are locked: they belong to super admins only and can't be granted to any other role (`app/permissions.py: LOCKED`). This means only super admins can create users, assign or change roles, or change role access.
- **By branch.** Users see bookings, patients, invoices, reports, leads and attendance only for their assigned branches. The branch switcher narrows the view further, and a user can never pick a branch they aren't assigned to.
- **By assigned patient (dentists).** A dentist can open a patient's record only if they're assigned to that patient. Booking an appointment with a dentist assigns them automatically, and a super admin can also grant or remove access on the patient page.
- **Own schedule only (dentists).** Without *View associates' schedules*, a dentist sees only their own appointments on the calendar.
- **Contact details.** Without *View patient contact details*, phone numbers, email and address show as "Hidden".
- **Laboratory users.** A user linked to a laboratory (for example DSDL) under *Authorized laboratories* sees every case sent to that lab, and needs no branch.
- **Front-desk clinical access.** Staff and Receptionists see a patient's short **alert flag** (for example "Penicillin allergy") but not the history, notes, treatment plans or clinical documents. A super admin can change this on the Role access page.
- **No self-escalation.** Nobody can change their own role or deactivate themselves, the last active super admin can't be removed, and changing a user's role, branches or active status signs them out so the new access applies straight away.
- **Least privilege by default.** New users get a one-time temporary password they must change at first sign-in. They start with no branches until one is assigned, and their role has to be chosen explicitly.
- **Audit trail.** Every one of these is logged with who made the change and when: user creation, role, branch and active changes, password resets, role-access changes, patient-record changes, voids and refunds, attendance corrections, payroll actions, report exports and settings changes.

## Default access (recommended)
Permission names follow MyMedsPH so the team recognises them. The clinic's MyMedsPH screenshots had every box unticked, so these defaults are a starting point: a super admin should review them on **Role access** before real use.
⚠ = sensitive (health data or financial impact). — = super admin only, can't be granted.

| Permission | Dentist | Staff | Receptionist | Super admin |
|---|:-:|:-:|:-:|:-:|
| **Dashboard privileges** | | | | |
| View dashboard (`dashboard.view`) | ✓ | ✓ | ✓ | ✓ |
| View patients with balance (`dashboard.balances`) ⚠ |  | ✓ |  | ✓ |
| **Calendar** | | | | |
| View Calendar & Appointments (`appointments.view`) | ✓ | ✓ | ✓ | ✓ |
| View Associates (other dentists' appointments) (`calendar.associates`) |  | ✓ | ✓ | ✓ |
| View Birthdays (`calendar.birthdays`) | ✓ | ✓ | ✓ | ✓ |
| View Follow-ups (`followups.view`) | ✓ | ✓ | ✓ | ✓ |
| View Events/Schedules (dentist schedules) (`calendar.events`) | ✓ | ✓ | ✓ | ✓ |
| View Online Bookings (`bookings.view`) |  | ✓ | ✓ | ✓ |
| **Appointments** | | | | |
| Book, confirm, reschedule and cancel appointments (`appointments.manage`) |  | ✓ | ✓ | ✓ |
| Check in, complete and mark no-show (`appointments.complete`) | ✓ | ✓ | ✓ | ✓ |
| Confirm or decline online bookings (`bookings.manage`) |  | ✓ | ✓ | ✓ |
| Create and complete follow-ups (`followups.manage`) | ✓ | ✓ | ✓ | ✓ |
| **Patients** | | | | |
| View patient list and profiles (`patients.view`) | ✓ | ✓ | ✓ | ✓ |
| View patient contact number, email address and home address (`patients.contact`) ⚠ |  | ✓ | ✓ | ✓ |
| Edit patient data (`patients.manage`) |  | ✓ | ✓ | ✓ |
| **Patient privileges** | | | | |
| Can delete patients (`patients.delete`) ⚠ |  |  |  | ✓ |
| **Progress notes** | | | | |
| View only progress notes (read-only clinical record) (`clinical.view`) ⚠ | ✓ |  |  | ✓ |
| Add new progress note (`progress.add`) ⚠ | ✓ |  |  | ✓ |
| View progress notes list actions (edit/delete entries) (`progress.actions`) ⚠ | ✓ |  |  | ✓ |
| Edit medical & dental history and alert flag (`clinical.edit`) ⚠ | ✓ |  |  | ✓ |
| **Patient treatment plans** | | | | |
| Delete treatment plan (`plans.delete`) ⚠ |  |  |  | ✓ |
| Edit existing treatment plan (`plans.edit`) ⚠ | ✓ |  |  | ✓ |
| Add new treatment plan (`plans.add`) ⚠ | ✓ |  |  | ✓ |
| Generate Progress Note (from a plan item) (`plans.generate`) ⚠ | ✓ |  |  | ✓ |
| **Patient charting** | | | | |
| Update patient chart (`chart.edit`) ⚠ | ✓ |  |  | ✓ |
| Delete patient chart (`chart.delete`) ⚠ |  |  |  | ✓ |
| **Patient bills/payments** | | | | |
| View bills and payments (`billing.view`) |  | ✓ |  | ✓ |
| Add bill (`billing.manage`) |  | ✓ |  | ✓ |
| Edit Patient bill (`bills.edit`) |  | ✓ |  | ✓ |
| Add Payment (and patient deposits) (`payments.add`) |  | ✓ |  | ✓ |
| Apply Account Credit (`credit.apply`) |  | ✓ |  | ✓ |
| Delete patient bill (void) and refunds (`billing.void`) ⚠ |  |  |  | ✓ |
| **Patient prescriptions** | | | | |
| Delete patient prescription (`rx.delete`) ⚠ |  |  |  | ✓ |
| Create patient prescription (`rx.create`) ⚠ | ✓ |  |  | ✓ |
| Edit patient prescription (`rx.edit`) ⚠ | ✓ |  |  | ✓ |
| **Upload attachments / lab results** | | | | |
| Upload attachments / lab results (`documents.upload`) ⚠ | ✓ | ✓ | ✓ | ✓ |
| Delete patient attachment (`documents.delete`) ⚠ |  |  |  | ✓ |
| **Patient certificates** | | | | |
| Delete patient certificate (`cert.delete`) ⚠ |  |  |  | ✓ |
| Create patient certificate (`cert.create`) ⚠ | ✓ |  |  | ✓ |
| Edit patient certificate (`cert.edit`) ⚠ | ✓ |  |  | ✓ |
| **Laboratory** | | | | |
| View lab cases (`lab.view`) | ✓ | ✓ |  | ✓ |
| Create and update lab cases (`lab.manage`) | ✓ |  |  | ✓ |
| **Expenses** | | | | |
| View Expenses (`expenses.view`) ⚠ |  | ✓ |  | ✓ |
| Post Expenses (`expenses.post`) ⚠ |  |  |  | ✓ |
| Add Expenses (`expenses.add`) |  | ✓ |  | ✓ |
| **Report cards** | | | | |
| Generate patient report cards (`reportcards.generate`) ⚠ | ✓ |  |  | ✓ |
| Review and approve patient report cards (`reportcards.review`) ⚠ | ✓ |  |  | ✓ |
| **Leads & reminders** | | | | |
| View lead inbox (`leads.view`) |  | ✓ | ✓ | ✓ |
| Create, assign and convert leads (`leads.manage`) |  |  | ✓ | ✓ |
| View reminder outbox (`reminders.view`) |  | ✓ | ✓ | ✓ |
| Generate reminders and record manual sends (`reminders.send`) |  | ✓ | ✓ | ✓ |
| Edit message and response templates (`templates.manage`) |  |  |  | ✓ |
| **Reports** | | | | |
| View sales, collections and balances reports (`reports.sales`) |  |  |  | ✓ |
| View appointment, lead and visit reports (`reports.operations`) |  | ✓ |  | ✓ |
| Export authorised reports to CSV (`reports.export`) |  |  |  | ✓ |
| **Staff & payroll** | | | | |
| View attendance (DTR) (`attendance.view`) |  | ✓ |  | ✓ |
| Record, import and correct attendance (`attendance.manage`) ⚠ |  |  |  | ✓ |
| View and edit compensation settings (`compensation.manage`) ⚠ |  |  |  | ✓ |
| Prepare draft payroll summaries (`payroll.prepare`) ⚠ |  |  |  | ✓ |
| Approve payroll summaries (`payroll.approve`) ⚠ |  |  |  | ✓ |
| **Configuration** | | | | |
| Edit public website content (`content.manage`) |  |  |  | ✓ |
| Edit branches, services, hours, rooms and schedules (`settings.manage`) |  |  |  | ✓ |
| **Super admin only** | | | | |
| Create users and assign roles/branches/labs (`users.manage`) ⚠ | — | — | — | ✓ |
| Grant or change role access (`roles.manage`) ⚠ | — | — | — | ✓ |
| View audit trail (`audit.view`) ⚠ | — | — | — | ✓ |
| Change system settings and import data (`system.settings`) ⚠ | — | — | — | ✓ |

## Record-level rules on top of permissions
| Rule | Where |
|---|---|
| A dentist sees only appointments where they are the dentist | `views/scheduling.py:_appt_scope` |
| Only a Dentist who is the assigned reviewer can approve a report card; super admins can't approve on a dentist's behalf | `views/reportcards.py` |
| Payroll: the approver must be someone other than the submitter, the pay rules must be confirmed, and no attendance exceptions may be open | `views/people.py` |
| Attendance in an approved payroll period is locked | `views/people.py:attendance_correct` |
| Without `attendance.manage`, a user sees only their own attendance records | `views/people.py:attendance` |
| Rates and estimates are hidden from anyone without `compensation.manage` | payroll pages and CSV |

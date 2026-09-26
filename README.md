# Dental Haven: clinic operations platform

A public website and a staff system for Dental Haven's four branches: Malolos, Guiguinto, Bocaue and San Jose del Monte (SJDM). It covers online appointment requests, scheduling, patient records, leads and follow-ups, reminders (sent manually for now), billing and sales reports, attendance, draft payroll review, dashboards and patient report cards.

## Going live
To run the real clinic site on Render with your own domain, follow **docs/GO_LIVE.md** (paid Starter plan, persistent disk, first admin from settings, weekly backup download).

## Stack and why
**Python 3.11 + Flask + SQLite (demo) / PostgreSQL (production)**, with server-rendered pages and a single stylesheet. There's no JavaScript build step.

- The original plan was Next.js + Postgres. The build workspace couldn't download packages (npm and PyPI returned 403), so Flask, which was already installed, was used instead. That way every stage could be run and tested here.
- The only runtime dependency is Flask. Production adds `psycopg` and `gunicorn` (see `docs/DEPLOYMENT.md`).
- The SQL is portable between SQLite and PostgreSQL, but **only SQLite was exercised here**.

## Quick start (demo)
```bash
pip install "Flask>=3.1"
cp .env.example .env               # optional for local use
flask --app wsgi init-db           # create tables
flask --app wsgi seed-demo --password 'DemoPass-2026'   # synthetic data only
flask --app wsgi run               # http://127.0.0.1:5000  (staff: /staff/login)
python -m unittest discover -s tests -v                 # 21 end-to-end checks
```

Demo accounts all use the password you pass to `seed-demo`. Every account ends in `@demo.dentalhaven.test`:

| Role | Email | Branches |
|---|---|---|
| Super admin | `admin@…` | all |
| Dentist | `dentist.malolos@…`, `dentist.guiguinto@…`, `dentist.bocaue@…`, `dentist.sjdm@…` | 1–2 each |
| Staff | `staff.malolos@…` (Malolos, Guiguinto), `staff.bocaue@…` (Bocaue, SJDM) | 2 each |
| Receptionist | `reception.malolos@…`, `reception.guiguinto@…`, `reception.bocaue@…`, `reception.sjdm@…` | 1 each |

All patients, leads, invoices, attendance and compensation values in the demo are **synthetic**: fictional names, `0900 000 ####` numbers, `example.test` emails, and amounts labelled "demo".

**Try it online:** see `docs/TRY_ONLINE.md` (free Render demo, one-click via `render.yaml`).

For a real installation, run `init-db`, then `seed-base`, then `create-superadmin` (see `docs/DEPLOYMENT.md`).

## What's included, by acceptance criterion
| Acceptance criterion | Where to find it |
|---|---|
| Staff switch between their authorised branches and see branch-scoped data | Branch selector in the top bar; server-side `branch_filter` / `patient_scope` |
| Only super admins create users, assign roles or change access | Administration → Users / Role access; locked permissions; audit trail |
| A patient request never shows a confirmation that hasn't been approved | `/book` → booking request **pending** → staff confirm (auto-confirm setting is off by default) |
| Confirm, reschedule, cancel and complete without conflicts | Appointment page. Checks cover dentist (across all branches), room/chair, branch hours and the dentist's schedule, inside a locked transaction |
| Patient profiles, history, notes and plans, by role | Patient page tabs: Overview, Clinical record, Documents, Change log |
| One work queue for inquiries and follow-ups | Work queue: booking requests, new leads, lead call-backs, follow-ups due |
| Invoices and payments feed sales and collections reports | Invoices → Sales & collections (branch and date filters, CSV export) |
| Attendance review and draft payroll | Attendance (DTR) with exceptions, corrections and CSV import → Payroll review (draft → submit → approve) |
| Management view across branches | Dashboard, Sales & collections, Operations report |
| Report cards for dentist review | Patient → Report card → the assigned dentist approves → printable |
| Mobile-friendly public site with editable placeholders | Public pages; Administration → Website content / Branches / Services |
| Documentation | This README and `docs/` |

## Confirmed requirements vs assumptions
**Confirmed with you:**
- The four branches, four services and in-house digital lab
- Exactly four roles; only super admins manage users and access
- Build here and deliver as a download; Flask stack (switched from Next.js because the registry was blocked)
- Dentists see assigned patients only
- Staff and Receptionists see the alert flag only, not the clinical record
- No real messages, no Facebook scraping, no payroll payments
- Synthetic demo data only

**Assumptions (all configurable; please confirm):**
- Currency PHP; time zone Asia/Manila; times stored as clinic-local.
- Branch hours Mon–Sat 09:00–18:00 and closed Sunday (placeholder); two chairs per branch; default durations of 30/60/90/60 minutes by service.
- Online requests don't hold a slot; staff confirm against live availability. Requests need at least 12 hours' notice and can be up to 60 days ahead, in 30-minute steps.
- Invoice numbers use the format `{prefix}-{year}-{seq:05d}` with a prefix per branch (MAL, GUI, BOC, SJD). **Tax is off.** Service prices are blank; nothing is invented.
- Sales = invoices issued in the period. Collections = payments received in the period minus refunds.
- Reminder rule: 24 hours before by SMS, with quiet hours 20:00–08:00. It stays manual send only.
- Attendance exceptions are measured against branch opening and closing times, with no grace period and no break deduction.
- Payroll shows only rate × days/hours for daily or hourly rates, marked **unconfirmed**. Monthly, percentage and per-case pay show "needs pay rule". Approval stays blocked until a super admin confirms the pay rules.
- Staff can view but not manage leads; Receptionists manage leads. Staff can record payments but not void or refund.

## Open questions (they block real use of these areas, not the build)
1. **Messaging:** which channels (SMS, email, Messenger), which provider, who approves templates, and quiet hours.
2. **Payroll:** pay basis for each role, overtime and holiday rules, associate dentist percentages or commissions, cut-offs, and approvers.
3. **Auto-confirm:** should online requests ever confirm automatically, and for which services?
4. **Tax and receipts:** VAT status, senior citizen/PWD discounts, and official receipt requirements.
5. **Retention:** how long to keep records, and the DPO's details (see `docs/PRIVACY_CHECKLIST.md`).
6. **Content:** approved copy, addresses, phone numbers, hours, photos (with authorisation) and testimonials (with consent).

## Known gaps
- No live SMS, email or Facebook integration (see `docs/INTEGRATIONS.md`). Manual workflows cover each one.
- No two-factor sign-in; no password-reset email (a super admin resets passwords).
- The PostgreSQL path hasn't been run (no driver available in the build environment).
- No merge tool for duplicate patient records; the system warns about duplicates when you register a patient.
- Rate limiting of public forms is per process (see the deployment notes).

## Layout
```
app/            Flask app: auth, permissions, scheduling, billing, messaging, payroll, uploads
app/views/      public, auth, dashboard, scheduling, patients, leads, billing, people, reportcards, admin
app/templates/  public site + staff app (Jinja)
app/static/     css/app.css, js/app.js (progressive enhancement only)
migrations/     SQL migrations (portable)
tests/          end-to-end tests of the acceptance criteria
docs/           PERMISSIONS, INTEGRATIONS, PRIVACY_CHECKLIST, DEPLOYMENT
```

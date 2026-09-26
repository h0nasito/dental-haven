# Integrations: status and next steps

**No external integration is configured or verified yet.** The code can send two kinds of outside messages, and both stay off until set up: emails from the branch Gmail accounts (to dentists and patients), and SMS through Semaphore. Nothing moves money.

| Area | Status | What works now | What's needed to integrate |
|---|---|---|---|
| Email to patients | Built, **off until the branch Gmail is set up**; not yet verified with a real account | The patient is emailed automatically when their booking is **approved**, **declined** (time not available), **rescheduled** or **cancelled**, and gets a **reminder the day before**. Staff see what was sent on the appointment and request pages. | The same branch Gmail app passwords as dentist emails (below). |
| SMS to patients | Built, **off**; not verified | Same messages as email, by text, to Philippine mobile numbers. Until switched on, reminders wait in the **Reminder outbox** for staff to send by hand. | A Semaphore account (semaphore.co) with credits and an approved sender name, then `SEMAPHORE_API_KEY` and `SEMAPHORE_SENDER_NAME` on the server. Test with a staff phone first. |
| Email to dentists (their own appointments) | Built, **off until set up**; not yet verified with a real account | When a booking is approved or booked, rescheduled or cancelled, the dentist gets an email with the day, time, branch, patient name and procedure (the subject line has no patient name). Each appointment page lists the emails and their status. | An app password for each branch Gmail, set as `MAIL_<BRANCH>_USERNAME` / `MAIL_<BRANCH>_PASSWORD` on the server (see below), then **System settings → Send me a test email**. Needs a paid Render plan (free Render blocks outgoing email). |
| Facebook Page / Messenger | Not connected; nothing is scraped | Staff log Facebook and Messenger inquiries as leads (source *Facebook page* or *Messenger*) and reply using the shared templates. | A Meta app with Page access, app review for `pages_messaging`, a webhook endpoint that creates leads, and compliance with Meta's 24-hour messaging window. Decide who owns the Page token. |
| Online payments (GCash/Maya/cards) | Not integrated | Staff record payments manually with the method and reference number. | A payment gateway account and a decision on whether online pre-payment is wanted. |
| Biometric / time clock | Not integrated | Staff enter time records by hand or import them as CSV (`employee,date,time_in,time_out[,branch]`). | The device's export format or API. |
| Accounting / BIR receipts | Not integrated | Printable "statement of account", clearly marked as not an official receipt | Confirmation from the clinic's accountant about official receipt/invoice rules (including BIR requirements for computerised systems) before these are used as receipts. |
| Maps | Link only | Each branch page links to its map using the URL a super admin enters | Nothing more is required. Embedding a map would need a CSP change. |

## Who gets which message
- **Booking updates** (approved, declined, rescheduled, cancelled) go to everyone who booked, because they answer the patient's own request. The only exception is a patient marked *opted out of all messages*.
- **Day-before reminders** follow the patient's contact consent: email only if they agreed to email, SMS only if they agreed to SMS.
- Messages carry the day, time, branch, service and dentist. They never include the internal cancel/decline reason, notes or any treatment details.
- The log keeps only the event, channel, a masked address (e.g. `j***@gmail.com`) and the status. Message text is never stored.
- The demo site never sends anything.
- If nothing could be sent (not set up, failed, no email or mobile number), staff see *"The patient was NOT notified automatically"* and should call or text them.

## Where reminders stand
1. When an appointment is **confirmed**, a reminder is created for each active rule (default: 24 hours before by SMS; a same-day rule is included but switched off).
2. A patient who has opted out, or hasn't agreed to that channel, gets a reminder marked `skipped_opt_out` or `skipped_no_consent` with no message text.
3. If a send time falls in quiet hours (default 20:00–08:00), it moves to the next morning.
4. Rescheduling replaces unsent reminders. Cancelling, completing or marking a no-show cancels them.
5. `flask --app wsgi generate-reminders` can run as a daily scheduled job to catch anything missed. It **queues** reminders only.
6. On the live site, every 5 minutes the server sends due reminders automatically by email and/or SMS (per consent), once Gmail or Semaphore is set up. A reminder that can't go out stays in the **Reminder outbox** for staff. `flask --app wsgi send-reminders` does the same on demand; set `AUTO_REMINDERS=off` to stop automatic sending.

## Setting up emails (branch Gmail accounts)
Each dentist and patient email is sent from the Gmail of the appointment's branch:

| Branch | Sender | Server settings to add |
|---|---|---|
| Malolos | dentalhavenmalolos@gmail.com | `MAIL_MALOLOS_USERNAME`, `MAIL_MALOLOS_PASSWORD` |
| Guiguinto | dentalhavenguiguintobranch@gmail.com | `MAIL_GUIGUINTO_USERNAME`, `MAIL_GUIGUINTO_PASSWORD` |
| Bocaue | dentalhavenbocaue@gmail.com | `MAIL_BOCAUE_USERNAME`, `MAIL_BOCAUE_PASSWORD` |
| San Jose del Monte | dentalhavensjdm@gmail.com | `MAIL_SJDM_USERNAME`, `MAIL_SJDM_PASSWORD` |

For each branch Gmail:
1. Sign in to the Gmail account, open **Google Account → Security** and turn on **2-Step Verification**.
2. Open **App passwords** (myaccount.google.com/apppasswords), create one named "Dental Haven" and copy the 16-letter password. This is not the normal Gmail password.
3. On the live server (Render → your service → **Environment**) add `MAIL_<BRANCH>_USERNAME` = the Gmail address and `MAIL_<BRANCH>_PASSWORD` = the app password. Save; Render restarts the site.

Then sign in as super admin → **Administration → System settings**. The table shows which branches are set up; **Send me a test email** sends one test from each account. Also make sure each dentist's user account has their email and **Email this dentist about their appointments** ticked.

Optional: `MAIL_USERNAME` / `MAIL_PASSWORD` set a shared fallback sender for any branch without its own. Gmail allows about 500 emails a day per account. If an app password is ever exposed, delete it in that Google Account and create a new one.

## Setting up SMS (optional, later)
1. Create an account at semaphore.co, buy credits and apply for a sender name (e.g. `DentalHaven`). Approval can take a few days.
2. In Render → Environment add `SEMAPHORE_API_KEY` (from the Semaphore dashboard) and `SEMAPHORE_SENDER_NAME`.
3. Book a test appointment for a staff member's own mobile number and check the text arrives before relying on it.

# Integrations: status and next steps

**No external integration is configured or verified yet.** The only outside connection the code can make is the dentist appointment email below, and it stays off until a clinic Gmail account is added. Nothing moves money.

| Area | Status | What works now | What's needed to integrate |
|---|---|---|---|
| SMS reminders | Not configured | Reminders are queued in the **Reminder outbox** following the reminder rules. Staff copy the text, send it from the clinic phone, and mark it *Sent* or *Failed*. | Choose a Philippine SMS provider, set up a registered sender name, API credentials in `.env`, and a signed-off template list. Then implement `MessagingProvider.send()` in `app/messaging.py`, register it in `PROVIDERS`, and add a scheduled job. Keep opt-out handling (STOP replies) in place. |
| Email to patients | Not configured | Same manual flow as SMS | An SMTP or transactional email account, SPF/DKIM for the clinic domain, and a provider class. |
| Email to dentists (their own appointments) | Built, **off until set up**; not yet verified with a real account | When a booking is approved or booked, rescheduled or cancelled, the dentist gets an email with the day, time, branch, patient name and procedure (the subject line has no patient name). Each appointment page lists the emails and their status. | An app password for each branch Gmail, set as `MAIL_<BRANCH>_USERNAME` / `MAIL_<BRANCH>_PASSWORD` on the server (see below), then **System settings → Send me a test email**. Needs a paid Render plan (free Render blocks outgoing email). |
| Facebook Page / Messenger | Not connected; nothing is scraped | Staff log Facebook and Messenger inquiries as leads (source *Facebook page* or *Messenger*) and reply using the shared templates. | A Meta app with Page access, app review for `pages_messaging`, a webhook endpoint that creates leads, and compliance with Meta's 24-hour messaging window. Decide who owns the Page token. |
| Online payments (GCash/Maya/cards) | Not integrated | Staff record payments manually with the method and reference number. | A payment gateway account and a decision on whether online pre-payment is wanted. |
| Biometric / time clock | Not integrated | Staff enter time records by hand or import them as CSV (`employee,date,time_in,time_out[,branch]`). | The device's export format or API. |
| Accounting / BIR receipts | Not integrated | Printable "statement of account", clearly marked as not an official receipt | Confirmation from the clinic's accountant about official receipt/invoice rules (including BIR requirements for computerised systems) before these are used as receipts. |
| Maps | Link only | Each branch page links to its map using the URL a super admin enters | Nothing more is required. Embedding a map would need a CSP change. |

## Where reminders stand
1. When an appointment is **confirmed**, a reminder is created for each active rule (default: 24 hours before by SMS; a same-day rule is included but switched off).
2. A patient who has opted out, or hasn't agreed to that channel, gets a reminder marked `skipped_opt_out` or `skipped_no_consent` with no message text.
3. If a send time falls in quiet hours (default 20:00–08:00), it moves to the next morning.
4. Rescheduling replaces unsent reminders. Cancelling, completing or marking a no-show cancels them.
5. `flask --app wsgi generate-reminders` can run as a daily scheduled job to catch anything missed. It **queues** reminders only; it never sends them.

## Setting up dentist emails (branch Gmail accounts)
Each dentist email is sent from the Gmail of the appointment's branch:

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

# Privacy, retention and regulatory items for Dental Haven to review

This is a checklist for the clinic, its Data Protection Officer (DPO) and its lawyer or accountant. **It isn't legal advice, and the system makes no claim of legal compliance.** Treat every item as something to verify.

## Philippine Data Privacy Act of 2012 (RA 10173) and its IRR, plus National Privacy Commission issuances
- [ ] Appoint a Data Protection Officer and publish their contact details. The privacy notice has a placeholder for them.
- [ ] Check whether NPC registration of the DPO and the processing systems applies. Health information is *sensitive personal information*.
- [ ] Finish and approve the **privacy notice** (Website content → Privacy notice). The current text is a draft.
- [ ] Approve the **consent wording** on the booking and inquiry forms and for reminders (Website content → consent texts).
- [ ] Record the lawful basis for each purpose: care delivery, reminders, promotions (a separate opt-in field exists), and billing.
- [ ] Have a data-sharing or outsourcing agreement with every processor: hosting provider, SMS/email provider, laboratory partners.
- [ ] Put a personal data breach procedure in place, including NPC and patient notification timelines.
- [ ] Have a process for data-subject requests (access, correction, objection). The patient profile and exports support access and correction.
- [ ] Carry out a privacy impact assessment for this system.

## Record retention
- [ ] Confirm how long to keep dental and medical records. Check DOH, PRC/Board of Dentistry and any Philippine Dental Association guidance, and the limitation periods for legal claims.
- [ ] Confirm retention for financial records (BIR rules on books and receipts).
- [ ] Confirm retention for CCTV, attendance and payroll records (DOLE rules on employment records).
- [ ] Decide how to handle **inactive patients**. The system currently deactivates rather than deletes, and has no automatic purge until you confirm the periods.

## Clinical and professional rules
- [ ] Confirm who may write in and see clinical records. The defaults are assigned dentists only, with front desk seeing the alert flag only.
- [ ] Get written patient consent for clinical photos and for any gallery or testimonial use. The gallery and feedback tools require a consent note.
- [ ] Check that advertising follows professional rules (no unapproved claims, prices or testimonials). The site uses placeholders until content is approved.

## Tax and billing
- [ ] Confirm VAT or non-VAT registration, senior citizen and PWD discount handling, and official receipt/invoice requirements. Tax is **off** by default and the printout isn't an official receipt.

## Employment and payroll
- [ ] Confirm pay rules: basis, overtime, holiday and rest-day premiums, night differential, 13th-month pay, SSS, PhilHealth and Pag-IBIG contributions, withholding tax, and the associate dentists' percentage or commission arrangements.
- [ ] Confirm cut-off dates and the approval chain. The system enforces that the submitter and approver are different people.

## Technical safeguards already in the build
- Passwords are hashed with scrypt. Accounts lock after 5 failed attempts. Sessions are stored server-side and time out after 60 minutes idle (12 hours maximum).
- Permissions are checked on the server. Access is scoped by branch and by assigned patient, and there's an audit trail of changes.
- Forms are protected against CSRF. Security headers include CSP, frame denial and nosniff. Staff pages are marked no-store.
- Patient searches are sent by POST so names don't appear in URLs, and patient details aren't written to application logs.
- Uploads are limited to known file types (checked by file signature, not name), stored under random names outside the web root, served only to authorised users, and each access is logged.
- Public forms have a honeypot, a rate limit and a consent checkbox.

## Still to do before going live (operational)
- [ ] Serve the site over HTTPS only (set `APP_ENV=production` for secure cookies).
- [ ] Encrypt backups and test restoring them (see DEPLOYMENT.md).
- [ ] Decide whether to require two-factor sign-in for super admins. It isn't implemented yet.

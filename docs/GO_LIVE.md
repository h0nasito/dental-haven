# Going live on Render with dentalhaven.net

This turns the free demo into the real clinic site: paid Starter plan, a 5 GB disk that keeps all data,
no demo data, and your own domain. Cost: about $7/month for the server plus $1.25/month for the disk.

**Important:** the live site starts from an empty database. Anything typed into the demo is not carried over.

## 1. Create the service from the Blueprint
`render.yaml` is already the live-site configuration (the old demo settings are in `render.demo.yaml`).
In Render, click **New → Blueprint**, choose the `dental-haven` repository, and continue.

## 2. Fill in the settings in Render
1. Render lists what it will create: a web service on the Starter plan with a 5 GB disk.
2. Fill in the values it asks for:
   - `INITIAL_ADMIN_EMAIL`: the email the clinic owner will sign in with.
   - `INITIAL_ADMIN_NAME`: their name.
   - `INITIAL_ADMIN_PASSWORD`: a temporary password with at least 10 characters, upper- and lower-case letters and a number. They must change it at first sign-in.
   - The `MAIL_..._PASSWORD` values can stay empty for now (see step 5).
3. Add a payment card if Render asks, then apply the changes. The first start takes a few minutes.
4. If the deploy log shows `Created the first super admin`, the site is ready.

## 3. First sign-in
1. Open `https://<your-service>.onrender.com/staff/login` and sign in with the INITIAL_ADMIN email and password.
2. Choose a new password.
3. In Render → Environment, delete `INITIAL_ADMIN_PASSWORD` (it's no longer used).
4. Check **Administration → Role access**, then **Branches & rooms** (hours, rooms), **Dentist schedules**, and **Website content**.
5. Create the staff accounts under **Administration → Users**. Each person gets a temporary password.
6. Import the patient records under **Administration → Import from MyMedsPH**.

## 4. Connect dentalhaven.net
1. Render → your service → **Settings → Custom Domains** → add `dentalhaven.net` and `www.dentalhaven.net`.
2. Porkbun → **Domain Management** → dentalhaven.net → **DNS**. Delete the default parking records, then add exactly the records Render shows.
3. Wait until Render marks both as verified (usually under an hour). HTTPS is set up automatically.

## 5. Dentist emails (optional, any time)
For each branch Gmail: turn on 2-Step Verification, create an app password (myaccount.google.com/apppasswords),
and paste it into the matching `MAIL_<BRANCH>_PASSWORD` in Render → Environment. Then use
**Administration → System settings → Send me a test email**. Details: docs/INTEGRATIONS.md.

## 6. Backups (every week)
**Administration → System settings → Download full backup** saves one zip with the whole database and all uploaded
files. It contains every patient record, so keep it on an encrypted, private drive, never in email or chat.

## If something goes wrong
- The deploy log says `DATA_DIR ... doesn't exist`: the disk isn't attached. Check the service's **Disks** tab (mount path `/var/data`).
- `No super admin yet`: `INITIAL_ADMIN_EMAIL` or `INITIAL_ADMIN_PASSWORD` is missing. Add them and redeploy.
- `INITIAL_ADMIN_PASSWORD: ...`: the password is too weak. Change it and redeploy.

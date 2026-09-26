# Try the demo online (Render, free plan)

The online demo uses synthetic data only. It shows a "Demo site" banner, is hidden from search engines, and **resets to fresh demo data each time it restarts**. Don't enter real patient information.

## You need
- A GitHub account (free), to hold the code
- A Render account (free); sign up with your GitHub account

## Steps
1. **Put the code on GitHub**
   - On github.com, click **New repository**, name it `dental-haven`, choose **Private**, and click **Create repository**.
   - On the new repository page, click **uploading an existing file**.
   - Unzip `dental-haven.zip`, open the `dental-haven` folder, and drag **everything inside it** onto the page. `render.yaml` must end up at the top level, not inside a subfolder.
   - Click **Commit changes**.
2. **Create the site on Render**
   - On dashboard.render.com, choose **New → Blueprint**, connect GitHub if asked, and pick the `dental-haven` repository.
   - Render reads `render.yaml`. When it asks for **DEMO_PASSWORD**, type a password of at least 10 characters that mixes upper- and lower-case letters and a number, e.g. `TrialPass-2026`.
   - Click **Apply**. The first build takes about 3–5 minutes.
3. **Open it**
   - Render shows the site address, e.g. `https://dental-haven-demo.onrender.com`.
   - Website: that address. Staff: add `/staff/login`.
   - Sign in as `admin@demo.dentalhaven.test` (or any demo account listed in the README) with your DEMO_PASSWORD.

## What to expect on the free plan
- After 15 minutes without visitors the site goes to sleep. The next visit takes about a minute to load, and the demo data resets.
- There are 750 free hours per month.
- To change something, edit or upload the file on GitHub and Render redeploys automatically.

## Moving to a real clinic site later
Don't reuse this demo setup. A real site needs a paid plan, a PostgreSQL database, persistent storage for documents, `APP_ENV=production`, and `seed-base` + `create-superadmin` instead of demo data. See `docs/DEPLOYMENT.md`.

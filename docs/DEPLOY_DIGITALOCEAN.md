# Going live on DigitalOcean with dentalhaven.net

This guide puts the real clinic system on a DigitalOcean server in Singapore, with your domain and HTTPS.
You don't need to know Linux: every command is copy and paste. Expect 45–60 minutes, most of it waiting.

**Cost:** about $14.40 a month (server $12 + daily backups $2.40).
**Starts empty:** the live system has its own new database. Nothing from the demo is carried over.

What you need before starting:
- A payment card for DigitalOcean.
- Your Porkbun login (for the dentalhaven.net DNS).
- Your GitHub login, and the newest code pushed to GitHub from GitHub Desktop.
- The clinic owner's email, and a temporary password for them (10+ characters, upper- and lower-case letters, a number).

---

## 1. Create the server (Droplet)
1. Sign up at **digitalocean.com** and add your payment card.
2. Click **Create → Droplets**.
3. Choose:
   - **Region:** Singapore (SGP1).
   - **Image:** Ubuntu **24.04 (LTS) x64**.
   - **Size:** Basic → Regular → **$12/mo (2 GB RAM, 1 CPU, 50 GB SSD)**.
   - **Backups:** turn on **Daily** backups.
   - **Authentication:** Password. Choose a long password (16+ characters) and store it in a password manager.
     This is the server's master password. Never send it in chat or email.
   - **Hostname:** `dental-haven`.
4. Click **Create Droplet**. After a minute, copy its **IPv4 address** (four numbers, like `159.89.x.x`).

## 2. Point dentalhaven.net to the server
1. In **Porkbun → Domain Management → dentalhaven.net → DNS**:
2. Delete the old records for `dentalhaven.net` and `www` that point to Render or to Porkbun parking
   (type ALIAS, CNAME or A). **Leave MX and TXT records alone** (those are for email).
3. Add two records:

   | Type | Host | Answer | TTL |
   |---|---|---|---|
   | A | *(leave empty)* | your Droplet IP | 600 |
   | A | `www` | your Droplet IP | 600 |

4. DNS changes usually take 10–30 minutes. Continue with the next steps meanwhile.

## 3. Open the server's Console
In DigitalOcean, open your Droplet and click **Console** (top right). A black window opens, already signed in as `root`.
Paste with **right-click → Paste** or **Ctrl+Shift+V**.

## 4. Give the server read-only access to your GitHub code
1. Paste this into the Console and press Enter:
   ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/github_deploy -C "dental-haven-server" && printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n  StrictHostKeyChecking accept-new\n' >> ~/.ssh/config && cat ~/.ssh/github_deploy.pub
   ```
2. It prints one line starting with `ssh-ed25519`. Select and copy that whole line.
3. On GitHub, open the **dental-haven** repository → **Settings → Deploy keys → Add deploy key**.
   Title: `DigitalOcean server`. Paste the line into **Key**. Leave **Allow write access** unticked. Click **Add key**.

## 5. Download the code and run the setup
Replace `YOUR-GITHUB-NAME` with your GitHub username, then paste:
```bash
git clone git@github.com:YOUR-GITHUB-NAME/dental-haven.git /opt/dental-haven && bash /opt/dental-haven/deploy/digitalocean/setup.sh
```
The setup asks a few questions:
- **Domain name:** press Enter for `dentalhaven.net`.
- **Also answer on www:** press Enter (yes).
- **Clinic owner's email and name.**
- **Temporary password**, typed twice. Nothing shows while you type; that's normal. It is never saved on the server,
  and the owner must change it at first sign-in.
- **Email for HTTPS certificate notices:** press Enter to use the owner's email.

Then it installs everything by itself (5–10 minutes):
- security updates and the firewall
- the system, set to start by itself after a reboot
- the database
- a nightly database backup
- HTTPS

It ends with **Done** and the address to open.

**If it says HTTPS isn't on yet:** the DNS from step 2 hasn't reached the server. Wait 15–30 minutes, then type
`dental-haven-https` in the Console.

## 6. First sign-in
1. Open **https://dentalhaven.net/staff/login**, sign in with the owner's email and temporary password, and choose a new password.
2. Check **Administration → Role access**, **Branches & chairs**, **Dentist schedules** and **Website content**.
3. Import employees (**Employees → Import**), then **Administration → Users → Create logins for employees**,
   and hand out the printed slips.
4. Check **Fee schedule** and **Quotations → Item list** (both come pre-filled) and adjust prices if needed.
5. Import patient records under **Administration → Import from MyMedsPH**.

## 7. Turn on emails (when you're ready)
For each branch Gmail: turn on 2-Step Verification and create an app password at myaccount.google.com/apppasswords. Then in the Console:
```bash
nano /etc/dental-haven/env
```
Remove the `#` at the start of that branch's two `MAIL_...` lines and paste the app password after `MAIL_..._PASSWORD=`.
Save with **Ctrl+O, Enter**, exit with **Ctrl+X**, then run:
```bash
systemctl restart dental-haven
```
Test it with **Administration → System settings → Send me a test email**.

## Updating the system later
When there's a new version: push it to GitHub from GitHub Desktop, open the Droplet Console and type:
```bash
dental-haven-update
```
It backs up the database, downloads the new version, updates the database structure and restarts. The system is down for about 10 seconds.

## Backups: three layers
1. **DigitalOcean daily backups** of the whole server, kept for 7 days. Restore from **Droplet → Backups**.
2. **Nightly database copy** at 11:30 PM on the server itself, kept for 14 days, in `/var/backups/dental-haven`.
   Make one any time with `dental-haven-backup`.
3. **Off-site copy, once a week:** **Administration → System settings → Download full backup**. It contains every patient record,
   so keep it on an encrypted drive, never in email or chat.

Once, after the first week, ask for help to do a **test restore** so you know recovery works.

## Useful commands (type them in the Console)
| Command | What it does |
|---|---|
| `dental-haven-update` | Get the newest version from GitHub and restart |
| `systemctl restart dental-haven` | Restart the system |
| `systemctl status dental-haven` | Show whether it's running |
| `journalctl -u dental-haven -n 50 --no-pager` | Show the latest errors |
| `dental-haven-backup` | Make a database backup now |
| `dental-haven-https` | Turn on HTTPS (if setup couldn't) |
| `df -h /` | Show how much disk space is left |

## If something goes wrong
- **`Permission denied (publickey)` in step 5:** the deploy key wasn't added to the right repository, or the GitHub name is wrong.
- **The site shows "502 Bad Gateway":** the system stopped. Run `journalctl -u dental-haven -n 50 --no-pager` and send the
  last lines (they contain no patient data) to whoever helps you.
- **You can't sign in over `http://`:** sign-in only works over HTTPS. Run `dental-haven-https`.
- **Disk almost full:** in DigitalOcean, add a Volume, or resize the Droplet. Ask for help before moving files.

## Where things are on the server
| What | Where |
|---|---|
| Code | `/opt/dental-haven` |
| Database and uploaded files | `/var/lib/dental-haven` |
| Settings (secret key, email passwords) | `/etc/dental-haven/env` (only root can read it) |
| Nightly database copies | `/var/backups/dental-haven` |

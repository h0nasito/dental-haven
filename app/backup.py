"""Full backup for super admins: everything needed to restore the system, plus a copy anyone can open.

The zip holds:
- dental_haven.db: the whole database (a consistent copy taken while the site runs). This is what a restore uses.
- patient-documents/: private uploads (patient files and photos, lab case photos, receipts…).
- website-images/: public website pictures.
- dental-haven-data.xlsx: every table as a sheet, readable in Excel without the system (login secrets left out).
- README.txt: what is in the zip and how to restore it.
Server settings (/etc/dental-haven/env: secret key, email passwords) are not included; keep them separately.
"""
from __future__ import annotations

import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

PARTS = {"database": "Database (for restoring)", "files": "Uploaded files", "excel": "Excel copy (readable)"}
FOLDERS = (("UPLOAD_DIR", "patient-documents", "Patient files & photos"), ("PUBLIC_UPLOAD_DIR", "website-images", "Website images"))
SKIP_TABLES = {"sessions"}                       # logins in progress: useless in a backup
SKIP_COLUMNS = {("users", "password_hash")}      # never in the readable copy (it stays in the database for restoring)
CELL_MAX = 32000
STORED = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".zip", ".mp4", ".heic"}
KEEP_HOURS = 2                                    # a prepared backup can be downloaded for this long, then it's deleted
STALE_MINUTES = 45                                # a job still "preparing" after this long has died (e.g. server restart)                                  # Excel's limit per cell is 32,767 characters


def db_path(app) -> Path | None:
    url = app.config["DATABASE_URL"]
    return Path(url[len("sqlite:///"):]) if url.startswith("sqlite:///") else None


def _size(n: int) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024
    return ""


def folder_stats(root: Path) -> tuple[int, int]:
    files = [f for f in root.rglob("*") if f.is_file()] if root.exists() else []
    return len(files), sum(f.stat().st_size for f in files)


def inventory(app, conn) -> dict:
    """What a backup would contain: sizes, file counts and the main record counts."""
    p = db_path(app)
    folders = []
    for key, arc, label in FOLDERS:
        n, size = folder_stats(Path(app.config[key]))
        folders.append({"label": label, "files": n, "size": _size(size)})
    count = lambda t: conn.scalar(f"SELECT COUNT(*) FROM {t}") or 0  # noqa: E731
    records = [("Patients", count("patients")), ("Appointments", count("appointments")), ("Bills", count("invoices")),
               ("Payments", count("payments")), ("Progress notes", count("clinical_notes")), ("Lab cases", count("lab_cases")),
               ("Outside lab works", count("lab_works")), ("Expenses", count("expenses")), ("Staff accounts", count("users"))]
    tables = conn.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'") or 0
    last = conn.all("SELECT a.at, u.name FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id WHERE a.action = 'backup_downloaded' "
                    "ORDER BY a.id DESC LIMIT 5")
    return {"db_size": _size(p.stat().st_size) if p and p.exists() else "—", "folders": folders, "records": records, "tables": tables,
            "last": last, "sqlite": p is not None}


def snapshot(src: Path, dst: Path) -> None:
    """A consistent copy of the live database (safe while people are using the site)."""
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def excel_copy(db_file: Path, out: Path) -> int:
    """Every table as a sheet of one workbook. Returns the number of sheets."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(write_only=True)
    db = sqlite3.connect(db_file)
    names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    index = wb.create_sheet("Contents")
    index.append(["Sheet", "Table", "Rows"])
    sheets, used = [], set()
    for t in names:
        if t in SKIP_TABLES:
            continue
        cols = [r[1] for r in db.execute(f'PRAGMA table_info("{t}")') if (t, r[1]) not in SKIP_COLUMNS]
        title = t[:31]
        i = 2
        while title.lower() in used:
            title = f"{t[:28]}~{i}"
            i += 1
        used.add(title.lower())
        ws = wb.create_sheet(title)
        bold = []
        for c in cols:
            from openpyxl.cell import WriteOnlyCell
            cell = WriteOnlyCell(ws, value=c)
            cell.font = Font(bold=True)
            bold.append(cell)
        ws.append(bold)
        n = 0
        quoted = ", ".join(f'"{c}"' for c in cols)
        for row in db.execute(f'SELECT {quoted} FROM "{t}"'):
            ws.append([_cell(v) for v in row])
            n += 1
        sheets.append((title, t, n))
    for s in sheets:
        index.append(list(s))
    db.close()
    wb.save(out)
    return len(sheets)


def _cell(v):
    if isinstance(v, bytes):
        return f"[{len(v):,} bytes of data, in the database]"
    if isinstance(v, str):
        if v.startswith("data:image") and len(v) > 200:
            return "[signature / image, in the database]"
        v = "".join(ch for ch in v if ch in "\t\n\r" or ord(ch) >= 32)   # Excel refuses control characters
        if len(v) > CELL_MAX:
            return v[:CELL_MAX] + " …[cut: full text in the database]"
    return v


README = """DENTAL HAVEN BACKUP  ({stamp})
===================================

This zip contains ALL patient records. Keep it private: store it on an encrypted drive or
a private cloud folder only you can open, and delete old copies you no longer need.

What is inside
--------------
{contents}

How to restore
--------------
Easiest: log in as super admin, open Administration -> Backup & download -> Restore a backup,
and upload this zip. You see what's in it first; a safety copy of the current data is saved
before anything is replaced.

If the website itself won't open, restore it on the server instead:
1. Stop the site:            sudo systemctl stop dental-haven
2. Copy the database back:   sudo cp dental_haven.db /var/lib/dental-haven/dental_haven.db
3. Copy the files back:      sudo cp -r patient-documents/. /var/lib/dental-haven/uploads/
                             sudo cp -r website-images/.    /var/lib/dental-haven/public/
4. Give them to the app:     sudo chown -R dentalhaven: /var/lib/dental-haven
5. Start the site again:     sudo systemctl start dental-haven
(Folder names are those of the standard DigitalOcean setup; see docs/DEPLOY_DIGITALOCEAN.md.)

Not included
------------
- Server settings in /etc/dental-haven/env (secret key, email passwords). Keep a copy of that
  file separately and safely; without the same SECRET_KEY everyone simply has to log in again.
- The program code itself: that is in GitHub.
"""

PART_TEXT = {
    "database": "- dental_haven.db      the whole database: patients, charts, notes, appointments, bills, payments,\n"
                "                        lab cases and works, expenses, payroll, inventory, users, settings, audit trail.\n"
                "                        This is what a restore uses.",
    "files": "- patient-documents/    uploaded patient files and photos, lab case photos and other private files.\n"
             "- website-images/       pictures on the public website.",
    "excel": "- dental-haven-data.xlsx  the same data as a spreadsheet, one sheet per table (see the Contents sheet),\n"
             "                        to read without the system. Passwords are left out.",
}


def build(app, parts: set[str], workdir: Path) -> Path:
    """Make the backup zip in workdir and return its path."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    src = db_path(app)
    db_copy = workdir / "dental_haven.db"
    if "database" in parts or "excel" in parts:
        snapshot(src, db_copy)
    zpath = workdir / f"dental-haven-backup-{stamp}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        if "database" in parts:
            zf.write(db_copy, "dental_haven.db")
        if "excel" in parts:
            xl = workdir / "dental-haven-data.xlsx"
            excel_copy(db_copy, xl)
            zf.write(xl, xl.name)
        if "files" in parts:
            for key, arc, _ in FOLDERS:
                root = Path(app.config[key])
                if root.exists():
                    for f in root.rglob("*"):
                        if f.is_file():
                            packed = f.suffix.lower() in STORED      # photos and PDFs are already compressed
                            zf.write(f, f"{arc}/{f.relative_to(root)}", compress_type=zipfile.ZIP_STORED if packed else zipfile.ZIP_DEFLATED)
        zf.writestr("README.txt", README.format(stamp=stamp.replace("_", " "),
                                                contents="\n".join(PART_TEXT[p] for p in PARTS if p in parts)))
    return zpath


# --------------------------------------------------------------------------- background jobs
# A big backup takes longer than a web request may last, so it is prepared in a background thread. Its state lives in
# files (jobs/<id>/status.json), so any server worker can show it.

def jobs_dir(app) -> Path:
    d = Path(app.config["DATA_DIR"]) / "backup-jobs"
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def _status(d: Path) -> dict | None:
    import json
    try:
        return json.loads((d / "status.json").read_text())
    except (OSError, ValueError):
        return None


def _write(d: Path, st: dict) -> None:
    import json
    tmp = d / "status.tmp"
    tmp.write_text(json.dumps(st))
    tmp.replace(d / "status.json")


def jobs(app) -> list[dict]:
    """Recent backups (newest first); removes expired ones and marks dead ones as failed."""
    import shutil
    import time
    out = []
    for d in jobs_dir(app).iterdir():
        st = _status(d) if d.is_dir() else None
        if not st:
            if d.is_dir() and time.time() - d.stat().st_mtime > 3600:
                shutil.rmtree(d, ignore_errors=True)
            continue
        age = time.time() - st["started"]
        if age > KEEP_HOURS * 3600:
            shutil.rmtree(d, ignore_errors=True)
            continue
        if st["state"] == "preparing" and age > STALE_MINUTES * 60:
            st.update(state="failed", error="It stopped before finishing (the server may have restarted). Please try again.")
            _write(d, st)
        st["id"] = d.name
        st["expires_in"] = max(1, int((KEEP_HOURS * 3600 - age) // 60))
        out.append(st)
    return sorted(out, key=lambda s: -s["started"])


def start(app, parts: set[str], user_id: int) -> str:
    """Start preparing a backup; returns the job id. Runs at once (no thread) when testing."""
    import secrets
    import threading
    import time
    jid = secrets.token_hex(8)
    d = jobs_dir(app) / jid
    d.mkdir()
    _write(d, {"state": "preparing", "parts": sorted(parts), "started": time.time(), "user_id": user_id})

    def run():
        st = _status(d)
        try:
            z = build(app, parts, d)
            for f in d.iterdir():                   # keep only the zip and the status
                if f != z and f.name != "status.json":
                    f.unlink(missing_ok=True)
            st.update(state="ready", file=z.name, size=_size(z.stat().st_size), finished=time.time())
        except Exception:                           # noqa: BLE001
            app.logger.exception("Backup failed")
            st.update(state="failed", error="The backup couldn't be made. Check the server's free disk space and try again.")
        _write(d, st)

    if app.config.get("TESTING"):
        run()
    else:
        threading.Thread(target=run, name=f"backup-{jid}", daemon=True).start()
    return jid


def job_file(app, jid: str) -> Path | None:
    if not jid.isalnum():
        return None
    d = jobs_dir(app) / jid
    st = _status(d)
    if not st or st.get("state") != "ready":
        return None
    f = d / st["file"]
    return f if f.exists() else None


def remove(app, jid: str) -> None:
    import shutil
    if jid.isalnum():
        shutil.rmtree(jobs_dir(app) / jid, ignore_errors=True)

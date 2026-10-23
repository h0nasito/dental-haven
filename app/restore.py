"""Restore a backup made on the Backup & download page (super admins only).

Steps, each one safe to look at before the next:
1. Upload: the browser sends the zip in pieces (no size limit from the web server), into restore-jobs/<id>/backup.zip.
2. Check: the zip must hold a Dental Haven database that passes SQLite's own check and was made by this version of the
   system or an older one. The review page shows what's in it next to what's in the system now.
3. Restore (after typing RESTORE), in the background:
   a. a safety copy of the current database and files is saved first (restore-safety/, last 3 kept), so the
      restore itself can be undone from the same page;
   b. the database is copied in with SQLite's backup API (the site keeps running; other users simply see the
      restored data on their next page), then brought up to date with the migrations;
   c. optionally the uploaded files are replaced by those in the backup;
   d. everyone is logged out (logins come from the restored data).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path

from .backup import FOLDERS, build, db_path, snapshot

KEEP_SAFETY = 3
COUNTS = (("Patients", "patients"), ("Appointments", "appointments"), ("Bills", "invoices"), ("Payments", "payments"),
          ("Progress notes", "clinical_notes"), ("Lab cases", "lab_cases"), ("Outside lab works", "lab_works"),
          ("Expenses", "expenses"), ("Staff accounts", "users"))


def _dir(app, name: str) -> Path:
    d = Path(app.config["DATA_DIR"]) / name
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def jobs_dir(app) -> Path:
    return _dir(app, "restore-jobs")


def safety_dir(app) -> Path:
    return _dir(app, "restore-safety")


def job(app, jid: str) -> Path | None:
    if not jid or not jid.isalnum():
        return None
    d = jobs_dir(app) / jid
    return d if d.is_dir() else None


def status(d: Path) -> dict:
    try:
        return json.loads((d / "status.json").read_text())
    except (OSError, ValueError):
        return {}


def write(d: Path, st: dict) -> None:
    tmp = d / "status.tmp"
    tmp.write_text(json.dumps(st))
    tmp.replace(d / "status.json")


def new_upload(app, filename: str, user_id: int) -> str:
    import secrets
    cleanup(app)
    jid = secrets.token_hex(8)
    d = jobs_dir(app) / jid
    d.mkdir()
    (d / "backup.zip").write_bytes(b"")
    write(d, {"state": "uploading", "name": Path(filename or "backup.zip").name[:120], "started": time.time(), "user_id": user_id})
    return jid


def add_chunk(d: Path, offset: int, data: bytes) -> int:
    f = d / "backup.zip"
    if f.stat().st_size != offset:          # pieces must arrive in order
        raise ValueError("out of order")
    with f.open("ab") as fh:
        fh.write(data)
    return f.stat().st_size


def _counts(db: Path) -> dict:
    con = sqlite3.connect(db)
    out = {}
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for label, t in COUNTS:
            out[label] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] if t in tables else None
    finally:
        con.close()
    return out


def check(app, d: Path) -> dict:
    """Open the uploaded zip and decide whether it can be restored. Writes and returns the status."""
    from .migrate import MIGRATIONS_DIR
    st = status(d)
    z = d / "backup.zip"
    st.update(state="invalid", size=z.stat().st_size if z.exists() else 0)
    try:
        zf = zipfile.ZipFile(z)
    except (zipfile.BadZipFile, OSError):
        st["error"] = "This isn't a zip file. Choose the .zip you downloaded from Backup & download."
        write(d, st)
        return st
    with zf:
        names = zf.namelist()
        if "dental_haven.db" not in names:
            st["error"] = ("This zip has no database (dental_haven.db). Make the backup with “Database” ticked; "
                           "an Excel-only backup can't be restored.")
            write(d, st)
            return st
        bad = [n for n in names if n.startswith("/") or ".." in Path(n).parts]
        if bad:
            st["error"] = "This zip contains unsafe file paths, so it won't be used."
            write(d, st)
            return st
        with zf.open("dental_haven.db") as src, (d / "restore.db").open("wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
        files = {arc: sum(1 for n in names if n.startswith(arc + "/") and not n.endswith("/")) for _, arc, _ in FOLDERS}
        readme = zf.read("README.txt").decode("utf-8", "replace") if "README.txt" in names else ""
    try:
        con = sqlite3.connect(d / "restore.db")
        ok = con.execute("PRAGMA quick_check").fetchone()[0]
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        applied = {r[0] for r in con.execute("SELECT name FROM schema_migrations")} if "schema_migrations" in tables else set()
        last_activity = con.execute("SELECT MAX(at) FROM audit_log").fetchone()[0] if "audit_log" in tables else None
        con.close()
    except sqlite3.DatabaseError:
        ok, tables, applied, last_activity = "not a database", set(), set(), None
    if ok != "ok":
        st["error"] = "The database in this backup is damaged, so it can't be restored. Try another backup."
    elif not {"patients", "users", "schema_migrations"} <= tables:
        st["error"] = "This doesn't look like a Dental Haven database."
    else:
        ours = {p.name for p in MIGRATIONS_DIR.glob("*.sql") if not p.name.endswith(".postgres.sql")}
        newer = sorted(applied - ours)
        if newer:
            st["error"] = ("This backup was made by a newer version of the system. Update the system first "
                           "(dental-haven-update on the server), then restore it.")
        else:
            st.update(state="ready", backup_counts=_counts(d / "restore.db"), files=files, last_activity=last_activity,
                      made=_made(readme),
                      updates=len(ours - applied))
    if st["state"] != "ready":
        (d / "restore.db").unlink(missing_ok=True)
    write(d, st)
    return st


def _made(readme: str) -> str | None:
    """When the backup was made, from its README ("DENTAL HAVEN BACKUP  (2026-10-23 2307)"), as 2026-10-23 23:07:00."""
    import re
    m = re.search(r"DENTAL HAVEN BACKUP\s+\((\d{4}-\d{2}-\d{2}) (\d{2})(\d{2})\)", readme)
    return f"{m.group(1)} {m.group(2)}:{m.group(3)}:00" if m else None


def current_counts(app) -> dict:
    return _counts(db_path(app))


def start(app, d: Path, with_files: bool, user_id: int, user_name: str) -> None:
    import threading
    st = status(d)
    st.update(state="restoring", step="Saving a safety copy of the current data…", with_files=with_files, by=user_id, began=time.time())
    write(d, st)

    def run():
        try:
            _restore(app, d, with_files, user_name)
        except Exception as e:                           # noqa: BLE001
            app.logger.exception("Restore failed")
            s = status(d)
            s.update(state="failed", error=f"The restore stopped: {type(e).__name__}. If the data looks wrong, restore the safety copy below.")
            write(d, s)

    if app.config.get("TESTING"):
        run()
    else:
        threading.Thread(target=run, name=f"restore-{d.name}", daemon=True).start()


def _step(d: Path, text: str) -> None:
    s = status(d)
    s["step"] = text
    write(d, s)


def _restore(app, d: Path, with_files: bool, user_name: str) -> None:
    from .db import standalone_connection
    from .migrate import run_migrations
    from .util import now_str
    # a. safety copy of what's there now
    import secrets
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    sd = safety_dir(app) / f"before-restore-{stamp}-{secrets.token_hex(3)}"
    sd.mkdir()
    z = build(app, {"database", "files"}, sd)
    (sd / "dental_haven.db").unlink(missing_ok=True)
    safety = z.rename(sd / f"safety-copy-before-restore-{stamp}.zip")
    _prune_safety(app)
    # b. the database
    _step(d, "Restoring the database…")
    live = db_path(app)
    src = sqlite3.connect(d / "restore.db")
    dst = sqlite3.connect(live, timeout=60)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    _step(d, "Bringing the database up to date…")
    conn = standalone_connection(app.config["DATABASE_URL"])
    try:
        run_migrations(conn, verbose=False)
    finally:
        conn.raw.close()
    # c. the files
    if with_files:
        _step(d, "Restoring the uploaded files…")
        with zipfile.ZipFile(d / "backup.zip") as zf:
            for key, arc, _ in FOLDERS:
                members = [n for n in zf.namelist() if n.startswith(arc + "/") and not n.endswith("/")]
                if not members:
                    continue
                root = Path(app.config[key])
                for child in root.iterdir() if root.exists() else []:
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                root.mkdir(parents=True, exist_ok=True)
                for n in members:
                    target = (root / n[len(arc) + 1:]).resolve()
                    if root.resolve() not in target.parents:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(n) as s, target.open("wb") as t:
                        shutil.copyfileobj(s, t, 1024 * 1024)
    # d. log everyone out and record it in the restored audit trail
    conn = standalone_connection(app.config["DATABASE_URL"])
    try:
        with conn.transaction():
            conn.execute("DELETE FROM sessions")
            st = status(d)
            conn.execute("INSERT INTO audit_log (at, actor_id, action, entity_type, entity_id, branch_id, summary, details) "
                         "VALUES (?, NULL, 'backup_restored', 'settings', NULL, NULL, ?, ?)",
                         (now_str(), f"Backup restored by {user_name}: {st.get('name')}" + (" (with files)" if with_files else " (database only)"),
                          json.dumps({"safety_copy": safety.name, "backup_made": st.get("made")})))
    finally:
        conn.raw.close()
    (d / "restore.db").unlink(missing_ok=True)
    (d / "backup.zip").unlink(missing_ok=True)
    s = status(d)
    s.update(state="done", step="", safety=safety.parent.name, finished=time.time())
    write(d, s)


def _prune_safety(app) -> None:
    olds = sorted((p for p in safety_dir(app).iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
    for p in olds[KEEP_SAFETY:]:
        shutil.rmtree(p, ignore_errors=True)


def safety_copies(app) -> list[dict]:
    out = []
    for p in sorted((p for p in safety_dir(app).iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        z = next(p.glob("*.zip"), None)
        if z:
            from .backup import _size
            out.append({"id": p.name, "file": z.name, "size": _size(z.stat().st_size), "made": _when(p.name)})
    return out


def _when(name: str) -> str:
    """before-restore-2026-10-23_231935-ab12cd -> 2026-10-23 23:19:35"""
    t = name[len("before-restore-"):]
    return f"{t[:10]} {t[11:13]}:{t[13:15]}:{t[15:17]}"


def safety_file(app, sid: str) -> Path | None:
    if not sid.startswith("before-restore-") or "/" in sid or ".." in sid:
        return None
    d = safety_dir(app) / sid
    return next(d.glob("*.zip"), None) if d.is_dir() else None


def from_safety(app, sid: str, user_id: int) -> str | None:
    """Use a safety copy as the backup to restore (undo a restore). Returns the job id."""
    import secrets
    f = safety_file(app, sid)
    if not f:
        return None
    jid = secrets.token_hex(8)
    d = jobs_dir(app) / jid
    d.mkdir()
    shutil.copyfile(f, d / "backup.zip")
    write(d, {"state": "uploading", "name": f.name, "started": time.time(), "user_id": user_id})
    return jid


def cleanup(app) -> None:
    """Remove restore jobs older than a day (uploaded zips are big)."""
    for d in jobs_dir(app).iterdir():
        st = status(d)
        if st.get("state") == "restoring" and time.time() - st.get("began", 0) < 3 * 3600:
            continue
        if time.time() - d.stat().st_mtime > 86400:
            shutil.rmtree(d, ignore_errors=True)


def active(app) -> list[dict]:
    """Restore jobs to show on the page (uploaded and checked, restoring, finished in the last day)."""
    out = []
    for d in jobs_dir(app).iterdir():
        st = status(d)
        if st and st.get("state") != "uploading":
            st["id"] = d.name
            out.append(st)
    return sorted(out, key=lambda s: -s.get("started", 0))

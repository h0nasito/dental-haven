"""Import (and re-import) a MyMedsPH data export.

MyMedsPH exports a zip of CSV files: patients, progress_notes, treatment_plans, bills,
notes, prescriptions and certificates. This module reads that export and creates or
updates records in Dental Haven:

- patients.csv        -> patients + medical/dental history (matched by MyMedsPH PATIENT ID)
- progress_notes.csv  -> completed procedures (visit history); future follow-up dates -> follow-up tasks
- treatment_plans.csv -> one "Imported from MyMedsPH" treatment plan per patient
- notes -> clinical notes; prescriptions and certificates -> their own records
- bills.csv           -> billing history (kept separate; not counted in the new sales reports)

Importing the same export again is safe: patients are matched by their MyMedsPH ID and every
other row carries a fingerprint (legacy_key), so rows already imported are skipped.
Contact details are refreshed from the file; history fields are only filled when empty, so
anything staff edited in Dental Haven is kept.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import date, datetime

from .util import fmt_dt, now_str, today

MAX_ERRORS_SHOWN = 50

# Identify each file by its columns (file names can change).
SIGNATURES = {
    "patients": {"patient id", "birthday", "firstname", "lastname"},
    "progress_notes": {"patient_id", "recall_datetime", "service"},
    "treatment_plans": {"patient_id", "plan_procedure"},
    "bills": {"patient_id", "bill_dt", "total_amount"},
    "notes": {"patient id", "note"},
    "prescriptions": {"patient_id", "medicine", "dosage"},
    "certificates": {"patient id", "certificate"},
}
NAME_COLS = {"firstname", "middlename", "lastname"}


class ImportFileError(Exception):
    pass


class _DryRun(Exception):
    def __init__(self, summary):
        self.summary = summary


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_csv(data: bytes):
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    cols = [h.strip().lower() for h in header]
    rows = []
    for line_no, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        row = {cols[i]: (values[i].strip() if i < len(values) else "") for i in range(len(cols))}
        row["_line"] = line_no
        rows.append(row)
    return cols, rows


def read_export(files: list[tuple[str, bytes]]) -> dict:
    """files: [(filename, bytes)] - a MyMedsPH .zip and/or individual .csv files."""
    csvs: list[tuple[str, bytes]] = []
    for name, data in files:
        if name.lower().endswith(".zip") or data[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if info.is_dir() or not info.filename.lower().endswith(".csv"):
                            continue
                        if info.file_size > 200 * 1024 * 1024:
                            raise ImportFileError(f"{info.filename} is too large.")
                        csvs.append((info.filename.rsplit("/", 1)[-1], zf.read(info)))
            except zipfile.BadZipFile as exc:
                raise ImportFileError("The zip file could not be opened.") from exc
        elif name.lower().endswith(".csv"):
            csvs.append((name, data))
    found = {}
    for name, data in csvs:
        cols, rows = _read_csv(data)
        colset = set(cols)
        for kind, sig in SIGNATURES.items():
            if sig <= colset and kind not in found:
                found[kind] = {"file": name, "rows": rows}
                break
    if "patients" not in found:
        raise ImportFileError("No patients file found. Upload the MyMedsPH export zip (it must contain patients.csv).")
    return found


# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------

def _date(value: str):
    value = (value or "").strip()[:10]
    if not value or value.startswith("0000"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            d = datetime.strptime(value, fmt).date()
            return d if 1900 <= d.year <= today().year + 5 else None
        except ValueError:
            continue
    return None


def _time(value: str):
    value = (value or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def _cents(value: str) -> int:
    value = (value or "").replace(",", "").replace("₱", "").strip()
    try:
        return int(round(float(value) * 100))
    except ValueError:
        return 0


def _phone(value: str) -> str:
    value = (value or "").strip().lstrip("'").strip()
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) < 7:
        return ""
    if value.startswith("+"):
        return "+" + digits
    if len(digits) == 10 and digits.startswith("9"):
        return "0" + digits
    return digits


def _clean(value: str, limit=2000) -> str:
    value = (value or "").strip()
    return "" if value.lower() in ("none", "n/a", "na", "-", ".", "nothing", "no") else value[:limit]


def _labelled(pairs) -> str:
    return "\n".join(f"{label}: {val}" for label, val in pairs if val)


def _key(kind: str, row: dict) -> str:
    parts = [kind] + [f"{k}={row[k]}" for k in sorted(row) if k not in NAME_COLS and k != "_line"]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]


def _pid(row):
    return (row.get("patient id") or row.get("patient_id") or "").strip()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def run_import(conn, data: dict, *, branch_id: int, user_id: int, commit: bool) -> dict:
    """Import `data` (from read_export). With commit=False, everything is rolled back and only
    the summary is returned (preview)."""
    s = {k: 0 for k in ("patients_new", "patients_updated", "patients_unchanged", "procedures", "followups",
                        "plan_items", "notes", "bills", "skipped_existing", "rows_with_errors")}
    s["errors"] = []
    s["files"] = {k: {"file": v["file"], "rows": len(v["rows"])} for k, v in data.items()}

    def err(kind, row, msg):
        s["rows_with_errors"] += 1
        if len(s["errors"]) < MAX_ERRORS_SHOWN:
            s["errors"].append(f"{data[kind]['file']} line {row.get('_line')}: {msg}")

    try:
        with conn.transaction(immediate=True):
            ts = now_str()
            by_legacy = {r["legacy_id"]: r for r in conn.all("SELECT * FROM patients WHERE legacy_id IS NOT NULL")}
            hist = {r["patient_id"]: r for r in conn.all(
                "SELECT h.* FROM patient_history h JOIN patients p ON p.id = h.patient_id WHERE p.legacy_id IS NOT NULL")}

            # --- patients --------------------------------------------------
            for row in data["patients"]["rows"]:
                lid = _pid(row)
                first, last = _clean(row.get("firstname"), 80), _clean(row.get("lastname"), 80)
                if not lid or not (first or last):
                    err("patients", row, "missing patient ID or name - skipped")
                    continue
                gender = (row.get("gender") or "").lower()
                vals = {
                    "first_name": first or "-", "last_name": last or "-", "middle_name": _clean(row.get("middlename"), 80),
                    "birth_date": (_date(row.get("birthday")) or None) and _date(row.get("birthday")).isoformat(),
                    "sex": "female" if gender == "female" else "male" if gender == "male" else ("other" if gender else ""),
                    "phone": _phone(row.get("mobile")), "email": _clean(row.get("email"), 200).lower(),
                    "address": _clean(row.get("address"), 300), "occupation": _clean(row.get("occupation"), 120),
                    "civil_status": _clean(row.get("civil status"), 40).lower(),
                    "emergency_contact": _clean(row.get("person to contact"), 120),
                    "emergency_phone": _phone(row.get("emergency number")),
                }
                history = {
                    "medical_conditions": _labelled([("Condition", _clean(row.get("medical condition"))),
                                                     ("Previous hospitalization", _clean(row.get("previous hospitalization"))),
                                                     ("Medical concerns", _clean(row.get("medical concerns")))]),
                    "allergies": _clean(row.get("allegies") or row.get("allergies")),
                    "medications": _clean(row.get("medications")),
                    "dental_history": _labelled([("Consultation reason", _clean(row.get("consultation reason"))),
                                                 ("Dental experience", _clean(row.get("dental experience"))),
                                                 ("Brushing difficulty", _clean(row.get("brushing difficulty"))),
                                                 ("Fluoride", _clean(row.get("fluoride details"))),
                                                 ("Last recall", _clean(row.get("last recall")) if _date(row.get("last recall")) else ""),
                                                 ("Last recall summary", _clean(row.get("last recall summary")))]),
                    "other_notes": _labelled([("Family medical concerns", _clean(row.get("family medical concerns"))),
                                              ("Child diet", _clean(row.get("child diet"))), ("School", _clean(row.get("school"))),
                                              ("Father", ", ".join(x for x in (_clean(row.get("father's name")), _clean(row.get("father's occupation")),
                                                                                _phone(row.get("father's mobile"))) if x)),
                                              ("Mother", ", ".join(x for x in (_clean(row.get("mother's name")), _clean(row.get("mother's occupation")),
                                                                                _phone(row.get("mother's mobile"))) if x)),
                                              ("Physician", ", ".join(x for x in (_clean(row.get("physician")), _clean(row.get("physician contact"))) if x))]),
                }
                existing = by_legacy.get(lid)
                if existing is None:
                    pid = conn.insert("patients", {
                        **vals, "chart_no": f"MM-{lid}", "legacy_id": lid, "preferred_branch_id": branch_id,
                        "alert_flag": f"Allergy: {history['allergies']}"[:120] if history["allergies"] else "",
                        "consent_privacy": 0, "source": "mymedsph", "created_at": ts, "created_by": user_id, "updated_at": ts,
                    })
                    conn.execute("INSERT INTO patient_history (patient_id, medical_conditions, allergies, medications, dental_history, "
                                 "other_notes, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 (pid, history["medical_conditions"], history["allergies"], history["medications"],
                                  history["dental_history"], history["other_notes"], ts, user_id))
                    by_legacy[lid] = {"id": pid, **vals}
                    s["patients_new"] += 1
                else:
                    pid = existing["id"]
                    # refresh details that the file has; never blank out what Dental Haven already holds
                    upd = {k: v for k, v in vals.items() if v and v != existing.get(k)}
                    h = hist.get(pid)
                    hupd = {k: v for k, v in history.items() if v and h is not None and not (h.get(k) or "").strip()}
                    if upd:
                        upd["updated_at"] = ts
                        conn.update("patients", pid, upd)
                    if hupd:
                        conn.execute("UPDATE patient_history SET " + ", ".join(f"{k} = ?" for k in hupd) + ", updated_at = ?, updated_by = ? "
                                     "WHERE patient_id = ?", [*hupd.values(), ts, user_id, pid])
                    if h is None and any(history.values()):
                        conn.execute("INSERT INTO patient_history (patient_id, medical_conditions, allergies, medications, dental_history, "
                                     "other_notes, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                     (pid, history["medical_conditions"], history["allergies"], history["medications"],
                                      history["dental_history"], history["other_notes"], ts, user_id))
                    if upd or hupd:
                        s["patients_updated"] += 1
                    else:
                        s["patients_unchanged"] += 1

            pmap = {lid: r["id"] for lid, r in by_legacy.items()}
            pbranch = {r["id"]: r["preferred_branch_id"] for r in conn.all(
                "SELECT id, preferred_branch_id FROM patients WHERE legacy_id IS NOT NULL")}

            def keys(table):
                return {r["legacy_key"] for r in conn.all(f"SELECT legacy_key FROM {table} WHERE legacy_key IS NOT NULL")}

            def patient_of(kind, row):
                pid = pmap.get(_pid(row))
                if pid is None:
                    err(kind, row, "patient ID not found in patients file - skipped")
                return pid

            # --- visits / procedures + follow-ups -------------------------
            if "progress_notes" in data:
                seen, fseen = keys("procedures"), keys("follow_ups")
                proc_rows, fu_rows = [], []
                for row in data["progress_notes"]["rows"]:
                    pid = patient_of("progress_notes", row)
                    if pid is None:
                        continue
                    k = _key("progress", row)
                    d = _date(row.get("recall_datetime"))
                    if not d:
                        err("progress_notes", row, "invalid visit date - skipped")
                        continue
                    if k in seen:
                        s["skipped_existing"] += 1
                    else:
                        seen.add(k)
                        desc = _clean(row.get("service"), 250) or "Visit"
                        notes = "; ".join(x for x in (_clean(row.get("progress_notes"), 500), _clean(row.get("remarks"), 500)) if x)
                        if notes:
                            desc = f"{desc} - {notes}"[:1000]
                        proc_rows.append((pid, pbranch.get(pid), _clean(row.get("tooth_no"), 40), desc, d.isoformat(), ts, k))
                    fd = _date(row.get("followup_date"))
                    if fd and fd >= today():
                        fk = "fu-" + k
                        if fk not in fseen:
                            fseen.add(fk)
                            due = f"{fd.isoformat()} {_time(row.get('followup_time')) or '10:00'}"
                            reason = _clean(row.get("followup_reason"), 150) or f"Follow-up: {_clean(row.get('service'), 100) or 'visit'}"
                            fu_rows.append((pbranch.get(pid), pid, "other", reason, due, "open", ts, user_id, fk))
                if proc_rows:
                    conn.executemany("INSERT INTO procedures (patient_id, branch_id, tooth, description, status, performed_at, created_at, legacy_key) "
                                     "VALUES (?, ?, ?, ?, 'completed', ?, ?, ?)", proc_rows)
                if fu_rows:
                    conn.executemany("INSERT INTO follow_ups (branch_id, patient_id, kind, title, due_at, status, created_at, created_by, legacy_key) "
                                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", fu_rows)
                s["procedures"] += len(proc_rows)
                s["followups"] += len(fu_rows)

            # --- treatment plans --------------------------------------------
            if "treatment_plans" in data:
                seen = keys("treatment_plan_items")
                plans = {r["patient_id"]: r["id"] for r in conn.all(
                    "SELECT patient_id, id FROM treatment_plans WHERE title = 'Imported from MyMedsPH'")}
                for row in data["treatment_plans"]["rows"]:
                    pid = patient_of("treatment_plans", row)
                    if pid is None:
                        continue
                    k = _key("plan", row)
                    if k in seen:
                        s["skipped_existing"] += 1
                        continue
                    seen.add(k)
                    if pid not in plans:
                        plans[pid] = conn.insert("treatment_plans", {"patient_id": pid, "title": "Imported from MyMedsPH",
                                                                     "status": "presented", "notes": "Plan items imported from MyMedsPH.",
                                                                     "created_at": ts, "updated_at": ts})
                    d = _date(row.get("datetime"))
                    desc = _clean(row.get("plan_procedure"), 250) or "Planned procedure"
                    extra = "; ".join(x for x in (f"planned {d.isoformat()}" if d else "", _clean(row.get("remarks"), 300)) if x)
                    conn.insert("treatment_plan_items", {"plan_id": plans[pid], "tooth": _clean(row.get("tooth_no"), 40),
                                                         "description": f"{desc} ({extra})" if extra else desc,
                                                         "estimate_cents": _cents(row.get("cost")) or None, "status": "pending",
                                                         "seq": 0, "legacy_key": k})
                    s["plan_items"] += 1

            # --- notes -> clinical notes; prescriptions and certificates -> their own records ----
            seen = keys("clinical_notes")
            note_rows = []
            for row in data.get("notes", {}).get("rows", []):
                pid = patient_of("notes", row)
                if pid is None:
                    continue
                k = _key("notes", row)
                if k in seen:
                    s["skipped_existing"] += 1
                    continue
                seen.add(k)
                body = _clean(row.get("note"), 8000)
                if not body:
                    continue
                d = _date(row.get("date/time"))
                note_rows.append((pid, user_id, f"[Imported from MyMedsPH{', dated ' + d.isoformat() if d else ''}]\n{body}",
                                  f"{d.isoformat()} 00:00:00" if d else ts, k))
            if note_rows:
                conn.executemany("INSERT INTO clinical_notes (patient_id, author_id, body, created_at, legacy_key) VALUES (?, ?, ?, ?, ?)", note_rows)
            s["notes"] += len(note_rows)

            seen = keys("prescriptions")
            for row in data.get("prescriptions", {}).get("rows", []):
                pid = patient_of("prescriptions", row)
                if pid is None:
                    continue
                k = _key("prescriptions", row)
                if k in seen:
                    s["skipped_existing"] += 1
                    continue
                seen.add(k)
                med = _clean(row.get("medicine"), 200)
                if not med:
                    continue
                d = _date(row.get("prescribed_date")) or today()
                rx_id = conn.insert("prescriptions", {"patient_id": pid, "branch_id": pbranch.get(pid), "prescribed_on": d.isoformat(),
                                                      "notes": "Imported from MyMedsPH", "created_by": user_id, "created_at": ts, "legacy_key": k})
                conn.insert("prescription_items", {"prescription_id": rx_id, "medicine": med, "dosage": _clean(row.get("dosage"), 120),
                                                   "quantity": _clean(row.get("quantity"), 40), "instructions": _clean(row.get("remarks"), 300), "seq": 0})
                s["notes"] += 1

            seen = keys("certificates")
            for row in data.get("certificates", {}).get("rows", []):
                pid = patient_of("certificates", row)
                if pid is None:
                    continue
                k = _key("certificates", row)
                if k in seen:
                    s["skipped_existing"] += 1
                    continue
                seen.add(k)
                body = "; ".join(x for x in (_clean(row.get("certificate"), 5000), _clean(row.get("remarks"))) if x)
                if not body:
                    continue
                d = _date(row.get("date/time")) or today()
                conn.insert("certificates", {"patient_id": pid, "branch_id": pbranch.get(pid), "kind": "other",
                                             "title": "Certificate (imported from MyMedsPH)", "body": body, "issued_on": d.isoformat(),
                                             "created_by": user_id, "created_at": ts, "legacy_key": k})
                s["notes"] += 1

            # --- bills -> billing history -----------------------------------
            if "bills" in data:
                seen = keys("legacy_bills")
                bill_rows = []
                for row in data["bills"]["rows"]:
                    pid = patient_of("bills", row)
                    if pid is None:
                        continue
                    d = _date(row.get("bill_dt"))
                    if not d:
                        err("bills", row, "invalid bill date - skipped")
                        continue
                    k = _key("bill", row)
                    if k in seen:
                        s["skipped_existing"] += 1
                        continue
                    seen.add(k)
                    try:
                        qty = max(1, int(float(row.get("qty") or 1)))
                    except ValueError:
                        qty = 1
                    bill_rows.append((pid, d.isoformat(), _clean(row.get("service_type"), 250), _clean(row.get("item"), 250), qty,
                                      _cents(row.get("unit_price")), _cents(row.get("discount_amount")), _cents(row.get("total_amount")),
                                      (row.get("status") or "")[:20], _clean(row.get("remarks"), 500), k))
                if bill_rows:
                    conn.executemany("INSERT INTO legacy_bills (patient_id, bill_date, service, item, qty, unit_price_cents, discount_cents, "
                                     "total_cents, status_code, remarks, legacy_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", bill_rows)
                s["bills"] += len(bill_rows)

            if not commit:
                raise _DryRun(s)
    except _DryRun:
        pass
    return s

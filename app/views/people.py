"""Employees, compensation settings (restricted), daily time records and draft payroll review."""
from __future__ import annotations

import csv
import io
import re
from datetime import date as date_cls, timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, settings
from ..auth import require
from ..db import get_db
from ..attendance_rules import refresh_record
from ..payroll import BASIS_LABELS, build_lines, current_compensation, evaluate_record, parse_time, worked_minutes
from ..permissions import POSITIONS, branch_filter
from ..util import clean, now_str, parse_date, parse_money, peso, to_int, today
from .common import branches_for_user

bp = Blueprint("people", __name__, url_prefix="/staff")


@bp.app_context_processor
def _ctx():
    return {"BASIS_LABELS": BASIS_LABELS}


def _own_employee_id():
    row = get_db().one("SELECT id FROM employees WHERE user_id = ?", (g.user.id,))
    return row["id"] if row else None


def _employee_scope(alias="e"):
    if g.user.is_super_admin:
        return "1 = 1", []
    return branch_filter(g.user, f"{alias}.primary_branch_id", g.user.branch_ids)


# ---------------------------------------------------------------------------
# Employees & compensation
# ---------------------------------------------------------------------------

@bp.route("/employees", methods=["GET", "POST"])
@require("attendance.manage", "compensation.manage", any_of=True)
def employees():
    conn = get_db()
    if request.method == "POST":
        if not g.user.can("attendance.manage"):
            abort(403)
        name = clean(request.form.get("full_name"), 120)
        branch_id = to_int(request.form.get("primary_branch_id"))
        if not name or not branch_id or not g.user.in_branch(branch_id):
            flash("Enter a name and one of your branches.", "error")
        else:
            eid = conn.insert("employees", {"full_name": name, "position": clean(request.form.get("position"), 80) if clean(request.form.get("position"), 80) in POSITIONS else "Staff",
                                            "employment_type": request.form.get("employment_type", "regular"),
                                            "primary_branch_id": branch_id, "active": 1, "created_at": now_str()})
            audit.record("employee_created", "employee", eid, f"Added employee {name}", branch_id=branch_id)
            flash("Employee added. This does not create a login; only a super admin can create users.", "success")
        return redirect(url_for("people.employees"))
    scope, params = _employee_scope()
    rows = conn.all(f"SELECT e.*, b.name AS branch, u.email AS login_email, u.role, u.access_role FROM employees e LEFT JOIN branches b ON b.id = e.primary_branch_id "
                    f"LEFT JOIN users u ON u.id = e.user_id WHERE {scope} ORDER BY e.active DESC, e.full_name", params)
    if g.user.can("compensation.manage"):
        for r in rows:
            r["comp"] = current_compensation(conn, r["id"], today().isoformat())
    return render_template("staff/people/employees.html", rows=rows, branches=branches_for_user(g.user))


EMPLOYMENT_TYPES = {"regular": "regular", "probationary": "probationary", "probation": "probationary", "associate": "associate",
                    "associate dentist": "associate", "part-time": "part_time", "part time": "part_time", "parttime": "part_time",
                    "part_time": "part_time", "contractual": "contractual", "contract": "contractual", "": "regular"}
HEADERS = {"name": ("name", "full name", "employee", "employee name", "pangalan"),
           "position": ("position", "job title", "title", "designation", "role"),
           "branch": ("branch", "primary branch", "clinic", "assigned branch"),
           "type": ("type", "employment type", "employment status", "status"),
           "email": ("email", "e-mail", "email address", "work email")}


def normalize_position(text: str):
    """Map what people type ('Assistant', 'Technician (RPD)', 'Receptionist / Cashier') to a position in the list.
    With two jobs in one cell, the first one that matches is used."""
    from ..evaluation_content import ALIASES
    t = " ".join((text or "").lower().replace("–", "-").split())
    if "/" in t and not t.startswith("cad/cam"):
        for part in t.split("/"):
            hit = normalize_position(part)
            if hit:
                return hit
        return None
    for p in POSITIONS:
        if t == p.lower() or t in ALIASES.get(p.lower(), ()):
            return p
    extra = {"dentist": "Dentist", "assistant": "Dental Assistant", "dental asst": "Dental Assistant", "front desk": "Receptionist",
             "technician": "Technician", "lab technician": "Technician", "dental technician": "Technician"}
    return extra.get(t)


def _branch_lookup(conn):
    out = {}
    for b in conn.all("SELECT id, slug, name FROM branches"):
        for key in {b["slug"].lower(), b["name"].lower(), b["name"].split(" (")[0].lower()}:
            out[key] = b
    if "sjdm" in out:
        out.setdefault("san jose del monte", out["sjdm"])
    return out


def _import_rows(conn, table):
    """Check each row of the uploaded list. Returns rows with status 'new' / 'update' / 'same' / 'error'."""
    branches = _branch_lookup(conn)
    existing = {" ".join(e["full_name"].lower().split()): e for e in conn.all("SELECT * FROM employees WHERE active = 1")}
    users_by_name = {" ".join(u["name"].lower().split()): u["id"] for u in conn.all(
        "SELECT u.id, u.name FROM users u WHERE u.active = 1 AND NOT EXISTS (SELECT 1 FROM employees e WHERE e.user_id = u.id)")}
    out, seen = [], set()

    def col(row, key):
        for h in HEADERS[key]:
            if h in row:
                return (row.get(h) or "").strip()
        return ""

    for i, row in enumerate(table, start=2):
        name = " ".join(col(row, "name").split())[:120]
        if name and name == name.lower():
            name = " ".join(w[:1].upper() + w[1:] for w in name.split())   # "jamie lorenzo" -> "Jamie Lorenzo"
        pos_raw, br_raw, type_raw = col(row, "position"), col(row, "branch"), col(row, "type")
        email = col(row, "email").lower()[:200]
        r = {"line": i, "name": name, "position_raw": pos_raw, "branch_raw": br_raw, "position": None, "branch_id": None,
             "branch": "", "type": EMPLOYMENT_TYPES.get(type_raw.lower().strip()), "type_raw": type_raw, "email": email, "status": "new", "note": ""}
        if not name and not pos_raw and not br_raw:
            continue
        problems = []
        if not name:
            problems.append("no name")
        r["position"] = normalize_position(pos_raw)
        if r["position"] and "/" in pos_raw:
            r["note"] = f"“{pos_raw}” → {r['position']} (pick the access role when creating their login)"
        if not r["position"]:
            problems.append(f"unknown position “{pos_raw}”" if pos_raw else "no position")
        if br_raw:
            b = branches.get(br_raw.lower().strip())
            if not b:
                problems.append(f"unknown branch “{br_raw}”")
            elif not g.user.is_super_admin and not g.user.in_branch(b["id"]):
                problems.append(f"{b['name']} isn't one of your branches")
            else:
                r["branch_id"], r["branch"] = b["id"], b["name"]
        elif not g.user.is_super_admin:
            problems.append("no branch")
        if r["type"] is None:
            problems.append(f"unknown employment type “{type_raw}”")
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            problems.append(f"invalid email “{email}”")
        key = " ".join(name.lower().split())
        if key and key in seen:
            problems.append("listed twice")
        seen.add(key)
        if problems:
            r["status"], r["note"] = "error", "; ".join(problems)
        elif key not in existing and key in users_by_name:
            r["user_id"] = users_by_name[key]
            r["note"] = ((r["note"] + "; ") if r["note"] else "") + "linked to their existing login"
        elif key in existing:
            e = existing[key]
            changes = []
            if e["position"] != r["position"]:
                changes.append(f"position {e['position'] or '—'} → {r['position']}")
            if r["branch_id"] and e["primary_branch_id"] != r["branch_id"]:
                changes.append("branch → " + r["branch"])
            if type_raw and e["employment_type"] != r["type"]:
                changes.append(f"type → {r['type']}")
            if email and (e["email"] or "") != email:
                changes.append(f"email → {email}")
            r["employee_id"] = e["id"]
            r["status"], r["note"] = ("update", ", ".join(changes)) if changes else ("same", "already up to date")
        out.append(r)
    return out


@bp.route("/employees/import", methods=["GET", "POST"])
@require("attendance.manage")
def employees_import():
    """Add or update many employees at once from an Excel (.xlsx) or CSV list: Name, Position, Branch, (Type)."""
    import json
    from ..sheets import SheetError, read_table
    conn = get_db()
    rows, error = None, None
    if request.method == "POST" and request.form.get("action") == "preview":
        f = request.files.get("file")
        if not f or not f.filename:
            error = "Choose your Excel or CSV file first."
        else:
            data = f.read(5 * 1024 * 1024 + 1)
            if len(data) > 5 * 1024 * 1024:
                error = "The file is larger than 5 MB."
            else:
                try:
                    table = read_table(f.filename, data)
                    if not any(any(h in row for h in HEADERS["name"]) for row in table[:1]) and table:
                        raise SheetError("The first row must be the headings: Name, Position, Branch (and Type, optional).")
                    rows = _import_rows(conn, table)
                    if not rows:
                        error = "No employees found in the file."
                except SheetError as exc:
                    error = str(exc)
    elif request.method == "POST" and request.form.get("action") == "import":
        try:
            raw = json.loads(request.form.get("rows_json") or "[]")
        except ValueError:
            abort(400)
        table = [{"name": r.get("name", ""), "position": r.get("position_raw", ""), "branch": r.get("branch_raw", ""),
                  "type": r.get("type_raw", ""), "email": r.get("email", "")} for r in raw if isinstance(r, dict)][:2000]
        checked = _import_rows(conn, table)
        added = updated = 0
        with conn.transaction():
            for r in checked:
                if r["status"] == "new":
                    conn.insert("employees", {"full_name": r["name"], "position": r["position"], "employment_type": r["type"],
                                              "primary_branch_id": r["branch_id"], "email": r["email"], "active": 1, "created_at": now_str(),
                                              "user_id": r.get("user_id")})
                    added += 1
                elif r["status"] == "update":
                    upd = {"position": r["position"]}
                    if r["branch_id"]:
                        upd["primary_branch_id"] = r["branch_id"]
                    if r["type_raw"]:
                        upd["employment_type"] = r["type"]
                    if r["email"]:
                        upd["email"] = r["email"]
                    conn.update("employees", r["employee_id"], upd)
                    updated += 1
            audit.record("employees_imported", "employee", None, f"Imported employee list: {added} added, {updated} updated",
                         {"added": added, "updated": updated, "skipped": sum(1 for r in checked if r["status"] == "error")})
        flash(f"Done: {added} employee(s) added, {updated} updated. Logins are separate; only a super admin creates user accounts.", "success")
        return redirect(url_for("people.employees"))
    payload = None
    if rows:
        payload = json.dumps([{"name": r["name"], "position_raw": r["position_raw"], "branch_raw": r["branch_raw"], "type_raw": r["type_raw"],
                               "email": r["email"]}
                              for r in rows if r["status"] in ("new", "update")])
    return render_template("staff/people/employees_import.html", rows=rows, error=error, payload=payload, positions=POSITIONS,
                           branches=conn.all("SELECT name FROM branches ORDER BY sort_order, name"))


@bp.route("/employees/import/template.csv")
@require("attendance.manage")
def employees_import_template():
    body = ("Name,Position,Branch,Type,Email\r\nJuan Dela Cruz,Dental Assistant,Malolos,Regular,juan@example.com\r\n"
            "Maria Santos,Receptionist,Bocaue,Probationary,maria@example.com\r\n")
    return Response("\ufeff" + body, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=employee-list-template.csv"})


def _pct_bp(raw):
    """'40' or '40%' or '37.5' -> basis points (4000); None if not 0-100."""
    raw = (raw or "").strip().rstrip("%").strip()
    try:
        v = float(raw)
    except ValueError:
        return None
    return int(round(v * 100)) if 0 <= v <= 100 else None


@bp.route("/employees/<int:emp_id>", methods=["GET", "POST"])
@require("attendance.manage", "compensation.manage", any_of=True)
def employee(emp_id):
    conn = get_db()
    scope, params = _employee_scope()
    e = conn.one(f"SELECT e.*, b.name AS branch FROM employees e LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE e.id = ? AND {scope}",
                 [emp_id, *params])
    if not e:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "compensation":
            if not g.user.can("compensation.manage"):
                abort(403)
            basis = request.form.get("basis")
            rate = parse_money(request.form.get("rate"))
            pct = request.form.get("percentage")
            pct_bp = int(round(float(pct) * 100)) if pct and pct.replace(".", "", 1).isdigit() else None
            eff = parse_date(request.form.get("effective_from")) or today()
            if basis not in BASIS_LABELS:
                flash("Choose a pay basis.", "error")
            else:
                cid = conn.insert("compensation", {"employee_id": emp_id, "basis": basis, "rate_cents": rate, "percentage_bp": pct_bp,
                                                   "notes": clean(request.form.get("notes"), 500), "effective_from": eff.isoformat(),
                                                   "created_by": g.user.id, "created_at": now_str()})
                audit.record("compensation_set", "employee", emp_id, "Compensation setting added",
                             {"compensation_id": cid, "basis": basis, "effective_from": eff.isoformat()}, e["primary_branch_id"])
                flash("Compensation setting saved (effective-dated history is kept).", "success")
        elif action in ("dentist_pay", "service_rate"):
            if not g.user.can("compensation.manage"):
                abort(403)
            if action == "dentist_pay":
                daily = parse_money(request.form.get("daily_rate"))
                pct = _pct_bp(request.form.get("commission"))
                eff = parse_date(request.form.get("effective_from")) or today()
                if daily is None or daily < 0 or pct is None:
                    flash("Enter the daily rate (e.g. 1500) and the commission % (e.g. 40).", "error")
                else:
                    rid = conn.insert("dentist_pay_rates", {"employee_id": emp_id, "daily_rate_cents": daily, "commission_bp": pct,
                                                            "effective_from": eff.isoformat(), "notes": clean(request.form.get("notes"), 300),
                                                            "created_by": g.user.id, "created_at": now_str()})
                    audit.record("dentist_pay_set", "employee", emp_id, "Dentist daily rate and commission set",
                                 {"rate_id": rid, "effective_from": eff.isoformat()}, e["primary_branch_id"])
                    flash("Saved. Earlier rates are kept as history.", "success")
            else:
                svc = to_int(request.form.get("service_id"))
                raw = (request.form.get("commission") or "").strip()
                if not conn.one("SELECT id FROM services WHERE id = ?", (svc,)):
                    flash("Choose a service.", "error")
                elif raw == "":
                    conn.execute("DELETE FROM dentist_service_rates WHERE employee_id = ? AND service_id = ?", (emp_id, svc))
                    audit.record("dentist_service_rate_removed", "employee", emp_id, "Service commission rate removed", {"service_id": svc})
                    flash("Removed: this service uses the dentist's usual rate.", "success")
                elif _pct_bp(raw) is None:
                    flash("Enter the commission % from 0 to 100.", "error")
                else:
                    conn.execute("INSERT INTO dentist_service_rates (employee_id, service_id, commission_bp) VALUES (?, ?, ?) "
                                 "ON CONFLICT(employee_id, service_id) DO UPDATE SET commission_bp = excluded.commission_bp", (emp_id, svc, _pct_bp(raw)))
                    audit.record("dentist_service_rate_set", "employee", emp_id, "Service commission rate set", {"service_id": svc})
                    flash("Saved.", "success")
        elif action == "details":
            if not g.user.can("attendance.manage"):
                abort(403)
            branch_id = to_int(request.form.get("primary_branch_id"))
            if branch_id and not g.user.in_branch(branch_id):
                abort(403)
            pos = clean(request.form.get("position"), 80)
            if pos not in POSITIONS and pos != e["position"]:
                pos = e["position"]
            upd = {"position": pos, "employment_type": request.form.get("employment_type", "regular"),
                   "primary_branch_id": branch_id, "active": 1 if request.form.get("active") else 0}
            conn.update("employees", emp_id, upd)
            audit.record("employee_updated", "employee", emp_id, "Updated employee", audit.diff(dict(e), upd, upd.keys()), branch_id)
            flash("Employee updated.", "success")
        return redirect(url_for("people.employee", emp_id=emp_id))
    comps = conn.all("SELECT c.*, u.name AS by_name FROM compensation c LEFT JOIN users u ON u.id = c.created_by WHERE employee_id = ? "
                     "ORDER BY effective_from DESC, id DESC", (emp_id,)) if g.user.can("compensation.manage") else []
    user = conn.one("SELECT role FROM users WHERE id = ?", (e["user_id"],)) if e["user_id"] else None
    is_dentist = bool(user and user["role"] == "dentist")
    dpay = svc_rates = []
    if is_dentist and g.user.can("compensation.manage"):
        dpay = conn.all("SELECT r.*, u.name AS by_name FROM dentist_pay_rates r LEFT JOIN users u ON u.id = r.created_by WHERE employee_id = ? "
                        "ORDER BY effective_from DESC, id DESC", (emp_id,))
        svc_rates = conn.all("SELECT r.*, s.name AS service FROM dentist_service_rates r JOIN services s ON s.id = r.service_id WHERE employee_id = ? "
                             "ORDER BY s.sort_order", (emp_id,))
    return render_template("staff/people/employee.html", e=e, comps=comps, branches=branches_for_user(g.user), is_dentist=is_dentist,
                           dpay=dpay, svc_rates=svc_rates, all_services=conn.all("SELECT id, name FROM services WHERE active = 1 ORDER BY sort_order"),
                           today=today().isoformat())


# ---------------------------------------------------------------------------
# Attendance (DTR)
# ---------------------------------------------------------------------------

@bp.route("/attendance", methods=["GET"])
@require("attendance.view")
def attendance():
    conn = get_db()
    end = parse_date(request.args.get("to")) or today()
    start = parse_date(request.args.get("from")) or (end - timedelta(days=13))
    where, args = ["t.work_date BETWEEN ? AND ?"], [start.isoformat(), end.isoformat()]
    manage = g.user.can("attendance.manage")
    if manage:
        bf, bp_ = branch_filter(g.user, "t.branch_id")
        where.append(bf)
        args += bp_
    else:
        own = _own_employee_id()
        where.append("t.employee_id = ?")
        args.append(own or 0)
    status = request.args.get("status")
    if status in ("ok", "exception", "corrected", "excused"):
        where.append("t.status = ?")
        args.append(status)
    elif status == "field":
        where.append("t.field_status = 'pending'")
    elif status == "ot":
        where.append("t.ot_minutes > 0 AND t.ot_approved_minutes = 0")
    elif status == "late":
        where.append("t.late_minutes > 0")
    emp = to_int(request.args.get("employee"))
    if emp and manage:
        where.append("t.employee_id = ?")
        args.append(emp)
    rows = conn.all("SELECT t.*, e.full_name, b.name AS branch, u.name AS corrected_by_name FROM time_records t JOIN employees e ON e.id = t.employee_id "
                    "JOIN branches b ON b.id = t.branch_id LEFT JOIN users u ON u.id = t.corrected_by "
                    f"WHERE {' AND '.join(where)} ORDER BY t.work_date DESC, e.full_name LIMIT 500", args)
    for r in rows:
        r["minutes"] = worked_minutes(r)
    scope, params = _employee_scope()
    emps = conn.all(f"SELECT e.id, e.full_name, e.primary_branch_id FROM employees e WHERE e.active = 1 AND {scope} ORDER BY e.full_name", params) if manage else []
    warnings = []
    if manage:
        ws, wp = _employee_scope()
        warnings = conn.all(f"SELECT w.*, e.full_name FROM late_warnings w JOIN employees e ON e.id = w.employee_id WHERE {ws} "
                            "ORDER BY w.id DESC LIMIT 20", wp)
    return render_template("staff/people/attendance.html", rows=rows, start=start, end=end, status=status, emps=emps, emp=emp,
                           warnings=warnings, can_ot=g.user.can("overtime.approve"),
                           manage=manage, branches=branches_for_user(g.user), today=today().isoformat())


def _save_record(conn, emp_id, branch_id, work_date, time_in, time_out, source="manual"):
    rec = {"employee_id": emp_id, "branch_id": branch_id, "work_date": work_date, "time_in": time_in, "time_out": time_out, "status": "ok"}
    status, note = evaluate_record(conn, rec)
    existing = conn.one("SELECT * FROM time_records WHERE employee_id = ? AND work_date = ?", (emp_id, work_date))
    if existing:
        return None, existing
    rid = conn.insert("time_records", {**rec, "status": status, "exception_note": note, "source": source, "created_at": now_str()})
    refresh_record(conn, rid)
    return rid, None


@bp.route("/attendance/record", methods=["POST"])
@require("attendance.manage")
def attendance_record():
    conn = get_db()
    emp_id = to_int(request.form.get("employee_id"))
    scope, params = _employee_scope()
    emp = conn.one(f"SELECT * FROM employees e WHERE e.id = ? AND {scope}", [emp_id, *params])
    branch_id = to_int(request.form.get("branch_id")) or (emp["primary_branch_id"] if emp else None)
    d = parse_date(request.form.get("work_date"))
    tin, tout = parse_time(request.form.get("time_in")), parse_time(request.form.get("time_out"))
    if not emp or not d or not branch_id or not g.user.in_branch(branch_id) or d > today():
        flash("Choose an employee, one of your branches and a date that isn't in the future.", "error")
    else:
        rid, existing = _save_record(conn, emp_id, branch_id, d.isoformat(), tin, tout)
        if existing:
            flash("A record already exists for that date. Use Correct on the existing record.", "error")
        else:
            audit.record("dtr_recorded", "time_record", rid, f"DTR {emp['full_name']} {d.isoformat()}", branch_id=branch_id)
            flash("Time record saved.", "success")
    return redirect(url_for("people.attendance"))


@bp.route("/attendance/<int:rec_id>/overtime", methods=["POST"])
@require("overtime.approve")
def attendance_overtime(rec_id):
    conn = get_db()
    r = conn.one("SELECT t.*, e.full_name FROM time_records t JOIN employees e ON e.id = t.employee_id WHERE t.id = ?", (rec_id,))
    if not r or not g.user.in_branch(r["branch_id"]):
        abort(404)
    minutes = to_int(request.form.get("minutes"))
    note = clean(request.form.get("note"), 200)
    if minutes is None or minutes < 0 or minutes > r["ot_minutes"]:
        flash(f"Approve between 0 and {r['ot_minutes']} minutes (the time after closing).", "error")
    else:
        conn.execute("UPDATE time_records SET ot_approved_minutes = ?, ot_approved_by = ?, ot_approved_at = ?, ot_note = ? WHERE id = ?",
                     (minutes, g.user.id, now_str(), note, rec_id))
        audit.record("overtime_approved", "time_record", rec_id, f"Overtime {minutes} min approved for {r['full_name']} {r['work_date']}",
                     {"note": note}, r["branch_id"])
        flash("Overtime saved." if minutes else "Overtime not approved.", "success")
    return redirect(request.referrer if (request.referrer or "").startswith(request.host_url) else url_for("people.attendance"))


@bp.route("/attendance/import", methods=["POST"])
@require("attendance.manage")
def attendance_import():
    """CSV columns: employee (name or email), date (YYYY-MM-DD), time_in, time_out, branch (optional name)."""
    conn = get_db()
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a CSV file.", "error")
        return redirect(url_for("people.attendance"))
    try:
        text = file.stream.read(2_000_000).decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("The file must be a UTF-8 CSV.", "error")
        return redirect(url_for("people.attendance"))
    scope, params = _employee_scope()
    emps = conn.all(f"SELECT e.*, COALESCE(u.email, e.email) AS login_email FROM employees e LEFT JOIN users u ON u.id = e.user_id "
                    f"WHERE e.active = 1 AND {scope}", params)
    by_key = {}
    for e in emps:
        by_key[e["full_name"].strip().lower()] = e
        if e["login_email"]:
            by_key[e["login_email"].lower()] = e
    branches = {b["name"].lower(): b["id"] for b in branches_for_user(g.user)}
    added, skipped, errors = 0, 0, []
    with conn.transaction():
        for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            e = by_key.get(row.get("employee", "").lower())
            d = parse_date(row.get("date"))
            branch_id = branches.get(row.get("branch", "").lower()) if row.get("branch") else (e["primary_branch_id"] if e else None)
            if not e or not d or not branch_id or d > today():
                errors.append(f"Line {i}: unknown employee/branch or bad date")
                continue
            rid, existing = _save_record(conn, e["id"], branch_id, d.isoformat(), parse_time(row.get("time_in")),
                                         parse_time(row.get("time_out")), source="import")
            if existing:
                skipped += 1
            else:
                added += 1
        audit.record("dtr_imported", "time_record", None, f"Imported {added} DTR rows ({skipped} duplicates skipped, {len(errors)} errors)")
    msg = f"Imported {added} records; {skipped} already existed."
    if errors:
        msg += " Problems: " + "; ".join(errors[:5]) + ("…" if len(errors) > 5 else "")
    flash(msg, "warning" if errors else "success")
    return redirect(url_for("people.attendance", status="exception"))


@bp.route("/attendance/<int:rec_id>/correct", methods=["GET", "POST"])
@require("attendance.manage")
def attendance_correct(rec_id):
    conn = get_db()
    r = conn.one("SELECT t.*, e.full_name FROM time_records t JOIN employees e ON e.id = t.employee_id WHERE t.id = ?", (rec_id,))
    if not r or not g.user.in_branch(r["branch_id"]):
        abort(404)
    locked = conn.one("SELECT id FROM payroll_periods WHERE status = 'approved' AND ? BETWEEN start_date AND end_date "
                      "AND (branch_id IS NULL OR branch_id = ?)", (r["work_date"], r["branch_id"]))
    if request.method == "POST":
        if locked:
            flash("This date is in an approved payroll period and is locked.", "error")
            return redirect(url_for("people.attendance"))
        reason = clean(request.form.get("reason"), 300)
        action = request.form.get("action")
        if not reason:
            flash("A reason is required for every correction.", "error")
            return redirect(url_for("people.attendance_correct", rec_id=rec_id))
        before = {"time_in": r["time_in"], "time_out": r["time_out"], "status": r["status"]}
        if action == "excuse":
            upd = {"status": "excused"}
        else:
            upd = {"time_in": parse_time(request.form.get("time_in")), "time_out": parse_time(request.form.get("time_out")), "status": "corrected"}
        upd.update({"correction_reason": reason, "corrected_by": g.user.id, "corrected_at": now_str()})
        conn.update("time_records", rec_id, upd)
        refresh_record(conn, rec_id)
        audit.record("dtr_corrected", "time_record", rec_id, f"Corrected DTR {r['full_name']} {r['work_date']}",
                     {"before": before, "after": {k: upd.get(k) for k in before}, "reason": reason}, r["branch_id"])
        flash("Correction saved with an audit record.", "success")
        return redirect(url_for("people.attendance"))
    history = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id WHERE entity_type = 'time_record' "
                       "AND entity_id = ? ORDER BY a.id DESC", (rec_id,))
    return render_template("staff/people/attendance_correct.html", r=r, history=history, locked=locked)


# ---------------------------------------------------------------------------
# Payroll review (draft → submitted → approved). No payments are made.
# ---------------------------------------------------------------------------

FIXED_REGULAR = [("01-01", "New Year's Day"), ("04-09", "Araw ng Kagitingan"), ("05-01", "Labor Day"), ("06-12", "Independence Day"),
                 ("11-30", "Bonifacio Day"), ("12-25", "Christmas Day"), ("12-30", "Rizal Day")]


@bp.route("/holidays", methods=["GET", "POST"])
@require("attendance.manage")
def holidays():
    import calendar
    conn = get_db()
    year = to_int(request.values.get("year")) or today().year
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            d = parse_date(request.form.get("day"))
            name = clean(request.form.get("name"), 80)
            kind = request.form.get("kind")
            if not d or len(name) < 2 or kind not in ("regular", "special"):
                flash("Enter the date, the holiday name and its type.", "error")
            elif conn.one("SELECT id FROM holidays WHERE day = ?", (d.isoformat(),)):
                flash("That date is already a holiday.", "error")
            else:
                conn.insert("holidays", {"day": d.isoformat(), "name": name, "kind": kind, "created_by": g.user.id, "created_at": now_str()})
                audit.record("holiday_added", "holiday", None, f"Holiday {d.isoformat()} {name} ({kind})")
                flash("Holiday added.", "success")
            year = d.year if d else year
        elif action == "delete":
            h = conn.one("SELECT * FROM holidays WHERE id = ?", (to_int(request.form.get("holiday_id")),))
            if h:
                conn.execute("DELETE FROM holidays WHERE id = ?", (h["id"],))
                audit.record("holiday_removed", "holiday", h["id"], f"Removed holiday {h['day']} {h['name']}")
                flash("Holiday removed.", "success")
        elif action == "fixed":
            last_monday_aug = max(d for d in (date_cls(year, 8, day) for day in range(1, 32)) if d.weekday() == 0)
            added = 0
            for mmdd, name in FIXED_REGULAR + [(last_monday_aug.strftime("%m-%d"), "National Heroes Day")]:
                day = f"{year}-{mmdd}"
                if not conn.one("SELECT id FROM holidays WHERE day = ?", (day,)):
                    conn.insert("holidays", {"day": day, "name": name, "kind": "regular", "created_by": g.user.id, "created_at": now_str()})
                    added += 1
            audit.record("holiday_added", "holiday", None, f"Added {added} fixed-date regular holidays for {year}")
            flash(f"Added {added} fixed-date regular holidays for {year}. Add Holy Week, Eid and special non-working days from this year's proclamation.",
                  "success")
        return redirect(url_for("people.holidays", year=year))
    rows = conn.all("SELECT * FROM holidays WHERE day LIKE ? ORDER BY day", (f"{year}-%",))
    return render_template("staff/people/holidays.html", rows=rows, year=year)


@bp.route("/payroll", methods=["GET", "POST"])
@require("payroll.prepare", "payroll.approve", any_of=True)
def payroll():
    conn = get_db()
    if request.method == "POST":
        if not g.user.can("payroll.prepare"):
            abort(403)
        s, e = parse_date(request.form.get("start_date")), parse_date(request.form.get("end_date"))
        branch_id = to_int(request.form.get("branch_id"))
        name = clean(request.form.get("name"), 80)
        if not s or not e or e < s or (e - s).days > 62:
            flash("Enter a valid period of up to two months.", "error")
        elif branch_id and not g.user.in_branch(branch_id):
            abort(403)
        else:
            pid = conn.insert("payroll_periods", {"name": name or f"{s.isoformat()} to {e.isoformat()}", "start_date": s.isoformat(),
                                                  "end_date": e.isoformat(), "branch_id": branch_id, "status": "draft",
                                                  "rules_confirmed": 1 if settings.get("payroll.rules_confirmed") else 0,
                                                  "created_by": g.user.id, "created_at": now_str()})
            _rebuild(conn, pid)
            audit.record("payroll_period_created", "payroll_period", pid, f"Draft payroll {s} – {e}", branch_id=branch_id)
            return redirect(url_for("people.payroll_period", period_id=pid))
    periods = conn.all("SELECT p.*, b.name AS branch, u.name AS creator FROM payroll_periods p LEFT JOIN branches b ON b.id = p.branch_id "
                       "LEFT JOIN users u ON u.id = p.created_by ORDER BY p.start_date DESC")
    periods = [p for p in periods if g.user.is_super_admin or p["branch_id"] in g.user.branch_ids]
    t = today()
    default_start, cutoff_end = cutoff_for(t)
    return render_template("staff/people/payroll.html", periods=periods, branches=branches_for_user(g.user),
                           rules_confirmed=settings.get("payroll.rules_confirmed"), default_start=default_start.isoformat(),
                           default_end=cutoff_end.isoformat(), prev_cutoff=cutoff_for(default_start - timedelta(days=1)))


def cutoff_for(d):
    """The clinic's pay cutoffs: 1st-15th and 16th-end of month."""
    import calendar
    if d.day <= 15:
        return d.replace(day=1), d.replace(day=15)
    return d.replace(day=16), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _rebuild(conn, period_id):
    period = conn.one("SELECT * FROM payroll_periods WHERE id = ?", (period_id,))
    old = {r["employee_id"]: r for r in conn.all("SELECT * FROM payroll_lines WHERE period_id = ?", (period_id,))}
    with conn.transaction():
        conn.execute("DELETE FROM payroll_lines WHERE period_id = ?", (period_id,))
        for line in build_lines(conn, period):
            prev = old.get(line["employee_id"])
            conn.insert("payroll_lines", {"period_id": period_id, **line,
                                          "adjustment_cents": prev["adjustment_cents"] if prev else 0,
                                          "adjustment_note": prev["adjustment_note"] if prev else ""})


def _load_period(period_id):
    p = get_db().one("SELECT p.*, b.name AS branch, c.name AS creator, s.name AS submitter, a.name AS approver FROM payroll_periods p "
                     "LEFT JOIN branches b ON b.id = p.branch_id LEFT JOIN users c ON c.id = p.created_by LEFT JOIN users s ON s.id = p.submitted_by "
                     "LEFT JOIN users a ON a.id = p.approved_by WHERE p.id = ?", (period_id,))
    if not p:
        abort(404)
    if p["branch_id"] and not g.user.in_branch(p["branch_id"]):
        abort(403)
    if not p["branch_id"] and not g.user.is_super_admin:
        active = {r["id"] for r in get_db().all("SELECT id FROM branches WHERE active = 1")}
        if not active.issubset(set(g.user.branch_ids)):
            abort(403)  # all-branch periods are only for users who cover every branch
    return p


@bp.route("/payroll/<int:period_id>", methods=["GET", "POST"])
@require("payroll.prepare", "payroll.approve", any_of=True)
def payroll_period(period_id):
    conn = get_db()
    p = _load_period(period_id)
    rules_confirmed = bool(settings.get("payroll.rules_confirmed"))
    if request.method == "POST":
        action = request.form.get("action")
        if action in ("rebuild", "adjust", "submit") and not g.user.can("payroll.prepare"):
            abort(403)
        if action in ("rebuild", "adjust") and p["status"] != "draft":
            flash("Only draft periods can be changed. Return it to draft first.", "error")
        elif action == "rebuild":
            _rebuild(conn, period_id)
            audit.record("payroll_recalculated", "payroll_period", period_id, "Recalculated from DTR")
            flash("Recalculated from time records.", "success")
        elif action == "adjust":
            line_id = to_int(request.form.get("line_id"))
            raw = (request.form.get("adjustment") or "").strip()
            neg = raw.startswith("-")
            amt = parse_money(raw.lstrip("-")) if raw else 0
            note = clean(request.form.get("adjustment_note"), 200)
            if amt is None or (amt and not note):
                flash("Enter an amount like 500 or -250 and a reason.", "error")
            else:
                amt = -amt if neg else amt
                conn.execute("UPDATE payroll_lines SET adjustment_cents = ?, adjustment_note = ? WHERE id = ? AND period_id = ?",
                             (amt, note, line_id, period_id))
                audit.record("payroll_adjusted", "payroll_period", period_id, f"Adjustment {peso(amt)}", {"line_id": line_id, "note": note})
                flash("Adjustment saved.", "success")
        elif action == "submit" and p["status"] == "draft":
            conn.execute("UPDATE payroll_periods SET status='submitted', submitted_by=?, submitted_at=? WHERE id=?", (g.user.id, now_str(), period_id))
            audit.record("payroll_submitted", "payroll_period", period_id, "Submitted for approval")
            flash("Submitted for approval.", "success")
        elif action == "return" and p["status"] == "submitted" and (g.user.can("payroll.approve") or p["submitted_by"] == g.user.id):
            conn.execute("UPDATE payroll_periods SET status='draft' WHERE id=?", (period_id,))
            audit.record("payroll_returned", "payroll_period", period_id, clean(request.form.get("note"), 300) or "Returned to draft")
            flash("Returned to draft.", "success")
        elif action == "approve" and p["status"] == "submitted":
            if not g.user.can("payroll.approve"):
                abort(403)
            open_exc = conn.scalar("SELECT COALESCE(SUM(open_exceptions),0) FROM payroll_lines WHERE period_id = ?", (period_id,))
            if not rules_confirmed:
                flash("Can't approve: the clinic's pay rules aren't confirmed yet (System settings). These figures are only an estimate.", "error")
            elif open_exc:
                flash(f"Can't approve: {open_exc} attendance exceptions are still unresolved.", "error")
            elif p["submitted_by"] == g.user.id:
                flash("A different person must approve than the one who submitted.", "error")
            else:
                conn.execute("UPDATE payroll_periods SET status='approved', approved_by=?, approved_at=?, rules_confirmed=1 WHERE id=?",
                             (g.user.id, now_str(), period_id))
                audit.record("payroll_approved", "payroll_period", period_id, "Approved payroll summary (no payment made)")
                flash("Payroll summary approved. Payments are still made outside this system.", "success")
        elif action == "cancel" and p["status"] in ("draft", "submitted") and g.user.can("payroll.prepare"):
            conn.execute("UPDATE payroll_periods SET status='cancelled' WHERE id=?", (period_id,))
            audit.record("payroll_cancelled", "payroll_period", period_id, "Cancelled")
        return redirect(url_for("people.payroll_period", period_id=period_id))
    lines = conn.all("SELECT l.*, e.full_name, e.position FROM payroll_lines l JOIN employees e ON e.id = l.employee_id "
                     "WHERE l.period_id = ? ORDER BY e.full_name", (period_id,))
    history = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                       "WHERE entity_type = 'payroll_period' AND entity_id = ? ORDER BY a.id DESC", (period_id,))
    return render_template("staff/people/payroll_period.html", p=p, lines=lines, history=history, rules_confirmed=rules_confirmed,
                           late_rate=settings.get("payroll.late_peso_per_minute", conn), pay_unworked=settings.get("payroll.pay_unworked_regular_holiday", conn),
                           show_money=g.user.can("compensation.manage"))


@bp.route("/payroll/<int:period_id>/dentist/<int:emp_id>")
@require("payroll.prepare", "payroll.approve", any_of=True)
def payroll_commission(period_id, emp_id):
    """The procedures behind a dentist's commission for the period."""
    from ..payroll import commission_items, dentist_rates, manual_commissions, per_procedure
    conn = get_db()
    p = _load_period(period_id)
    e = conn.one("SELECT e.*, u.name AS user_name FROM employees e JOIN users u ON u.id = e.user_id WHERE e.id = ? AND u.role = 'dentist'", (emp_id,))
    if not e:
        abort(404)
    rates = dentist_rates(conn, e["id"], p["end_date"])
    svc = {r["service_id"]: r["commission_bp"] for r in conn.all("SELECT * FROM dentist_service_rates WHERE employee_id = ?", (e["id"],))}
    by_procedure = per_procedure(conn)
    items = commission_items(conn, e["user_id"], p["start_date"], p["end_date"], p["branch_id"], rates["commission_bp"] if rates else 0, svc) \
        if by_procedure else []
    manual = manual_commissions(conn, e["id"], p["start_date"], p["end_date"])
    line = conn.one("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (period_id, emp_id))
    return render_template("staff/people/payroll_commission.html", p=p, e=e, items=items, manual=manual, rates=rates, line=line,
                           by_procedure=by_procedure,
                           total=sum(i["commission_cents"] for i in items) + sum(m["amount_cents"] for m in manual),
                           show_money=g.user.can("compensation.manage"), today=today().isoformat())


@bp.route("/payroll/<int:period_id>/dentist/<int:emp_id>/manual", methods=["POST"])
@require("payroll.prepare")
def payroll_commission_manual(period_id, emp_id):
    """Manual commission not tied to a bill line (e.g. an agreed amount), or remove one."""
    from ..payroll import add_manual_commission
    from .billing import pct_to_bp
    conn = get_db()
    p = _load_period(period_id)
    if p["status"] != "draft":
        flash("This payroll period is no longer a draft.", "error")
        return redirect(url_for("people.payroll_commission", period_id=period_id, emp_id=emp_id))
    e = conn.one("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE e.id = ? AND u.role = 'dentist'", (emp_id,))
    if not e:
        abort(404)
    back = redirect(url_for("people.payroll_commission", period_id=period_id, emp_id=emp_id))
    if request.form.get("action") == "void":
        c = conn.one("SELECT * FROM dentist_commissions WHERE id = ? AND employee_id = ? AND status = 'valid'",
                     (to_int(request.form.get("commission_id")), emp_id))
        if not c:
            abort(404)
        conn.execute("UPDATE dentist_commissions SET status = 'void', voided_by = ?, voided_at = ? WHERE id = ?", (g.user.id, now_str(), c["id"]))
        audit.record("dentist_commission_voided", "employee", emp_id, f"Removed manual commission {peso(c['amount_cents'])}", {"commission_id": c["id"]})
        flash("Commission removed. Use Recalculate from DTR on the period page to update the totals.", "success")
        return back
    earned = parse_date(request.form.get("earned_on"))
    amt_txt, base_txt, pct_txt = ((request.form.get(k) or "").strip() for k in ("amount", "base", "pct"))
    amount = parse_money(amt_txt) if amt_txt else None
    base = parse_money(base_txt) if base_txt else None
    bp = pct_to_bp(pct_txt) if pct_txt else None
    desc = clean(request.form.get("description"), 200)
    if not earned or not (p["start_date"] <= earned.isoformat() <= p["end_date"]):
        flash("The date must be inside this payroll period.", "error")
        return back
    if (amt_txt and amount is None) or (base_txt and base is None) or (pct_txt and bp is None) or not desc:
        flash("Enter what it's for, and the amount (or the base and %).", "error")
        return back
    cid, err = add_manual_commission(conn, None, emp_id, earned, base, bp, amount, g.user.id, description=desc)
    if err:
        flash(err, "error")
        return back
    audit.record("dentist_commission_added", "employee", emp_id, f"Manual commission for {earned.isoformat()}: {desc}", {"commission_id": cid})
    flash("Commission added. Use Recalculate from DTR on the period page to update the totals.", "success")
    return back


@bp.route("/payroll/<int:period_id>/technician/<int:emp_id>")
@require("payroll.prepare", "payroll.approve", any_of=True)
def payroll_tech_commission(period_id, emp_id):
    from ..lab_commission import for_period
    conn = get_db()
    p = _load_period(period_id)
    e = conn.one("SELECT * FROM employees WHERE id = ?", (emp_id,))
    if not e:
        abort(404)
    items = for_period(conn, emp_id, p["start_date"], p["end_date"])
    return render_template("staff/people/payroll_tech.html", p=p, e=e, items=items, show_money=g.user.can("compensation.manage"))


@bp.route("/payroll/<int:period_id>/export.csv")
@require("payroll.prepare", "payroll.approve", any_of=True)
def payroll_export(period_id):
    conn = get_db()
    p = _load_period(period_id)
    lines = conn.all("SELECT l.*, e.full_name, e.position FROM payroll_lines l JOIN employees e ON e.id = l.employee_id WHERE l.period_id = ? "
                     "ORDER BY l.kind DESC, e.full_name", (period_id,))
    show_money = g.user.can("compensation.manage")
    buf = io.StringIO()
    w = csv.writer(buf)
    label = "APPROVED SUMMARY (not a payment instruction)" if p["status"] == "approved" else "DRAFT — UNCONFIRMED ESTIMATE, NOT FINAL PAYROLL"
    w.writerow([f"Dental Haven payroll review: {p['name']} ({p['start_date']} to {p['end_date']})", label])
    header = ["Employee", "Position", "Group", "Days present", "Hours worked", "Late (min)", "Undertime (min)", "Open exceptions", "Pay basis",
              "Procedures done"]
    if show_money:
        header += ["Rate (PHP)", "Commission %", "Daily pay (PHP)", "Commission base (PHP)", "Commission (PHP)", "Estimate (PHP)",
                   "Adjustment (PHP)", "Adjustment note"]
    w.writerow(header)
    for l in lines:
        dent = l["kind"] == "dentist"
        row = [l["full_name"], l["position"], "Dentist" if dent else "Staff", l["days_present"], round(l["minutes_worked"] / 60, 2), l["late_minutes"],
               l["undertime_minutes"], l["open_exceptions"], BASIS_LABELS.get(l["basis"], l["basis"]), l["commission_items"] if dent else ""]
        if show_money:
            row += [(l["rate_cents"] or 0) / 100 if l["rate_cents"] is not None else "", (l["percentage_bp"] or 0) / 100 if dent else "",
                    (l["daily_pay_cents"] or 0) / 100 if dent and l["daily_pay_cents"] is not None else "",
                    (l["commission_base_cents"] or 0) / 100 if dent else "", (l["commission_cents"] or 0) / 100 if l["commission_cents"] is not None else "",
                    l["estimate_cents"] / 100 if l["estimate_cents"] is not None else "needs pay rule",
                    l["adjustment_cents"] / 100, l["adjustment_note"]]
        w.writerow(row)
    audit.record("payroll_exported", "payroll_period", period_id, "Exported payroll CSV")
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="payroll-{p["start_date"]}-{p["end_date"]}.csv"',
                             "Cache-Control": "no-store"})

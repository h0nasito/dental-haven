"""Employees, compensation settings (restricted), daily time records and draft payroll review."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, settings
from ..auth import require
from ..db import get_db
from ..payroll import BASIS_LABELS, build_lines, current_compensation, evaluate_record, parse_time, worked_minutes
from ..permissions import branch_filter
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
            eid = conn.insert("employees", {"full_name": name, "position": clean(request.form.get("position"), 80),
                                            "employment_type": request.form.get("employment_type", "regular"),
                                            "primary_branch_id": branch_id, "active": 1, "created_at": now_str()})
            audit.record("employee_created", "employee", eid, f"Added employee {name}", branch_id=branch_id)
            flash("Employee added. This does not create a login; only a super admin can create users.", "success")
        return redirect(url_for("people.employees"))
    scope, params = _employee_scope()
    rows = conn.all(f"SELECT e.*, b.name AS branch, u.email, u.role FROM employees e LEFT JOIN branches b ON b.id = e.primary_branch_id "
                    f"LEFT JOIN users u ON u.id = e.user_id WHERE {scope} ORDER BY e.active DESC, e.full_name", params)
    if g.user.can("compensation.manage"):
        for r in rows:
            r["comp"] = current_compensation(conn, r["id"], today().isoformat())
    return render_template("staff/people/employees.html", rows=rows, branches=branches_for_user(g.user))


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
        elif action == "details":
            if not g.user.can("attendance.manage"):
                abort(403)
            branch_id = to_int(request.form.get("primary_branch_id"))
            if branch_id and not g.user.in_branch(branch_id):
                abort(403)
            upd = {"position": clean(request.form.get("position"), 80), "employment_type": request.form.get("employment_type", "regular"),
                   "primary_branch_id": branch_id, "active": 1 if request.form.get("active") else 0}
            conn.update("employees", emp_id, upd)
            audit.record("employee_updated", "employee", emp_id, "Updated employee", audit.diff(dict(e), upd, upd.keys()), branch_id)
            flash("Employee updated.", "success")
        return redirect(url_for("people.employee", emp_id=emp_id))
    comps = conn.all("SELECT c.*, u.name AS by_name FROM compensation c LEFT JOIN users u ON u.id = c.created_by WHERE employee_id = ? "
                     "ORDER BY effective_from DESC, id DESC", (emp_id,)) if g.user.can("compensation.manage") else []
    return render_template("staff/people/employee.html", e=e, comps=comps, branches=branches_for_user(g.user))


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
    return render_template("staff/people/attendance.html", rows=rows, start=start, end=end, status=status, emps=emps, emp=emp,
                           manage=manage, branches=branches_for_user(g.user), today=today().isoformat())


def _save_record(conn, emp_id, branch_id, work_date, time_in, time_out, source="manual"):
    rec = {"employee_id": emp_id, "branch_id": branch_id, "work_date": work_date, "time_in": time_in, "time_out": time_out, "status": "ok"}
    status, note = evaluate_record(conn, rec)
    existing = conn.one("SELECT * FROM time_records WHERE employee_id = ? AND work_date = ?", (emp_id, work_date))
    if existing:
        return None, existing
    rid = conn.insert("time_records", {**rec, "status": status, "exception_note": note, "source": source, "created_at": now_str()})
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
    emps = conn.all(f"SELECT e.*, u.email FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.active = 1 AND {scope}", params)
    by_key = {}
    for e in emps:
        by_key[e["full_name"].strip().lower()] = e
        if e["email"]:
            by_key[e["email"].lower()] = e
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
    default_start = t.replace(day=1) if t.day <= 15 else t.replace(day=16)
    return render_template("staff/people/payroll.html", periods=periods, branches=branches_for_user(g.user),
                           rules_confirmed=settings.get("payroll.rules_confirmed"), default_start=default_start.isoformat(),
                           default_end=t.isoformat())


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
                           show_money=g.user.can("compensation.manage"))


@bp.route("/payroll/<int:period_id>/export.csv")
@require("payroll.prepare", "payroll.approve", any_of=True)
def payroll_export(period_id):
    conn = get_db()
    p = _load_period(period_id)
    lines = conn.all("SELECT l.*, e.full_name, e.position FROM payroll_lines l JOIN employees e ON e.id = l.employee_id WHERE l.period_id = ? "
                     "ORDER BY e.full_name", (period_id,))
    show_money = g.user.can("compensation.manage")
    buf = io.StringIO()
    w = csv.writer(buf)
    label = "APPROVED SUMMARY (not a payment instruction)" if p["status"] == "approved" else "DRAFT — UNCONFIRMED ESTIMATE, NOT FINAL PAYROLL"
    w.writerow([f"Dental Haven payroll review: {p['name']} ({p['start_date']} to {p['end_date']})", label])
    header = ["Employee", "Position", "Days present", "Hours worked", "Late (min)", "Undertime (min)", "Open exceptions", "Pay basis"]
    if show_money:
        header += ["Rate (PHP)", "Estimate (PHP)", "Adjustment (PHP)", "Adjustment note"]
    w.writerow(header)
    for l in lines:
        row = [l["full_name"], l["position"], l["days_present"], round(l["minutes_worked"] / 60, 2), l["late_minutes"],
               l["undertime_minutes"], l["open_exceptions"], BASIS_LABELS.get(l["basis"], l["basis"])]
        if show_money:
            row += [(l["rate_cents"] or 0) / 100 if l["rate_cents"] is not None else "",
                    l["estimate_cents"] / 100 if l["estimate_cents"] is not None else "needs pay rule",
                    l["adjustment_cents"] / 100, l["adjustment_note"]]
        w.writerow(row)
    audit.record("payroll_exported", "payroll_period", period_id, "Exported payroll CSV")
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="payroll-{p["start_date"]}-{p["end_date"]}.csv"',
                             "Cache-Control": "no-store"})

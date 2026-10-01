"""Staff evaluation forms (e.g. the Assistant Checklist).

- Each form has its own link (/staff/evaluations/f/<code>). Only signed-in accounts whose access role has
  "Answer evaluation forms" can answer, and only while the admin has the form open.
- Admins ("Manage evaluation forms", super admin always) open/close forms, edit questions, and see the results.
"""
from __future__ import annotations

import csv
import io
import json
import secrets

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import login_required, require
from ..db import get_db
from ..evaluation_content import matches_target, parse_questions, to_text
from ..evaluation_roles import ANSWERED_BY
from ..permissions import POSITIONS
from ..util import clean, now_str, parse_date, to_int, today
from .common import branches_for_user

bp = Blueprint("evals", __name__, url_prefix="/staff/evaluations")

ANSWERS = {"yes": "Yes", "no": "No", "na": "N/A"}


def _form(form_id=None, slug=None):
    conn = get_db()
    f = conn.one("SELECT * FROM evaluation_forms WHERE id = ?", (form_id,)) if form_id else \
        conn.one("SELECT * FROM evaluation_forms WHERE slug = ?", (slug,))
    if not f:
        abort(404)
    f = dict(f)
    f["items"] = json.loads(f["questions_json"] or "[]")
    f["questions"] = [i for i in f["items"] if "q" in i]
    return f


def _employees(conn):
    return conn.all("SELECT e.id, e.full_name, e.position, e.user_id, e.primary_branch_id, b.name AS branch FROM employees e "
                    "LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE e.active = 1 ORDER BY e.full_name")


def _staff_for(conn, f, exclude_user=None, user=None):
    """The people this form is for (by position), never the evaluator themself. With `user`, only staff of that
    user's branches (super admins see everyone)."""
    out = []
    for e in _employees(conn):
        if not matches_target(e["position"], f.get("target_positions") or ""):
            continue
        if exclude_user and e["user_id"] == exclude_user:
            continue
        lab_form = "technician" in (f.get("target_positions") or "").lower()
        if user and not user.is_super_admin and not lab_form and e["primary_branch_id"] and not user.in_branch(e["primary_branch_id"]):
            continue
        out.append(e)
    return out


def is_head_dentist(conn, user) -> bool:
    return bool(conn.one("SELECT 1 AS x FROM employees WHERE user_id = ? AND active = 1 AND lower(position) = 'head dentist'", (user.id,)))


def can_answer_form(conn, user, f) -> bool:
    """Management can answer any form. Otherwise: 'dentists' forms need "Answer staff evaluation forms";
    'head_dentist' forms need that permission and the Head Dentist position; 'management' forms are admin-only."""
    if user.can("evaluations.manage"):
        return True
    who = f.get("answered_by") or "dentists"
    if not user.can("evaluations.answer") or who == "management":
        return False
    return who == "dentists" or (who == "head_dentist" and is_head_dentist(conn, user))


def score(yes: int, no: int):
    return round(yes * 100 / (yes + no)) if (yes + no) else None


@bp.route("/")
@login_required
def index():
    can_manage, can_answer = g.user.can("evaluations.manage"), g.user.can("evaluations.answer")
    if not (can_manage or can_answer):
        abort(403)
    conn = get_db()
    forms = conn.all("SELECT f.*, (SELECT COUNT(*) FROM evaluation_responses r WHERE r.form_id = f.id AND r.status = 'valid') AS n "
                     "FROM evaluation_forms f ORDER BY f.status DESC, f.title")
    last = {(r["form_id"], r["subject_employee_id"]): r["d"] for r in conn.all(
        "SELECT form_id, subject_employee_id, MAX(eval_date) AS d FROM evaluation_responses WHERE evaluator_id = ? AND status = 'valid' "
        "GROUP BY form_id, subject_employee_id", (g.user.id,))}
    for f in forms:
        f["qn"] = sum(1 for i in json.loads(f["questions_json"] or "[]") if "q" in i)
        f["mine"] = can_answer_form(conn, g.user, f)
        if f["status"] == "open" and f["mine"]:
            f["staff"] = [{**e, "last": last.get((f["id"], e["id"]))} for e in _staff_for(conn, f, g.user.id, g.user)]
    if not can_manage:
        forms = [f for f in forms if f["status"] == "open" and f["mine"]]
    mine = conn.all("SELECT r.*, f.title, e.full_name AS subject FROM evaluation_responses r JOIN evaluation_forms f ON f.id = r.form_id "
                    "LEFT JOIN employees e ON e.id = r.subject_employee_id WHERE r.evaluator_id = ? AND r.status = 'valid' "
                    "ORDER BY r.id DESC LIMIT 20", (g.user.id,))
    for r in mine:
        r["score"] = score(r["yes_count"], r["no_count"])
    return render_template("staff/evals/index.html", forms=forms, mine=mine, can_manage=can_manage, can_answer=can_answer)


@bp.route("/f/<slug>", methods=["GET", "POST"])
@login_required
def answer(slug):
    conn = get_db()
    f = _form(slug=slug)
    if not can_answer_form(conn, g.user, f):
        return render_template("staff/evals/blocked.html", f=f, reason="access", who=ANSWERED_BY.get(f["answered_by"], "")), 403
    if f["status"] != "open":
        return render_template("staff/evals/blocked.html", f=f, reason="closed")
    employees = _staff_for(conn, f, g.user.id, g.user)
    branches = branches_for_user(g.user)
    pre = next((e for e in employees if e["id"] == to_int(request.args.get("staff"))), None)
    branch = pre["primary_branch_id"] if pre and pre["primary_branch_id"] and g.user.in_branch(pre["primary_branch_id"]) else \
        (g.user.active_branch_id or (branches[0]["id"] if branches else None))
    v = {"subject": pre["id"] if pre else None, "eval_date": today().isoformat(), "branch_id": branch, "remarks": "", "answers": {}}
    errors = []
    if request.method == "POST":
        v["subject"] = to_int(request.form.get("subject_employee_id"))
        v["branch_id"] = to_int(request.form.get("branch_id"))
        v["eval_date"] = clean(request.form.get("eval_date"), 10)
        v["remarks"] = clean(request.form.get("remarks"), 2000)
        allowed = {"yes", "no"} | ({"na"} if f["allow_na"] else set())
        for q in f["questions"]:
            a = request.form.get(f"q{q['n']}")
            if a in allowed:
                v["answers"][str(q["n"])] = a
        missing = [q["n"] for q in f["questions"] if str(q["n"]) not in v["answers"]]
        day = parse_date(v["eval_date"])
        if not any(e["id"] == v["subject"] for e in employees):
            errors.append("Choose the staff member you're evaluating" + (f" ({f['target_positions']})" if f.get("target_positions") else "") + ".")
        if not day or day > today():
            errors.append("Enter the date (not in the future).")
        if v["branch_id"] and not g.user.in_branch(v["branch_id"]):
            errors.append("Choose one of your branches.")
        if missing:
            errors.append(f"Answer every question. Not answered yet: {', '.join(str(n) for n in missing[:15])}{'…' if len(missing) > 15 else ''}.")
        if not errors:
            vals = list(v["answers"].values())
            rid = conn.insert("evaluation_responses", {
                "form_id": f["id"], "evaluator_id": g.user.id, "subject_employee_id": v["subject"], "branch_id": v["branch_id"],
                "eval_date": day.isoformat(), "answers_json": json.dumps(v["answers"]), "yes_count": vals.count("yes"),
                "no_count": vals.count("no"), "na_count": vals.count("na"), "remarks": v["remarks"], "created_at": now_str()})
            audit.record("evaluation_submitted", "evaluation_form", f["id"], f"Answered {f['title']}", {"response_id": rid})
            flash("Thank you. Your evaluation was submitted.", "success")
            return redirect(url_for("evals.index"))
    return render_template("staff/evals/answer.html", f=f, v=v, errors=errors, employees=employees, branches=branches, answers=ANSWERS,
                           today_iso=today().isoformat())


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:form_id>/edit", methods=["GET", "POST"])
@require("evaluations.manage")
def edit(form_id=None):
    conn = get_db()
    f = _form(form_id) if form_id else None
    has_answers = bool(form_id and conn.one("SELECT id FROM evaluation_responses WHERE form_id = ? LIMIT 1", (form_id,)))
    v = {"title": f["title"] if f else "", "description": f["description"] if f else "", "questions": to_text(f["items"]) if f else "",
         "allow_na": f["allow_na"] if f else 1, "targets": [t.strip() for t in (f["target_positions"] if f else "").split(",") if t.strip()],
         "answered_by": f["answered_by"] if f else "dentists"}
    errors = []
    if request.method == "POST":
        v = {"title": clean(request.form.get("title"), 150), "description": clean(request.form.get("description"), 1000),
             "questions": request.form.get("questions") or "", "allow_na": 1 if request.form.get("allow_na") else 0,
             "targets": [t for t in request.form.getlist("target") if t in POSITIONS],
             "answered_by": request.form.get("answered_by") if request.form.get("answered_by") in ANSWERED_BY else "dentists"}
        items = parse_questions(v["questions"])
        if not v["title"]:
            errors.append("Enter the form title.")
        if not any("q" in i for i in items):
            errors.append("Add at least one question.")
        if len(items) > 300:
            errors.append("That's too many lines (300 at most).")
        if not errors:
            row = {"title": v["title"], "description": v["description"], "questions_json": json.dumps(items), "allow_na": v["allow_na"],
                   "target_positions": ", ".join(v["targets"]), "answered_by": v["answered_by"], "updated_at": now_str()}
            if f:
                conn.update("evaluation_forms", f["id"], row)
                fid = f["id"]
                audit.record("evaluation_form_edited", "evaluation_form", fid, f"Edited {v['title']}")
            else:
                fid = conn.insert("evaluation_forms", {**row, "slug": secrets.token_urlsafe(9), "status": "closed",
                                                       "created_by": g.user.id, "created_at": now_str()})
                audit.record("evaluation_form_created", "evaluation_form", fid, f"Created {v['title']}")
            flash("Form saved." + ("" if f else " It's closed until you open it."), "success")
            return redirect(url_for("evals.results", form_id=fid))
    return render_template("staff/evals/edit.html", f=f, v=v, errors=errors, has_answers=has_answers, positions=POSITIONS,
                           answered_by=ANSWERED_BY)


@bp.route("/<int:form_id>/status", methods=["POST"])
@require("evaluations.manage")
def status(form_id):
    conn = get_db()
    f = _form(form_id)
    action = request.form.get("action")
    if action == "open":
        conn.execute("UPDATE evaluation_forms SET status = 'open', opened_at = ?, updated_at = ? WHERE id = ?", (now_str(), now_str(), form_id))
        from ..notices import notify
        roles = {r["role"] for r in conn.all("SELECT role FROM role_permissions WHERE permission = 'evaluations.answer'")}
        users = []
        if f["answered_by"] in ("dentists", "head_dentist"):
            users = [u["id"] for u in conn.all("SELECT id, role, access_role FROM users WHERE active = 1")
                     if (u["access_role"] or u["role"]) in roles]
        if f["answered_by"] == "head_dentist":
            heads = {r["user_id"] for r in conn.all("SELECT user_id FROM employees WHERE active = 1 AND lower(position) = 'head dentist'")}
            users = [u for u in users if u in heads]
        notify(conn, users, "evaluation_open", f"Evaluation form open: {f['title']}", "Tap to answer.",
               url_for("evals.answer", slug=f["slug"]), exclude=g.user.id)
        flash(f"“{f['title']}” is open. Staff with access can answer it through the link, and they got a notification.", "success")
    elif action == "close":
        conn.execute("UPDATE evaluation_forms SET status = 'closed', closed_at = ?, updated_at = ? WHERE id = ?", (now_str(), now_str(), form_id))
        flash(f"“{f['title']}” is closed. No new answers are accepted.", "success")
    elif action == "new_link":
        conn.execute("UPDATE evaluation_forms SET slug = ?, updated_at = ? WHERE id = ?", (secrets.token_urlsafe(9), now_str(), form_id))
        flash("New link made. The old link no longer works.", "success")
    else:
        abort(400)
    audit.record(f"evaluation_form_{action}", "evaluation_form", form_id, f"{action.replace('_', ' ').capitalize()}: {f['title']}")
    return redirect(request.form.get("back") == "index" and url_for("evals.index") or url_for("evals.results", form_id=form_id))


def _responses(conn, form_id, args):
    where, params = ["r.form_id = ?", "r.status = 'valid'"], [form_id]
    start, end = parse_date(args.get("start")), parse_date(args.get("end"))
    if start:
        where.append("r.eval_date >= ?")
        params.append(start.isoformat())
    if end:
        where.append("r.eval_date <= ?")
        params.append(end.isoformat())
    emp = to_int(args.get("employee"))
    if emp:
        where.append("r.subject_employee_id = ?")
        params.append(emp)
    rows = conn.all("SELECT r.*, e.full_name AS subject, e.position, u.name AS evaluator, b.name AS branch FROM evaluation_responses r "
                    "LEFT JOIN employees e ON e.id = r.subject_employee_id JOIN users u ON u.id = r.evaluator_id "
                    f"LEFT JOIN branches b ON b.id = r.branch_id WHERE {' AND '.join(where)} ORDER BY r.eval_date DESC, r.id DESC", params)
    for r in rows:
        r["answers"] = json.loads(r["answers_json"] or "{}")
        r["score"] = score(r["yes_count"], r["no_count"])
    return rows


@bp.route("/<int:form_id>/results")
@require("evaluations.manage")
def results(form_id):
    conn = get_db()
    f = _form(form_id)
    rows = _responses(conn, form_id, request.args)
    per_q = []
    for q in f["questions"]:
        k = str(q["n"])
        yes = sum(1 for r in rows if r["answers"].get(k) == "yes")
        no = sum(1 for r in rows if r["answers"].get(k) == "no")
        per_q.append({**q, "yes": yes, "no": no, "na": sum(1 for r in rows if r["answers"].get(k) == "na"), "score": score(yes, no)})
    people = {}
    for r in rows:
        p = people.setdefault(r["subject_employee_id"], {"name": r["subject"] or "—", "n": 0, "yes": 0, "no": 0})
        p["n"] += 1
        p["yes"] += r["yes_count"]
        p["no"] += r["no_count"]
    for p in people.values():
        p["score"] = score(p["yes"], p["no"])
    link = url_for("evals.answer", slug=f["slug"], _external=True)
    f["who"] = ANSWERED_BY.get(f["answered_by"], "")
    return render_template("staff/evals/results.html", f=f, rows=rows, per_q=per_q, people=sorted(people.values(), key=lambda p: p["name"]),
                           link=link, employees=_staff_for(conn, f), args=request.args)


@bp.route("/<int:form_id>/results.csv")
@require("evaluations.manage")
def results_csv(form_id):
    conn = get_db()
    f = _form(form_id)
    rows = _responses(conn, form_id, request.args)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Staff evaluated", "Position", "Branch", "Evaluator", "Yes", "No", "N/A", "Score %", "Remarks"]
               + [f"{q['n']}. {q['q']}" for q in f["questions"]])
    for r in rows:
        w.writerow([r["eval_date"], r["subject"] or "", r["position"] or "", r["branch"] or "", r["evaluator"], r["yes_count"], r["no_count"],
                    r["na_count"], "" if r["score"] is None else r["score"], r["remarks"]]
                   + [ANSWERS.get(r["answers"].get(str(q["n"])), "") for q in f["questions"]])
    audit.record("evaluation_exported", "evaluation_form", form_id, f"Exported answers of {f['title']}")
    name = "".join(ch for ch in f["title"].lower().replace(" ", "-") if ch.isalnum() or ch == "-") or "evaluation"
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}-answers.csv"})


@bp.route("/responses/<int:rid>", methods=["GET", "POST"])
@login_required
def response(rid):
    conn = get_db()
    r = conn.one("SELECT r.*, e.full_name AS subject, e.position, u.name AS evaluator, b.name AS branch FROM evaluation_responses r "
                 "LEFT JOIN employees e ON e.id = r.subject_employee_id JOIN users u ON u.id = r.evaluator_id "
                 "LEFT JOIN branches b ON b.id = r.branch_id WHERE r.id = ? AND r.status = 'valid'", (rid,))
    if not r:
        abort(404)
    manage = g.user.can("evaluations.manage")
    if not (manage or r["evaluator_id"] == g.user.id):
        abort(403)
    f = _form(r["form_id"])
    if request.method == "POST":
        if not manage or request.form.get("action") != "delete":
            abort(403)
        conn.execute("UPDATE evaluation_responses SET status = 'deleted' WHERE id = ?", (rid,))
        audit.record("evaluation_deleted", "evaluation_form", f["id"], f"Deleted an answer to {f['title']}", {"response_id": rid})
        flash("Answer deleted.", "success")
        return redirect(url_for("evals.results", form_id=f["id"]))
    r = dict(r)
    r["answers"] = json.loads(r["answers_json"] or "{}")
    r["score"] = score(r["yes_count"], r["no_count"])
    return render_template("staff/evals/response.html", f=f, r=r, answers=ANSWERS, manage=manage)

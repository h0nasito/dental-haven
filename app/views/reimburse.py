"""Reimbursements: employees ask back money they spent for the clinic (amount, details, reason, receipt photo);
HR or anyone with reimburse.approve approves or disapproves. Approved reimbursements are added to the salary in the
payroll cutoff that covers the approval date (Payroll review → Recalculate), each one only once."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..notices import notify
from ..permissions import load_user_permissions
from ..uploads import IMAGE_TYPES, document_path, save_document, save_private_photo, sniff
from ..util import clean, now_str, parse_date, parse_money, peso, today
from .common import branches_for_user

bp = Blueprint("reimburse", __name__, url_prefix="/staff/reimbursements")

CATEGORIES = ["Transportation / fare", "Gas / parking / toll", "Meals", "Supplies bought for the clinic", "Delivery / courier",
              "Load / communication", "Medical", "Other"]
STATUS = {"pending": ("Pending", "badge-amber"), "approved": ("Approved", "badge-green"), "disapproved": ("Disapproved", "badge-red"),
          "cancelled": ("Cancelled", "")}


def approvers(conn, branch_id) -> list[int]:
    out = []
    for u in conn.all("SELECT id, role, access_role FROM users WHERE active = 1"):
        if u["role"] == "super_admin":
            out.append(u["id"])
        elif (not branch_id or conn.one("SELECT 1 AS x FROM user_branches WHERE user_id = ? AND branch_id = ?", (u["id"], branch_id))) \
                and "reimburse.approve" in load_user_permissions(conn, u["id"], u["access_role"] or u["role"]):
            out.append(u["id"])
    return out


def _can_review(r) -> bool:
    if not g.user.can("reimburse.approve"):
        return False
    me = get_db().one("SELECT id FROM employees WHERE user_id = ?", (g.user.id,))
    if me and me["id"] == r["employee_id"]:
        return False
    return g.user.is_super_admin or bool(r["branch_id"] and g.user.in_branch(r["branch_id"]))


@bp.route("/", methods=["GET", "POST"])
@require("reimburse.request", "reimburse.approve", any_of=True)
def index():
    conn = get_db()
    me = conn.one("SELECT * FROM employees WHERE user_id = ? AND active = 1", (g.user.id,))
    if request.method == "POST":
        if not g.user.can("reimburse.request"):
            abort(403)
        if not me:
            flash("Your account isn't linked to an employee record yet. Ask HR.", "error")
            return redirect(url_for("reimburse.index"))
        f = request.form
        spent = parse_date(f.get("spent_on"))
        cat = f.get("category")
        amt = parse_money(f.get("amount"))
        details, reason = clean(f.get("details"), 300), clean(f.get("reason"), 300)
        if not spent or spent > today() or spent < today() - timedelta(days=90):
            flash("Enter the date you spent it (within the last 90 days).", "error")
        elif cat not in CATEGORIES or not amt or amt <= 0 or amt > 10000000:
            flash("Choose what it was for and enter the amount.", "error")
        elif len(details) < 3 or len(reason) < 3:
            flash("Write the details (what was bought or paid) and the reason.", "error")
        else:
            stored = ""
            rc = request.files.get("receipt")
            if rc and rc.filename:
                head = rc.stream.read(16)
                rc.stream.seek(0)
                if sniff(head) in IMAGE_TYPES:
                    stored, err = save_private_photo(rc, "reimbursements")
                else:
                    stored, _m, _s, _o, err = save_document(rc)
                if err:
                    flash(f"Receipt: {err}", "error")
                    return redirect(url_for("reimburse.index"))
            rid = conn.insert("reimbursements", {"employee_id": me["id"], "branch_id": me["primary_branch_id"], "spent_on": spent.isoformat(),
                                                  "category": cat, "amount_cents": amt, "details": details, "reason": reason, "receipt": stored or "",
                                                  "status": "pending", "created_by": g.user.id, "created_at": now_str()})
            audit.record("reimbursement_filed", "reimbursement", rid, f"{me['full_name']} filed a reimbursement of {peso(amt)} ({cat})",
                         branch_id=me["primary_branch_id"])
            notify(conn, approvers(conn, me["primary_branch_id"]), "reimbursement", f"Reimbursement to approve: {me['full_name']}",
                   f"{peso(amt)} · {cat}", url_for("reimburse.index", show="pending"), exclude=g.user.id)
            flash("Reimbursement sent for approval.", "success")
        return redirect(url_for("reimburse.index"))
    show = request.args.get("show") or ("pending" if g.user.can("reimburse.approve") else "mine")
    mine = conn.all("SELECT r.*, u.name AS reviewer, p.name AS period_name FROM reimbursements r LEFT JOIN users u ON u.id = r.reviewed_by "
                    "LEFT JOIN payroll_periods p ON p.id = r.period_id WHERE r.employee_id = ? ORDER BY r.id DESC LIMIT 100",
                    (me["id"],)) if me else []
    rows, pending_n, pending_amt = [], 0, 0
    if g.user.can("reimburse.approve"):
        ids = [b["id"] for b in branches_for_user(g.user, include_all=g.user.is_super_admin)]
        marks = ",".join("?" * len(ids)) or "NULL"
        where = f"(r.branch_id IN ({marks}){' OR r.branch_id IS NULL' if g.user.is_super_admin else ''})"
        pend = conn.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(amount_cents), 0) AS a FROM reimbursements r WHERE r.status = 'pending' AND {where}", ids)
        pending_n, pending_amt = pend["n"], pend["a"]
        if show in ("pending", "approved", "all"):
            extra = {"pending": " AND r.status = 'pending'", "approved": " AND r.status = 'approved'", "all": ""}[show]
            rows = conn.all("SELECT r.*, e.full_name, e.position, b.name AS branch, u.name AS reviewer, p.name AS period_name FROM reimbursements r "
                            "JOIN employees e ON e.id = r.employee_id LEFT JOIN branches b ON b.id = r.branch_id LEFT JOIN users u ON u.id = r.reviewed_by "
                            f"LEFT JOIN payroll_periods p ON p.id = r.period_id WHERE {where}{extra} "
                            "ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END, r.id DESC LIMIT 300", ids)
    return render_template("staff/reimburse/index.html", me=me, mine=mine, rows=rows, show=show, pending_n=pending_n, pending_amt=pending_amt,
                           categories=CATEGORIES, status=STATUS, today=today().isoformat(), can_review=_can_review)


@bp.route("/<int:rid>", methods=["POST"])
@require("reimburse.request", "reimburse.approve", any_of=True)
def act(rid):
    conn = get_db()
    r = conn.one("SELECT r.*, e.full_name, e.user_id FROM reimbursements r JOIN employees e ON e.id = r.employee_id WHERE r.id = ?", (rid,))
    if not r:
        abort(404)
    action = request.form.get("action")
    note = clean(request.form.get("note"), 300)
    back = redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/staff/reimbursements") else url_for("reimburse.index"))
    if action == "cancel":
        if r["user_id"] != g.user.id or r["status"] != "pending":
            flash("Only your own pending reimbursement can be cancelled.", "error")
            return back
        conn.execute("UPDATE reimbursements SET status = 'cancelled' WHERE id = ?", (r["id"],))
        audit.record("reimbursement_cancelled", "reimbursement", r["id"], f"{r['full_name']} cancelled a reimbursement of {peso(r['amount_cents'])}",
                     branch_id=r["branch_id"])
        flash("Reimbursement cancelled.", "success")
        return back
    if action not in ("approve", "disapprove"):
        abort(400)
    if not _can_review(r):
        abort(403)
    if r["status"] != "pending":
        flash("This reimbursement was already decided.", "error")
        return back
    if action == "disapprove" and len(note) < 3:
        flash("Write the reason for disapproving.", "error")
        return back
    new = "approved" if action == "approve" else "disapproved"
    with conn.transaction():
        conn.execute("UPDATE reimbursements SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                     (new, note, g.user.id, now_str(), r["id"]))
        audit.record(f"reimbursement_{new}", "reimbursement", r["id"], f"{new.capitalize()} {r['full_name']}'s reimbursement of "
                     f"{peso(r['amount_cents'])}" + (f": {note}" if note else ""), branch_id=r["branch_id"])
        notify(conn, [r["user_id"]], "reimbursement", f"Your reimbursement was {new}",
               f"{peso(r['amount_cents'])} · {r['category']}" + (". It will be added to your salary in this cutoff's payroll." if new == "approved" else "")
               + (f" Note: {note}" if note else ""), url_for("reimburse.index", show="mine"))
    flash(f"Reimbursement {new}." + (" It is added to the salary when this cutoff's payroll is made or recalculated." if new == "approved" else ""),
          "success")
    return back


@bp.route("/<int:rid>/receipt")
@require("reimburse.request", "reimburse.approve", any_of=True)
def receipt(rid):
    conn = get_db()
    r = conn.one("SELECT r.*, e.user_id FROM reimbursements r JOIN employees e ON e.id = r.employee_id WHERE r.id = ?", (rid,))
    if not r or not r["receipt"]:
        abort(404)
    if r["user_id"] != g.user.id and not (g.user.can("reimburse.approve") and (g.user.is_super_admin or g.user.in_branch(r["branch_id"]))):
        abort(403)
    resp = send_file(document_path(r["receipt"]), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp

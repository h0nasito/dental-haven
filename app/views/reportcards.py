"""Patient report cards: generated from the record, written in plain language, reviewed by a dentist
before they can be printed or shared with the patient."""
from __future__ import annotations

import json
from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..permissions import branch_filter, can_see_clinical
from ..util import clean, now_str, parse_date, to_int, today

bp = Blueprint("reportcards", __name__, url_prefix="/staff/report-cards")


def build_snapshot(conn, patient_id: int, start: str, end: str) -> dict:
    end_excl = (parse_date(end) + timedelta(days=1)).isoformat()
    visits = conn.all("SELECT a.start_at, s.name AS service, u.name AS dentist, b.name AS branch FROM appointments a "
                      "JOIN services s ON s.id = a.service_id LEFT JOIN users u ON u.id = a.dentist_id JOIN branches b ON b.id = a.branch_id "
                      "WHERE a.patient_id = ? AND a.status = 'completed' AND a.start_at >= ? AND a.start_at < ? ORDER BY a.start_at",
                      (patient_id, start, end_excl))
    procedures = conn.all("SELECT performed_at, description, tooth FROM procedures WHERE patient_id = ? AND status = 'completed' "
                          "AND performed_at BETWEEN ? AND ? ORDER BY performed_at", (patient_id, start, end))
    planned = conn.all("SELECT i.description, i.tooth, i.status, t.title AS plan FROM treatment_plan_items i JOIN treatment_plans t ON t.id = i.plan_id "
                       "WHERE t.patient_id = ? AND t.status NOT IN ('completed','declined') AND i.status IN ('pending','scheduled') "
                       "ORDER BY t.id, i.seq", (patient_id,))
    followups = conn.all("SELECT title, due_at FROM follow_ups WHERE patient_id = ? AND status = 'open' ORDER BY due_at", (patient_id,))
    upcoming = conn.all("SELECT a.start_at, s.name AS service FROM appointments a JOIN services s ON s.id = a.service_id "
                        "WHERE a.patient_id = ? AND a.status IN ('confirmed','requested') AND a.start_at >= ? ORDER BY a.start_at LIMIT 3",
                        (patient_id, today().isoformat()))
    return {"visits": visits, "procedures": procedures, "planned": planned, "followups": followups, "upcoming": upcoming}


def draft_summary(snap: dict) -> tuple[str, str]:
    n = len(snap["visits"])
    parts = [f"During this period you visited Dental Haven {n} time{'s' if n != 1 else ''}."] if n else \
        ["We have no completed visits recorded for this period."]
    if snap["procedures"]:
        parts.append("Treatments completed: " + "; ".join(
            p["description"] + (f" (tooth {p['tooth']})" if p["tooth"] else "") for p in snap["procedures"]) + ".")
    if snap["planned"]:
        parts.append("Your dentist has recommended the following next steps: " + "; ".join(
            p["description"] + (f" (tooth {p['tooth']})" if p["tooth"] else "") for p in snap["planned"]) + ".")
    recs = []
    if snap["upcoming"]:
        recs.append("Your next appointment: " + ", ".join(f"{u['service']} on {u['start_at'][:10]}" for u in snap["upcoming"]) + ".")
    if snap["followups"]:
        recs.append("We will check in with you about: " + "; ".join(f["title"] for f in snap["followups"]) + ".")
    recs.append("[Dentist: add home-care advice and when to return for a check-up.]")
    return " ".join(parts), "\n".join(recs)


@bp.route("/")
@require("reportcards.generate", "reportcards.review", any_of=True)
def index():
    conn = get_db()
    where, args = [], []
    if g.user.role == "dentist":
        where.append("(r.reviewer_id = ? OR r.patient_id IN (SELECT patient_id FROM patient_assignments WHERE dentist_id = ?))")
        args += [g.user.id, g.user.id]
    else:
        bf, bp_ = branch_filter(g.user, "r.branch_id")
        where.append(bf)
        args += bp_
    rows = conn.all("SELECT r.*, p.first_name, p.last_name, p.chart_no, u.name AS reviewer, gb.name AS generated_by_name FROM report_cards r "
                    "JOIN patients p ON p.id = r.patient_id LEFT JOIN users u ON u.id = r.reviewer_id LEFT JOIN users gb ON gb.id = r.generated_by "
                    f"WHERE {' AND '.join(where)} ORDER BY CASE r.status WHEN 'pending_review' THEN 0 ELSE 1 END, r.generated_at DESC LIMIT 200", args)
    return render_template("staff/reportcards/index.html", rows=rows)


@bp.route("/new/<int:patient_id>", methods=["GET", "POST"])
@require("reportcards.generate")
def new(patient_id):
    conn = get_db()
    if not can_see_clinical(conn, g.user, patient_id):
        abort(403)
    p = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    reviewers = conn.all("SELECT u.id, u.name FROM patient_assignments pa JOIN users u ON u.id = pa.dentist_id WHERE pa.patient_id = ? "
                         "AND u.active = 1 ORDER BY u.name", (patient_id,))
    start = parse_date(request.values.get("from")) or (today() - timedelta(days=180))
    end = parse_date(request.values.get("to")) or today()
    if request.method == "POST":
        reviewer_id = to_int(request.form.get("reviewer_id"))
        if g.user.role == "dentist":
            reviewer_id = g.user.id
        if not any(r["id"] == reviewer_id for r in reviewers):
            flash("Choose the patient's dentist as reviewer (only an assigned dentist can review).", "error")
        else:
            snap = build_snapshot(conn, patient_id, start.isoformat(), end.isoformat())
            summary, recs = draft_summary(snap)
            rid = conn.insert("report_cards", {"patient_id": patient_id, "branch_id": p["preferred_branch_id"],
                                               "period_from": start.isoformat(), "period_to": end.isoformat(), "reviewer_id": reviewer_id,
                                               "status": "pending_review", "summary": summary, "recommendations": recs,
                                               "snapshot": json.dumps(snap, default=str), "generated_by": g.user.id, "generated_at": now_str()})
            audit.record("reportcard_generated", "patient", patient_id, "Generated report card (pending dentist review)", {"report_card_id": rid})
            flash("Report card generated. The dentist must review it before it can be shared.", "success")
            return redirect(url_for("reportcards.detail", rc_id=rid))
    preview = build_snapshot(conn, patient_id, start.isoformat(), end.isoformat())
    return render_template("staff/reportcards/new.html", p=p, reviewers=reviewers, start=start, end=end, preview=preview)


def _load(rc_id):
    conn = get_db()
    r = conn.one("SELECT r.*, p.first_name, p.last_name, p.chart_no, p.birth_date, u.name AS reviewer, rv.name AS reviewed_by_name, "
                 "gb.name AS generated_by_name, b.name AS branch FROM report_cards r JOIN patients p ON p.id = r.patient_id "
                 "LEFT JOIN users u ON u.id = r.reviewer_id LEFT JOIN users rv ON rv.id = r.reviewed_by LEFT JOIN users gb ON gb.id = r.generated_by "
                 "LEFT JOIN branches b ON b.id = r.branch_id WHERE r.id = ?", (rc_id,))
    if not r:
        abort(404)
    if not can_see_clinical(conn, g.user, r["patient_id"]):
        abort(403)
    r["snap"] = json.loads(r["snapshot"] or "{}")
    return r


@bp.route("/<int:rc_id>", methods=["GET", "POST"])
@require("reportcards.generate", "reportcards.review", any_of=True)
def detail(rc_id):
    conn = get_db()
    r = _load(rc_id)
    is_reviewer = g.user.role == "dentist" and g.user.id == r["reviewer_id"] and g.user.can("reportcards.review")
    if request.method == "POST":
        action = request.form.get("action")
        summary = clean(request.form.get("summary"), 4000)
        recs = clean(request.form.get("recommendations"), 4000)
        if action == "save" and r["status"] in ("pending_review", "changes_requested"):
            if not (is_reviewer or g.user.can("reportcards.generate")):
                abort(403)
            conn.execute("UPDATE report_cards SET summary = ?, recommendations = ?, status = 'pending_review' WHERE id = ?", (summary, recs, rc_id))
            audit.record("reportcard_edited", "patient", r["patient_id"], "Edited report card text", {"report_card_id": rc_id})
            flash("Saved. Still waiting for dentist review.", "success")
        elif action in ("approve", "changes") and r["status"] in ("pending_review", "changes_requested"):
            if not is_reviewer:
                abort(403)
            if action == "approve" and "[Dentist:" in (summary + recs):
                flash("Replace the [Dentist: …] placeholder text before approving.", "error")
                return redirect(url_for("reportcards.detail", rc_id=rc_id))
            status = "approved" if action == "approve" else "changes_requested"
            conn.execute("UPDATE report_cards SET summary = ?, recommendations = ?, status = ?, reviewed_by = ?, reviewed_at = ?, review_note = ? WHERE id = ?",
                         (summary, recs, status, g.user.id, now_str(), clean(request.form.get("review_note"), 500), rc_id))
            audit.record("reportcard_" + status, "patient", r["patient_id"], f"Report card {status.replace('_', ' ')}", {"report_card_id": rc_id})
            flash("Approved. The report card can now be printed for the patient." if status == "approved" else "Sent back for changes.", "success")
        elif action == "revoke" and r["status"] == "approved":
            if not (is_reviewer or g.user.is_super_admin):
                abort(403)
            conn.execute("UPDATE report_cards SET status = 'revoked' WHERE id = ?", (rc_id,))
            audit.record("reportcard_revoked", "patient", r["patient_id"], "Report card revoked", {"report_card_id": rc_id})
            flash("Revoked.", "success")
        return redirect(url_for("reportcards.detail", rc_id=rc_id))
    return render_template("staff/reportcards/detail.html", r=r, is_reviewer=is_reviewer)


@bp.route("/<int:rc_id>/print")
@require("reportcards.generate", "reportcards.review", any_of=True)
def print_view(rc_id):
    r = _load(rc_id)
    if r["status"] == "approved":
        audit.record("reportcard_printed", "patient", r["patient_id"], "Printed approved report card", {"report_card_id": rc_id})
    return render_template("staff/reportcards/print.html", r=r)

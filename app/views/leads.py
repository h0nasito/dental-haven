"""Lead inbox, follow-up tasks, response templates and the reminder outbox."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..messaging import (ALLOWED_PLACEHOLDERS, CHANNELS, appointment_values, channel_allowed, get_provider, render,
                         schedule_appointment_reminders)
from ..permissions import branch_filter, can_see_patient
from ..util import clean, fmt_dt, now, now_str, parse_dt, to_int, today
from .common import branches_for_user, followup_scope, paginate, services

bp = Blueprint("leads", __name__, url_prefix="/staff")

LEAD_SOURCES = {
    "facebook": "Facebook page", "messenger": "Messenger", "instagram": "Instagram", "website": "Website form",
    "phone": "Phone call", "walk_in": "Walk-in", "referral": "Referral", "other": "Other",
}
LEAD_STATUSES = {"new": "New", "contacted": "Contacted", "qualified": "Interested", "booked": "Booked",
                 "converted": "Converted to patient", "lost": "Lost / not interested"}
FOLLOWUP_KINDS = {"post_treatment": "Post-treatment check", "recall": "Recall / cleaning due", "no_show": "Missed appointment",
                  "treatment_plan": "Pending treatment plan", "balance": "Outstanding balance", "lead": "Lead follow-up",
                  "other": "Other"}


@bp.app_context_processor
def _globals():
    return {"LEAD_SOURCES": LEAD_SOURCES, "LEAD_STATUSES": LEAD_STATUSES, "FOLLOWUP_KINDS": FOLLOWUP_KINDS, "CHANNELS": CHANNELS}


def _lead_scope(alias="l"):
    bf, bp_ = branch_filter(g.user, f"{alias}.branch_id")
    return f"({bf} OR {alias}.branch_id IS NULL)", bp_


def _load_lead(lead_id):
    conn = get_db()
    lead = conn.one("SELECT l.*, b.name AS branch, s.name AS service, u.name AS owner FROM leads l "
                    "LEFT JOIN branches b ON b.id = l.branch_id LEFT JOIN services s ON s.id = l.service_id "
                    "LEFT JOIN users u ON u.id = l.owner_id WHERE l.id = ?", (lead_id,))
    if not lead:
        abort(404)
    if lead["branch_id"] and not g.user.in_branch(lead["branch_id"]):
        abort(403)
    return lead


def _staff_options():
    conn = get_db()
    ids = g.user.branch_ids or [0]
    marks = ",".join("?" for _ in ids)
    return conn.all(f"SELECT DISTINCT u.id, u.name FROM users u LEFT JOIN user_branches ub ON ub.user_id = u.id "
                    f"WHERE u.active = 1 AND u.role IN ('receptionist','staff','super_admin') AND (ub.branch_id IN ({marks}) OR u.role='super_admin') "
                    "ORDER BY u.name", ids)


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

@bp.route("/leads")
@require("leads.view")
def index():
    conn = get_db()
    scope, params = _lead_scope()
    where, args = [scope], list(params)
    status = request.args.get("status", "open")
    if status == "open":
        where.append("l.status IN ('new','contacted','qualified')")
    elif status in LEAD_STATUSES:
        where.append("l.status = ?")
        args.append(status)
    source = request.args.get("source")
    if source in LEAD_SOURCES:
        where.append("l.source = ?")
        args.append(source)
    owner = request.args.get("owner")
    if owner == "me":
        where.append("l.owner_id = ?")
        args.append(g.user.id)
    elif owner == "none":
        where.append("l.owner_id IS NULL")
    total = conn.scalar(f"SELECT COUNT(*) FROM leads l WHERE {' AND '.join(where)}", args)
    pg = paginate(total, 40)
    rows = conn.all("SELECT l.*, b.name AS branch, s.name AS service, u.name AS owner FROM leads l "
                    "LEFT JOIN branches b ON b.id = l.branch_id LEFT JOIN services s ON s.id = l.service_id "
                    f"LEFT JOIN users u ON u.id = l.owner_id WHERE {' AND '.join(where)} "
                    "ORDER BY CASE l.status WHEN 'new' THEN 0 ELSE 1 END, COALESCE(l.next_follow_up_at, l.created_at) LIMIT ? OFFSET ?",
                    [*args, pg["limit"], pg["offset"]])
    since = (today() - timedelta(days=30)).isoformat()
    stats = conn.all(f"SELECT l.source, COUNT(*) AS total, SUM(CASE WHEN l.status IN ('booked','converted') THEN 1 ELSE 0 END) AS won "
                     f"FROM leads l WHERE {scope} AND l.created_at >= ? GROUP BY l.source ORDER BY total DESC", [*params, since])
    return render_template("staff/leads/index.html", rows=rows, pg=pg, status=status, source=source, owner=owner,
                           stats=stats, now_s=now_str())


@bp.route("/leads/new", methods=["GET", "POST"])
@require("leads.manage")
def lead_new():
    conn = get_db()
    v = {"full_name": "", "phone": "", "email": "", "source": "facebook", "branch_id": g.user.active_branch_id,
         "service_id": None, "message": "", "owner_id": g.user.id, "consent_contact": False,
         "next_follow_up_at": ""}
    errors = {}
    if request.method == "POST":
        v = {"full_name": clean(request.form.get("full_name"), 120), "phone": clean(request.form.get("phone"), 25),
             "email": clean(request.form.get("email"), 200).lower(), "source": request.form.get("source"),
             "branch_id": to_int(request.form.get("branch_id")), "service_id": to_int(request.form.get("service_id")),
             "message": clean(request.form.get("message"), 2000), "owner_id": to_int(request.form.get("owner_id")),
             "consent_contact": bool(request.form.get("consent_contact")),
             "next_follow_up_at": clean(request.form.get("next_follow_up_at"), 16)}
        if not v["full_name"]:
            errors["full_name"] = "Enter a name (a Facebook display name is fine)."
        if v["source"] not in LEAD_SOURCES:
            errors["source"] = "Choose where the inquiry came from."
        if v["branch_id"] and not g.user.in_branch(v["branch_id"]):
            errors["branch_id"] = "Choose one of your branches."
        nf = parse_dt(v["next_follow_up_at"]) if v["next_follow_up_at"] else None
        if v["next_follow_up_at"] and not nf:
            errors["next_follow_up_at"] = "Enter a valid date and time."
        if not errors:
            lead_id = conn.insert("leads", {
                "full_name": v["full_name"], "phone": v["phone"], "email": v["email"], "source": v["source"],
                "branch_id": v["branch_id"], "service_id": v["service_id"], "message": v["message"], "owner_id": v["owner_id"],
                "status": "new", "consent_contact": 1 if v["consent_contact"] else 0,
                "next_follow_up_at": fmt_dt(nf) if nf else None, "created_at": now_str(), "created_by": g.user.id,
                "updated_at": now_str()})
            conn.execute("INSERT INTO lead_activities (lead_id, user_id, kind, body, created_at) VALUES (?, ?, 'created', ?, ?)",
                         (lead_id, g.user.id, f"Logged manually ({LEAD_SOURCES[v['source']]})", now_str()))
            audit.record("lead_created", "lead", lead_id, f"Logged {LEAD_SOURCES[v['source']]} inquiry", branch_id=v["branch_id"])
            flash("Inquiry logged.", "success")
            return redirect(url_for("leads.lead_detail", lead_id=lead_id))
    return render_template("staff/leads/lead_form.html", v=v, errors=errors, branches=branches_for_user(g.user),
                           services=services(), staff=_staff_options())


@bp.route("/leads/<int:lead_id>", methods=["GET", "POST"])
@require("leads.view")
def lead_detail(lead_id):
    conn = get_db()
    lead = _load_lead(lead_id)
    if request.method == "POST":
        if not g.user.can("leads.manage"):
            abort(403)
        action = request.form.get("action")
        if action == "update":
            status = request.form.get("status")
            nf_raw = clean(request.form.get("next_follow_up_at"), 16)
            nf = parse_dt(nf_raw) if nf_raw else None
            owner_id = to_int(request.form.get("owner_id"))
            branch_id = to_int(request.form.get("branch_id"))
            if status not in LEAD_STATUSES or (branch_id and not g.user.in_branch(branch_id)):
                abort(400)
            upd = {"status": status, "next_follow_up_at": fmt_dt(nf) if nf else None, "owner_id": owner_id,
                   "branch_id": branch_id, "service_id": to_int(request.form.get("service_id")),
                   "lost_reason": clean(request.form.get("lost_reason"), 300), "updated_at": now_str()}
            changes = audit.diff(dict(lead), upd, ["status", "next_follow_up_at", "owner_id", "branch_id", "service_id", "lost_reason"])
            conn.update("leads", lead_id, upd)
            if changes:
                conn.execute("INSERT INTO lead_activities (lead_id, user_id, kind, body, created_at) VALUES (?, ?, 'update', ?, ?)",
                             (lead_id, g.user.id, "Updated " + ", ".join(k.replace("_", " ") for k in changes), now_str()))
                audit.record("lead_updated", "lead", lead_id, "Updated lead", changes, branch_id)
            flash("Lead updated.", "success")
        elif action == "activity":
            kind = request.form.get("kind", "note")
            body = clean(request.form.get("body"), 2000)
            if body:
                conn.execute("INSERT INTO lead_activities (lead_id, user_id, kind, body, created_at) VALUES (?, ?, ?, ?, ?)",
                             (lead_id, g.user.id, kind if kind in ("note", "call", "message", "reply") else "note", body, now_str()))
                if lead["status"] == "new" and kind in ("call", "message", "reply"):
                    conn.execute("UPDATE leads SET status = 'contacted', updated_at = ? WHERE id = ?", (now_str(), lead_id))
                flash("Activity logged.", "success")
        elif action == "convert":
            if not g.user.can("patients.manage"):
                abort(403)
            pid = to_int(request.form.get("patient_id"))
            if pid:
                if not can_see_patient(conn, g.user, pid):
                    abort(403)
            else:
                from .patients import next_chart_no
                first, _, last = lead["full_name"].strip().partition(" ")
                branch = lead["branch_id"] or (g.user.branch_ids[0] if g.user.branch_ids else None)
                pid = conn.insert("patients", {
                    "chart_no": next_chart_no(conn), "first_name": first, "last_name": last or "-", "phone": lead["phone"],
                    "email": lead["email"], "preferred_branch_id": branch, "consent_privacy": 0,
                    "contact_sms": lead["consent_contact"] if lead["phone"] else 0,
                    "contact_email": lead["consent_contact"] if lead["email"] else 0,
                    "source": f"lead:{lead['source']}", "created_at": now_str(), "created_by": g.user.id})
                audit.record("patient_created", "patient", pid, f"Registered from lead #{lead_id}", branch_id=branch)
            conn.execute("UPDATE leads SET patient_id = ?, status = 'converted', updated_at = ? WHERE id = ?", (pid, now_str(), lead_id))
            conn.execute("INSERT INTO lead_activities (lead_id, user_id, kind, body, created_at) VALUES (?, ?, 'converted', 'Converted to patient record', ?)",
                         (lead_id, g.user.id, now_str()))
            audit.record("lead_converted", "lead", lead_id, "Converted to patient", {"patient_id": pid}, lead["branch_id"])
            flash("Converted to a patient record. Record privacy consent at the first visit, then book an appointment.", "success")
            if g.user.can("appointments.manage"):
                return redirect(url_for("sched.appointment_new", patient_id=pid))
            return redirect(url_for("patients.detail", patient_id=pid))
        return redirect(url_for("leads.lead_detail", lead_id=lead_id))
    activities = conn.all("SELECT a.*, u.name AS user FROM lead_activities a LEFT JOIN users u ON u.id = a.user_id "
                          "WHERE a.lead_id = ? ORDER BY a.id DESC", (lead_id,))
    templates = conn.all("SELECT * FROM message_templates WHERE purpose IN ('lead_reply','booking_ack') AND active = 1 ORDER BY name")
    first = lead["full_name"].split(" ")[0]
    branch = conn.one("SELECT * FROM branches WHERE id = ?", (lead["branch_id"],)) if lead["branch_id"] else None
    values = {"first_name": first, "clinic": "Dental Haven", "branch": branch["name"] if branch else "our clinic",
              "branch_phone": branch["phone"] if branch else "", "service": lead["service"] or ""}
    rendered = [{"t": t, "text": render(t["body"], values)} for t in templates]
    matches = []
    if lead["phone"] or lead["email"]:
        digits = "".join(c for c in lead["phone"] if c.isdigit())[-10:]
        from ..permissions import patient_scope
        frag, params = patient_scope(g.user, "p")
        matches = conn.all(f"SELECT p.id, p.chart_no, p.first_name, p.last_name, p.phone FROM patients p WHERE {frag} AND "
                           "(replace(replace(p.phone,' ',''),'-','') LIKE ? OR (p.email != '' AND lower(p.email) = lower(?))) LIMIT 5",
                           [*params, f"%{digits}" if digits else "__none__", lead["email"] or "__none__"])
    return render_template("staff/leads/lead_detail.html", lead=lead, activities=activities, rendered=rendered,
                           branches=branches_for_user(g.user), services=services(), staff=_staff_options(), matches=matches)


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------

@bp.route("/followups")
@require("followups.view")
def followups():
    conn = get_db()
    fq, fp = followup_scope(g.user)
    view = request.args.get("view", "due")
    where, args = [fq], list(fp)
    tomorrow = (today() + timedelta(days=1)).isoformat()
    if view == "due":
        where.append("f.status = 'open' AND f.due_at < ?")
        args.append(tomorrow)
    elif view == "upcoming":
        where.append("f.status = 'open' AND f.due_at >= ?")
        args.append(tomorrow)
    elif view == "done":
        where.append("f.status IN ('done','cancelled')")
    if request.args.get("mine"):
        where.append("f.assignee_id = ?")
        args.append(g.user.id)
    order = "f.completed_at DESC" if view == "done" else "f.due_at"
    rows = conn.all("SELECT f.*, p.first_name, p.last_name, p.alert_flag, l.full_name AS lead_name, u.name AS assignee, b.name AS branch "
                    "FROM follow_ups f LEFT JOIN patients p ON p.id = f.patient_id LEFT JOIN leads l ON l.id = f.lead_id "
                    "LEFT JOIN users u ON u.id = f.assignee_id LEFT JOIN branches b ON b.id = f.branch_id "
                    f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 300", args)
    counts = {
        "overdue": conn.scalar(f"SELECT COUNT(*) FROM follow_ups f WHERE {fq} AND f.status='open' AND f.due_at < ?", [*fp, now_str()]),
        "today": conn.scalar(f"SELECT COUNT(*) FROM follow_ups f WHERE {fq} AND f.status='open' AND f.due_at >= ? AND f.due_at < ?",
                             [*fp, now_str(), tomorrow]),
    }
    return render_template("staff/leads/followups.html", rows=rows, view=view, counts=counts, now_s=now_str())


@bp.route("/followups/new", methods=["GET", "POST"])
@require("followups.manage")
def followup_new():
    conn = get_db()
    patient_id = to_int(request.values.get("patient_id"))
    lead_id = to_int(request.values.get("lead_id"))
    patient = lead = None
    if patient_id:
        if not can_see_patient(conn, g.user, patient_id):
            abort(403)
        patient = conn.one("SELECT * FROM patients WHERE id = ?", (patient_id,))
    if lead_id:
        lead = _load_lead(lead_id)
    v = {"kind": "lead" if lead else "post_treatment", "title": "", "due_at": fmt_dt((now() + timedelta(days=1)).replace(hour=10, minute=0)),
         "assignee_id": g.user.id if g.user.role != "dentist" else None, "notes": "",
         "branch_id": (patient["preferred_branch_id"] if patient else None) or (lead["branch_id"] if lead else None) or g.user.active_branch_id}
    errors = {}
    if request.method == "POST":
        v = {"kind": request.form.get("kind"), "title": clean(request.form.get("title"), 150),
             "due_at": clean(request.form.get("due_at"), 16), "assignee_id": to_int(request.form.get("assignee_id")),
             "notes": clean(request.form.get("notes"), 2000), "branch_id": to_int(request.form.get("branch_id"))}
        due = parse_dt(v["due_at"])
        if v["kind"] not in FOLLOWUP_KINDS:
            errors["kind"] = "Choose a type."
        if not v["title"]:
            errors["title"] = "Describe the follow-up."
        if not due:
            errors["due_at"] = "Enter a due date and time."
        if not v["branch_id"] or not g.user.in_branch(v["branch_id"]):
            errors["branch_id"] = "Choose one of your branches."
        if not errors:
            fid = conn.insert("follow_ups", {"branch_id": v["branch_id"], "patient_id": patient_id, "lead_id": lead_id, "kind": v["kind"],
                                             "title": v["title"], "due_at": fmt_dt(due), "status": "open", "assignee_id": v["assignee_id"],
                                             "notes": v["notes"], "created_at": now_str(), "created_by": g.user.id})
            audit.record("followup_created", "follow_up", fid, v["title"], branch_id=v["branch_id"])
            flash("Follow-up created.", "success")
            return redirect(url_for("leads.followup_detail", fu_id=fid))
    return render_template("staff/leads/followup_form.html", v=v, errors=errors, patient=patient, lead=lead,
                           branches=branches_for_user(g.user), staff=_staff_options())


def _load_followup(fu_id):
    conn = get_db()
    f = conn.one("SELECT f.*, p.first_name, p.last_name, p.phone AS patient_phone, p.alert_flag, l.full_name AS lead_name, "
                 "l.phone AS lead_phone, u.name AS assignee, b.name AS branch FROM follow_ups f LEFT JOIN patients p ON p.id = f.patient_id "
                 "LEFT JOIN leads l ON l.id = f.lead_id LEFT JOIN users u ON u.id = f.assignee_id LEFT JOIN branches b ON b.id = f.branch_id "
                 "WHERE f.id = ?", (fu_id,))
    if not f:
        abort(404)
    fq, fp = followup_scope(g.user)
    if not conn.one(f"SELECT f.id FROM follow_ups f WHERE f.id = ? AND {fq}", [fu_id, *fp]):
        abort(403)
    return f


@bp.route("/followups/<int:fu_id>", methods=["GET", "POST"])
@require("followups.view")
def followup_detail(fu_id):
    conn = get_db()
    f = _load_followup(fu_id)
    if request.method == "POST":
        if not g.user.can("followups.manage"):
            abort(403)
        action = request.form.get("action")
        if action == "complete":
            outcome = clean(request.form.get("outcome"), 1000)
            if not outcome:
                flash("Record the outcome (e.g. 'Called, booked for Oct 3').", "error")
                return redirect(url_for("leads.followup_detail", fu_id=fu_id))
            conn.execute("UPDATE follow_ups SET status='done', outcome=?, completed_at=?, completed_by=? WHERE id=?",
                         (outcome, now_str(), g.user.id, fu_id))
            audit.record("followup_completed", "follow_up", fu_id, f"Completed: {f['title']}", {"outcome": outcome}, f["branch_id"])
            if request.form.get("next_days"):
                days = to_int(request.form.get("next_days"), 0)
                if 0 < days <= 730:
                    nid = conn.insert("follow_ups", {"branch_id": f["branch_id"], "patient_id": f["patient_id"], "lead_id": f["lead_id"],
                                                     "kind": f["kind"], "title": f["title"], "due_at": fmt_dt((now() + timedelta(days=days)).replace(hour=10, minute=0)),
                                                     "status": "open", "assignee_id": f["assignee_id"], "created_at": now_str(), "created_by": g.user.id})
                    audit.record("followup_created", "follow_up", nid, "Next follow-up scheduled", branch_id=f["branch_id"])
            flash("Follow-up completed.", "success")
            return redirect(url_for("leads.followups"))
        if action == "reschedule":
            due = parse_dt(request.form.get("due_at"))
            if due:
                conn.execute("UPDATE follow_ups SET due_at = ?, assignee_id = ? WHERE id = ?",
                             (fmt_dt(due), to_int(request.form.get("assignee_id")), fu_id))
                audit.record("followup_rescheduled", "follow_up", fu_id, f"Due {fmt_dt(due)}", branch_id=f["branch_id"])
                flash("Follow-up updated.", "success")
        if action == "cancel":
            conn.execute("UPDATE follow_ups SET status='cancelled', outcome=?, completed_at=?, completed_by=? WHERE id=?",
                         (clean(request.form.get("outcome"), 500) or "Cancelled", now_str(), g.user.id, fu_id))
            audit.record("followup_cancelled", "follow_up", fu_id, f["title"], branch_id=f["branch_id"])
            flash("Follow-up cancelled.", "success")
        return redirect(url_for("leads.followup_detail", fu_id=fu_id))
    templates = conn.all("SELECT * FROM message_templates WHERE purpose IN ('follow_up','lead_reply') AND active = 1 ORDER BY name")
    first = (f["first_name"] or (f["lead_name"] or "").split(" ")[0]) if (f["first_name"] or f["lead_name"]) else ""
    br = conn.one("SELECT * FROM branches WHERE id = ?", (f["branch_id"],)) if f["branch_id"] else None
    values = {"first_name": first, "clinic": "Dental Haven", "branch": br["name"] if br else "", "branch_phone": br["phone"] if br else ""}
    patient = conn.one("SELECT * FROM patients WHERE id = ?", (f["patient_id"],)) if f["patient_id"] else None
    rendered = [{"t": t, "text": render(t["body"], values)} for t in templates]
    return render_template("staff/leads/followup_detail.html", f=f, rendered=rendered, staff=_staff_options(), patient=patient,
                           now_s=now_str())


# ---------------------------------------------------------------------------
# Reminder outbox (manual send only)
# ---------------------------------------------------------------------------

@bp.route("/reminders")
@require("reminders.view")
def reminders():
    conn = get_db()
    rf, rp = branch_filter(g.user, "r.branch_id")
    view = request.args.get("view", "due")
    where, args = [rf], list(rp)
    horizon = fmt_dt(now() + timedelta(days=1))
    if view == "due":
        where.append("r.status = 'pending' AND r.scheduled_for <= ?")
        args.append(horizon)
    elif view == "scheduled":
        where.append("r.status = 'pending' AND r.scheduled_for > ?")
        args.append(horizon)
    elif view == "skipped":
        where.append("r.status IN ('skipped_opt_out','skipped_no_consent','cancelled')")
    else:
        where.append("r.status IN ('sent_manual','sent_provider','failed')")
    rows = conn.all("SELECT r.*, p.first_name, p.last_name, p.phone, p.email, a.start_at, t.name AS template, b.name AS branch "
                    "FROM reminders r LEFT JOIN patients p ON p.id = r.patient_id LEFT JOIN appointments a ON a.id = r.appointment_id "
                    "LEFT JOIN message_templates t ON t.id = r.template_id LEFT JOIN branches b ON b.id = r.branch_id "
                    f"WHERE {' AND '.join(where)} ORDER BY r.scheduled_for " + ("DESC" if view in ("sent", "skipped") else "") + " LIMIT 300", args)
    rules = conn.all("SELECT r.*, t.name AS template FROM reminder_rules r JOIN message_templates t ON t.id = r.template_id ORDER BY r.offset_minutes")
    return render_template("staff/leads/reminders.html", rows=rows, view=view, rules=rules,
                           provider=get_provider("manual"))


@bp.route("/reminders/generate", methods=["POST"])
@require("reminders.send")
def reminders_generate():
    """Create reminder rows for confirmed upcoming appointments (idempotent). Nothing is sent."""
    conn = get_db()
    af, ap = branch_filter(g.user, "branch_id")
    appts = conn.all(f"SELECT id FROM appointments WHERE status = 'confirmed' AND start_at >= ? AND start_at < ? AND {af}",
                     [now_str(), fmt_dt(now() + timedelta(days=14)), *ap])
    created = 0
    with conn.transaction():
        for a in appts:
            created += schedule_appointment_reminders(conn, a["id"])
    flash(f"Checked {len(appts)} upcoming appointments; {created} new reminders queued for manual sending.", "success")
    return redirect(url_for("leads.reminders"))


@bp.route("/reminders/<int:rem_id>", methods=["POST"])
@require("reminders.send")
def reminder_update(rem_id):
    conn = get_db()
    r = conn.one("SELECT * FROM reminders WHERE id = ?", (rem_id,))
    if not r or not g.user.in_branch(r["branch_id"]):
        abort(404)
    action = request.form.get("action")
    if r["status"] != "pending":
        flash("This reminder was already handled.", "info")
        return redirect(url_for("leads.reminders"))
    if action == "sent":
        patient = conn.one("SELECT * FROM patients WHERE id = ?", (r["patient_id"],))
        ok, status = channel_allowed(patient, r["channel"])
        if not ok:
            conn.execute("UPDATE reminders SET status = ?, result_note = 'Preferences changed before sending' WHERE id = ?", (status, rem_id))
            flash("Not sent: the patient's contact preferences no longer allow this channel.", "warning")
            return redirect(url_for("leads.reminders"))
        result = get_provider(r["provider"]).send(r["channel"], "", r["rendered_body"])
        conn.execute("UPDATE reminders SET status = ?, sent_at = ?, sent_by = ?, result_note = ? WHERE id = ?",
                     (result.status, now_str(), g.user.id, clean(request.form.get("note"), 300) or result.note, rem_id))
        audit.record("reminder_sent_manual", "reminder", rem_id, f"{r['channel']} reminder recorded as sent", branch_id=r["branch_id"])
        flash("Recorded as sent.", "success")
    elif action == "failed":
        conn.execute("UPDATE reminders SET status = 'failed', sent_by = ?, sent_at = ?, result_note = ? WHERE id = ?",
                     (g.user.id, now_str(), clean(request.form.get("note"), 300) or "Could not deliver", rem_id))
        audit.record("reminder_failed", "reminder", rem_id, "Reminder delivery failed", branch_id=r["branch_id"])
        if g.user.can("followups.manage") and r["patient_id"]:
            conn.insert("follow_ups", {"branch_id": r["branch_id"], "patient_id": r["patient_id"], "appointment_id": r["appointment_id"],
                                       "kind": "other", "title": "Reminder failed — call patient to confirm visit",
                                       "due_at": now_str()[:16], "status": "open", "created_at": now_str(), "created_by": g.user.id})
        flash("Marked as failed. A call-back follow-up was created.", "success")
    elif action == "skip":
        conn.execute("UPDATE reminders SET status = 'cancelled', sent_by = ?, result_note = ? WHERE id = ?",
                     (g.user.id, clean(request.form.get("note"), 300) or "Skipped by staff", rem_id))
        flash("Reminder skipped.", "success")
    return redirect(url_for("leads.reminders"))


# ---------------------------------------------------------------------------
# Templates and reminder rules
# ---------------------------------------------------------------------------

@bp.route("/templates", methods=["GET", "POST"])
@require("leads.view", "templates.manage", any_of=True)
def templates():
    conn = get_db()
    if request.method == "POST":
        if not g.user.can("templates.manage"):
            abort(403)
        action = request.form.get("action")
        if action == "rule":
            rid = to_int(request.form.get("rule_id"))
            offset_h = to_int(request.form.get("offset_hours"))
            channel = request.form.get("channel")
            if offset_h is None or channel not in CHANNELS:
                flash("Enter hours before the appointment and a channel.", "error")
            else:
                vals = {"offset_minutes": -abs(offset_h) * 60, "channel": channel, "active": 1 if request.form.get("active") else 0,
                        "template_id": to_int(request.form.get("template_id"))}
                if rid:
                    conn.update("reminder_rules", rid, vals)
                else:
                    vals["name"] = clean(request.form.get("name"), 80) or f"{abs(offset_h)}h before"
                    vals["purpose"] = "appointment"
                    rid = conn.insert("reminder_rules", vals)
                audit.record("reminder_rule_saved", "reminder_rule", rid, "Saved reminder rule", vals)
                flash("Reminder timing saved.", "success")
            return redirect(url_for("leads.templates") + "#rules")
        tid = to_int(request.form.get("template_id"))
        body = clean(request.form.get("body"), 1500)
        name = clean(request.form.get("name"), 120)
        purpose = request.form.get("purpose")
        if not body or not name or purpose not in ("appointment_reminder", "follow_up", "lead_reply", "booking_ack"):
            flash("Name, purpose and text are required.", "error")
        elif tid:
            before = conn.one("SELECT * FROM message_templates WHERE id = ?", (tid,))
            conn.execute("UPDATE message_templates SET name = ?, body = ?, purpose = ?, active = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                         (name, body, purpose, 1 if request.form.get("active") else 0, now_str(), g.user.id, tid))
            audit.record("template_updated", "message_template", tid, f"Edited template {name}",
                         audit.diff(dict(before), {"body": body, "name": name}, ["body", "name"]))
            flash("Template saved.", "success")
        else:
            key = "custom_" + str((conn.scalar("SELECT MAX(id) FROM message_templates") or 0) + 1)
            tid = conn.insert("message_templates", {"key": key, "name": name, "purpose": purpose, "channel": "any", "body": body,
                                                    "active": 1, "updated_at": now_str(), "updated_by": g.user.id})
            audit.record("template_created", "message_template", tid, f"Created template {name}")
            flash("Template created.", "success")
        return redirect(url_for("leads.templates") + f"#t{tid or ''}")
    rows = conn.all("SELECT t.*, u.name AS editor FROM message_templates t LEFT JOIN users u ON u.id = t.updated_by ORDER BY t.purpose, t.name")
    sample = {"first_name": "Ana", "clinic": "Dental Haven", "branch": "Malolos", "branch_phone": "(branch number)",
              "date": "Monday, October 5", "time": "10:00 AM", "service": "Dental check-up", "dentist": "Dr. Santos"}
    for r in rows:
        r["preview"] = render(r["body"], sample)
    rules = conn.all("SELECT * FROM reminder_rules ORDER BY offset_minutes")
    return render_template("staff/leads/templates.html", rows=rows, placeholders=ALLOWED_PLACEHOLDERS, rules=rules)

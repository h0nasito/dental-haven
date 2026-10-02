"""Patient emails (super admin only): birthday greetings and announcement / promotion blasts. Public unsubscribe page."""
from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from .. import audit, patient_mail, settings
from ..auth import require_super_admin
from ..db import get_db
from ..util import clean, now_str, to_int, today

bp = Blueprint("emails", __name__)


def _test_send(conn, subject, body):
    configs = patient_mail.sender_configs(conn)
    if not configs:
        flash("Email isn't set up yet: add a branch Gmail and its app password on the server (see docs/INTEGRATIONS.md).", "error")
        return
    try:
        patient_mail.smtp_send(configs[0], g.user.email, "[TEST] " + subject, body)
    except Exception as exc:  # noqa: BLE001
        flash(f"The test email couldn't be sent ({type(exc).__name__}). Check the Gmail app password.", "error")
        return
    flash(f"Test email sent to {g.user.email} from {configs[0]['sender']}. Check the inbox (and spam folder).", "success")


@bp.route("/staff/admin/emails", methods=["GET", "POST"])
@require_super_admin
def index():
    conn = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "birthday":
            enabled = bool(request.form.get("enabled"))
            settings.put("birthday.enabled", enabled, g.user.id, conn)
            settings.put("birthday.subject", clean(request.form.get("subject"), 200) or patient_mail.DEFAULT_BIRTHDAY_SUBJECT, g.user.id, conn)
            settings.put("birthday.body", clean(request.form.get("body"), 5000) or patient_mail.DEFAULT_BIRTHDAY_BODY, g.user.id, conn)
            settings.put("birthday.promo", clean(request.form.get("promo"), 2000), g.user.id, conn)
            audit.record("birthday_email_settings", "setting", None, f"Birthday emails {'on' if enabled else 'off'}")
            flash("Birthday email saved." + (" Greetings go out every day from 8 AM." if enabled else " Automatic sending is off."), "success")
        elif action == "birthday_test":
            me = {"id": 0, "first_name": g.user.name.split()[0] if g.user.name else "there", "consent_marketing": 1}
            subject, body = patient_mail.birthday_message(conn, me)
            _test_send(conn, subject, body.split("\n\n—\n")[0] + "\n\n— (test: the real email ends with the unsubscribe link)")
        elif action == "limit":
            n = to_int(request.form.get("daily_limit"))
            if not n or not 20 <= n <= 1900:
                flash("Enter a number from 20 to 1,900 emails per account per day.", "error")
            else:
                settings.put("mail.daily_limit", n, g.user.id, conn)
                flash("Daily limit saved.", "success")
        return redirect(url_for("emails.index"))
    campaigns = conn.all("SELECT c.*, b.name AS branch, u.name AS by_name FROM email_campaigns c LEFT JOIN branches b ON b.id = c.branch_id "
                         "LEFT JOIN users u ON u.id = c.created_by ORDER BY c.id DESC LIMIT 100")
    for c in campaigns:
        c["stats"] = patient_mail.stats(conn, c["id"])
    where, args = patient_mail.audience_sql("birthday")
    bsql, bargs = patient_mail._birthday_today_sql(today())
    return render_template("staff/emails/index.html", campaigns=campaigns, kinds=patient_mail.KINDS,
                           senders=patient_mail.sender_configs(conn), limit=patient_mail.daily_limit(conn),
                           queue=patient_mail.stats(conn), demo=current_app.config["APP_ENV"] == "demo",
                           bday={"enabled": settings.get("birthday.enabled", conn),
                                 "subject": settings.get("birthday.subject", conn) or patient_mail.DEFAULT_BIRTHDAY_SUBJECT,
                                 "body": settings.get("birthday.body", conn) or patient_mail.DEFAULT_BIRTHDAY_BODY,
                                 "promo": settings.get("birthday.promo", conn) or "",
                                 "audience": patient_mail.audience_count(conn, "birthday"),
                                 "today": conn.scalar(f"SELECT COUNT(*) FROM patients p WHERE {where} AND {bsql}", [*args, *bargs])},
                           recent=conn.all("SELECT o.kind, o.status, o.sent_at, o.created_at, o.error, p.first_name, p.last_name FROM email_outbox o "
                                           "JOIN patients p ON p.id = o.patient_id WHERE o.kind = 'birthday' ORDER BY o.id DESC LIMIT 10"))


@bp.route("/staff/admin/emails/new", methods=["GET", "POST"])
@bp.route("/staff/admin/emails/<int:cid>", methods=["GET", "POST"])
@require_super_admin
def campaign(cid=None):
    conn = get_db()
    c = conn.one("SELECT * FROM email_campaigns WHERE id = ?", (cid,)) if cid else None
    if cid and not c:
        abort(404)
    branches = conn.all("SELECT id, name FROM branches WHERE active = 1 ORDER BY sort_order")
    v = dict(c) if c else {"kind": request.args.get("kind") if request.args.get("kind") in ("announcement", "promotion") else "announcement",
                           "subject": "", "body": "Hi {first_name},\n\n", "branch_id": None, "status": "draft"}
    errors = {}
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "cancel" and c and c["status"] == "queued":
            n = conn.execute("UPDATE email_outbox SET status = 'cancelled', error = 'Campaign cancelled' WHERE campaign_id = ? AND status = 'pending'",
                             (c["id"],)).rowcount
            conn.execute("UPDATE email_campaigns SET status = 'cancelled', updated_at = ? WHERE id = ?", (now_str(), c["id"]))
            audit.record("email_campaign_cancelled", "email_campaign", c["id"], f"Cancelled email: {c['subject']} ({n} not sent)")
            flash(f"Cancelled. {n} email(s) that hadn't gone out yet won't be sent.", "success")
            return redirect(url_for("emails.campaign", cid=c["id"]))
        if c and c["status"] != "draft":
            abort(400)
        v.update({"kind": request.form.get("kind") if request.form.get("kind") in ("announcement", "promotion") else "announcement",
                  "subject": clean(request.form.get("subject"), 200), "body": clean(request.form.get("body"), 20000),
                  "branch_id": to_int(request.form.get("branch_id")) or None})
        if v["branch_id"] and not any(b["id"] == v["branch_id"] for b in branches):
            v["branch_id"] = None
        if len(v["subject"]) < 3:
            errors["subject"] = "Write a subject."
        if len(v["body"].replace("Hi {first_name},", "").strip()) < 10:
            errors["body"] = "Write the message."
        if not errors:
            vals = {"kind": v["kind"], "subject": v["subject"], "body": v["body"], "branch_id": v["branch_id"], "updated_at": now_str()}
            if c:
                conn.update("email_campaigns", c["id"], vals)
                cid = c["id"]
            else:
                cid = conn.insert("email_campaigns", {**vals, "status": "draft", "created_by": g.user.id, "created_at": now_str()})
            c = conn.one("SELECT * FROM email_campaigns WHERE id = ?", (cid,))
            if action == "test":
                me = {"id": 0, "first_name": g.user.name.split()[0] if g.user.name else "there"}
                subject = patient_mail.personalise(c["subject"], me)
                body = patient_mail.personalise(c["body"], me) + "\n\n— (test: the real email ends with the unsubscribe link)"
                _test_send(conn, subject, body)
            elif action == "send":
                if request.form.get("confirm_count") != str(patient_mail.audience_count(conn, c["kind"], c["branch_id"])):
                    flash("The number of recipients changed. Check it and click Send again.", "error")
                else:
                    with conn.transaction():
                        n = patient_mail.queue_campaign(conn, c)
                        conn.execute("UPDATE email_campaigns SET status = 'queued', recipients = ?, queued_at = ?, updated_at = ? WHERE id = ?",
                                     (n, now_str(), now_str(), c["id"]))
                        audit.record("email_campaign_queued", "email_campaign", c["id"],
                                     f"{patient_mail.KINDS[c['kind']]} queued for {n} patient(s): {c['subject']}")
                    days = -(-n // max(1, patient_mail.daily_limit(conn) * max(1, len(patient_mail.sender_configs(conn)))))
                    flash(f"Queued for {n} patient(s). Sending starts within 5 minutes" +
                          (f" and takes about {days} day(s) because of the Gmail daily limit." if days > 1 else "."), "success")
            else:
                flash("Draft saved.", "success")
            return redirect(url_for("emails.campaign", cid=cid))
    count = patient_mail.audience_count(conn, v["kind"], v["branch_id"])
    counts = {k: {b["id"]: patient_mail.audience_count(conn, k, b["id"]) for b in branches} | {None: patient_mail.audience_count(conn, k)}
              for k in ("announcement", "promotion")}
    return render_template("staff/emails/campaign.html", c=c, v=v, errors=errors, branches=branches, count=count, counts=counts,
                           kinds=patient_mail.KINDS, stats=patient_mail.stats(conn, c["id"]) if c else None,
                           senders=patient_mail.sender_configs(conn))


# ---------------------------------------------------------------------------
# Public: unsubscribe (link in every patient email). No sign-in; the link itself is the proof.
# ---------------------------------------------------------------------------

@bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    conn = get_db()
    pid = patient_mail.read_unsubscribe_token(token)
    p = conn.one("SELECT id, first_name, consent_marketing, news_opt_out FROM patients WHERE id = ?", (pid,)) if pid else None
    if not p:
        return render_template("public/unsubscribe.html", p=None, done=None), 404
    done = None
    if request.method == "POST":
        choice = request.form.get("choice")
        if choice == "promotions":
            conn.execute("UPDATE patients SET consent_marketing = 0, updated_at = ? WHERE id = ?", (now_str(), p["id"]))
            done = "promotions"
        elif choice == "all":
            conn.execute("UPDATE patients SET consent_marketing = 0, news_opt_out = 1, updated_at = ? WHERE id = ?", (now_str(), p["id"]))
            done = "all"
        if done:
            conn.execute("UPDATE email_outbox SET status = 'cancelled', error = 'Unsubscribed' WHERE patient_id = ? AND status = 'pending' "
                         "AND (kind = 'promotion' OR ? = 'all')", (p["id"], done))
            audit.record("patient_unsubscribed", "patient", p["id"], f"Patient unsubscribed from {'promotions' if done == 'promotions' else 'all clinic emails'}",
                         actor_id=None)
    # Only the first name is shown: whoever has the link already has the email.
    return render_template("public/unsubscribe.html", p=p, done=done, token=token)

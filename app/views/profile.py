"""My profile: profile picture (and a link to change the password). Admins with users.manage can set others' pictures."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit, avatars
from ..auth import login_required
from ..db import get_db

bp = Blueprint("profile", __name__)


@bp.route("/staff/account", methods=["GET"])
@login_required
def account():
    conn = get_db()
    me = conn.one("SELECT u.*, e.position FROM users u LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = ?", (g.user.id,))
    approver = any(g.user.can(p) for p in APPROVAL_PERMS)
    return render_template("staff/profile/account.html", me=me, approver=approver)


APPROVAL_PERMS = ("leave.approve", "reimburse.approve", "attendance.manage", "overtime.approve", "payroll.approve")


@bp.route("/staff/account/emails", methods=["POST"])
@login_required
def set_emails():
    """Turn the morning approval reminder email on or off for yourself."""
    on = 1 if request.form.get("notify_approvals") == "1" else 0
    conn = get_db()
    with conn.transaction():
        conn.execute("UPDATE users SET notify_approvals = ? WHERE id = ?", (on, g.user.id))
        audit.record("approval_emails_" + ("on" if on else "off"), "user", g.user.id,
                     "Turned " + ("on" if on else "off") + " approval reminder emails")
    flash("Approval reminder emails turned " + ("on." if on else "off."), "success")
    return redirect(url_for("profile.account"))


@bp.route("/staff/account/avatar", methods=["POST"])
@login_required
def set_avatar():
    conn = get_db()
    uid = int(request.form.get("user_id") or g.user.id)
    if uid != g.user.id and not (g.user.is_super_admin or g.user.can("users.manage")):
        abort(403)
    row = conn.one("SELECT id, avatar FROM users WHERE id = ?", (uid,))
    if not row:
        abort(404)
    back = request.form.get("next") or url_for("profile.account")
    if not back.startswith("/") or back.startswith("//"):
        back = url_for("profile.account")
    if request.form.get("action") == "remove":
        with conn.transaction():
            conn.execute("UPDATE users SET avatar = NULL WHERE id = ?", (uid,))
            audit.record("avatar_removed", "user", uid, "Removed profile picture")
        avatars.delete(row["avatar"])
        flash("Profile picture removed.", "success")
        return redirect(back)
    f = request.files.get("photo")
    if not f or not f.filename:
        flash("Choose a picture first.", "error")
        return redirect(back)
    name, err = avatars.save(f)
    if err:
        flash(err, "error")
        return redirect(back)
    with conn.transaction():
        conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (name, uid))
        audit.record("avatar_changed", "user", uid, "Changed profile picture")
    avatars.delete(row["avatar"])
    flash("Profile picture saved.", "success")
    return redirect(back)


@bp.route("/media/avatar/<int:user_id>/<name>.jpg")
@login_required
def avatar_img(user_id, name):
    """Staff-only. The file name changes with every new picture, so it can be cached."""
    row = get_db().one("SELECT avatar FROM users WHERE id = ?", (user_id,))
    if not row or row["avatar"] != f"{name}.jpg":
        abort(404)
    p = avatars.path(row["avatar"])
    if not p:
        abort(404)
    resp = send_file(p, mimetype="image/jpeg", max_age=7 * 86400)
    resp.headers["Cache-Control"] = "private, max-age=604800"
    return resp


@bp.app_template_global("avatar_url")
def _avatar_url(user_id, name):
    return avatars.url(user_id, name)


@bp.app_template_filter("initials")
def _initials(full_name):
    return avatars.initials(full_name)


@bp.app_template_filter("avatar_color")
def _avatar_color(user_id):
    return avatars.color(user_id)

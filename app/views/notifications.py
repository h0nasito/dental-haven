"""The notification bell: list, open (mark read and follow the link), mark all read."""
from __future__ import annotations

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from ..auth import login_required
from ..db import get_db
from ..util import now_str

bp = Blueprint("notifications", __name__, url_prefix="/staff/notifications")


@bp.route("")
@login_required
def index():
    rows = get_db().all("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 200", (g.user.id,))
    return render_template("staff/notifications.html", rows=rows)


@bp.route("/<int:nid>/open", methods=["POST"])
@login_required
def open_(nid):
    conn = get_db()
    n = conn.one("SELECT * FROM notifications WHERE id = ? AND user_id = ?", (nid, g.user.id))
    if not n:
        abort(404)
    if not n["read_at"]:
        conn.execute("UPDATE notifications SET read_at = ? WHERE id = ?", (now_str(), nid))
    link = n["link"] or ""
    # internal links only
    return redirect(link if link.startswith("/staff/") and "//" not in link else url_for("notifications.index"))


@bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    get_db().execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL", (now_str(), g.user.id))
    return redirect(request.referrer if (request.referrer or "").startswith(request.host_url + "staff/") else url_for("notifications.index"))

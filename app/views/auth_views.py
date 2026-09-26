from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import (attempt_login, end_session, hash_password, login_required, password_problems, revoke_user_sessions,
                    start_session, verify_password)
from ..db import get_db

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/staff") and "//" not in target and "\\" not in target:
        return target
    return url_for("dash.home")


@bp.route("/staff/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("dash.home"))
    error = None
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "")[:200]
        user, error = attempt_login(email, request.form.get("password", ""))
        if user:
            start_session(user["id"])
            audit.record("login", "user", user["id"], "Signed in", actor_id=user["id"])
            return redirect(_safe_next(request.args.get("next")))
    return render_template("auth/login.html", error=error, email=email)


@bp.route("/staff/logout", methods=["POST"])
def logout():
    end_session()
    flash("You have signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/staff/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    errors = []
    if request.method == "POST":
        conn = get_db()
        row = conn.one("SELECT password_hash FROM users WHERE id = ?", (g.user.id,))
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not verify_password(row["password_hash"], current):
            errors.append("Your current password is incorrect.")
        errors += password_problems(new)
        if new != confirm:
            errors.append("The new passwords do not match.")
        if new and new == current:
            errors.append("Choose a password different from the current one.")
        if not errors:
            conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                         (hash_password(new), g.user.id))
            audit.record("password_changed", "user", g.user.id, "Changed own password")
            revoke_user_sessions(g.user.id)
            start_session(g.user.id)
            flash("Password updated.", "success")
            return redirect(url_for("dash.home"))
    return render_template("auth/password.html", errors=errors, forced=g.user.must_change_password)

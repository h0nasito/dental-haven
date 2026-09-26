"""Authentication, server-side sessions, CSRF and permission decorators."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .permissions import load_role_permissions
from .util import now, now_str, parse_dt

SESSION_KEY = "sid"
MAX_FAILED = 5
LOCK_MINUTES = 15
MIN_PASSWORD = 10


def hash_password(password: str) -> str:
    return generate_password_hash(password, method="scrypt")


def verify_password(pw_hash: str, password: str) -> bool:
    return check_password_hash(pw_hash, password)


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"Use at least {MIN_PASSWORD} characters.")
    if password.lower() == password or password.upper() == password:
        problems.append("Mix upper- and lower-case letters.")
    if not any(c.isdigit() for c in password):
        problems.append("Include at least one number.")
    return problems


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CurrentUser:
    def __init__(self, row, perms: set[str], branch_ids: list[int], active_branch_id: int | None):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.role = row["role"]
        self.must_change_password = bool(row["must_change_password"])
        self.perms = perms
        self.branch_ids = branch_ids
        self.active_branch_id = active_branch_id if active_branch_id in branch_ids else None

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    @property
    def branch_selected(self) -> bool:
        return self.active_branch_id is not None

    @property
    def scope_branch_ids(self) -> list[int]:
        """Branches currently in view: the selected branch, or all authorised branches."""
        return [self.active_branch_id] if self.active_branch_id else list(self.branch_ids)

    @property
    def own_schedule_only(self) -> bool:
        """Dentists see only their own appointments unless granted 'View Associates'."""
        return self.role == "dentist" and "calendar.associates" not in self.perms

    def can(self, perm: str) -> bool:
        return perm in self.perms

    def in_branch(self, branch_id) -> bool:
        return branch_id in self.branch_ids


def load_user():
    g.user = None
    sid = session.get(SESSION_KEY)
    if not sid:
        return
    conn = get_db()
    s = conn.one("SELECT * FROM sessions WHERE id_hash = ?", (_token_hash(sid),))
    if not s:
        session.pop(SESSION_KEY, None)
        return
    current = now()
    idle = timedelta(minutes=current_app.config["SESSION_IDLE_MINUTES"])
    if parse_dt(s["expires_at"]) < current or parse_dt(s["last_seen_at"]) + idle < current:
        conn.execute("DELETE FROM sessions WHERE id_hash = ?", (s["id_hash"],))
        session.pop(SESSION_KEY, None)
        return
    row = conn.one("SELECT * FROM users WHERE id = ? AND active = 1", (s["user_id"],))
    if not row:
        conn.execute("DELETE FROM sessions WHERE id_hash = ?", (s["id_hash"],))
        session.pop(SESSION_KEY, None)
        return
    if row["role"] == "super_admin":
        branch_ids = [r["id"] for r in conn.all("SELECT id FROM branches WHERE active = 1 ORDER BY sort_order")]
    else:
        branch_ids = [
            r["branch_id"]
            for r in conn.all(
                "SELECT ub.branch_id FROM user_branches ub JOIN branches b ON b.id = ub.branch_id "
                "WHERE ub.user_id = ? AND b.active = 1 ORDER BY b.sort_order",
                (row["id"],),
            )
        ]
    perms = load_role_permissions(conn, row["role"])
    g.user = CurrentUser(row, perms, branch_ids, s["active_branch_id"])
    g.session_hash = s["id_hash"]
    conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id_hash = ?", (now_str(), s["id_hash"]))


def start_session(user_id: int):
    token = secrets.token_urlsafe(32)
    conn = get_db()
    ts = now()
    conn.execute(
        "INSERT INTO sessions (id_hash, user_id, created_at, last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (
            _token_hash(token), user_id, ts.strftime("%Y-%m-%d %H:%M:%S"), ts.strftime("%Y-%m-%d %H:%M:%S"),
            (ts + timedelta(hours=current_app.config["SESSION_MAX_HOURS"])).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    session.clear()
    session.permanent = True
    session[SESSION_KEY] = token
    session["csrf"] = secrets.token_urlsafe(24)


def end_session():
    sid = session.get(SESSION_KEY)
    if sid:
        get_db().execute("DELETE FROM sessions WHERE id_hash = ?", (_token_hash(sid),))
    session.clear()


def revoke_user_sessions(user_id: int):
    get_db().execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def attempt_login(email: str, password: str):
    """Returns (user_row, error_message)."""
    conn = get_db()
    row = conn.one("SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),))
    generic = "Email or password is incorrect."
    if not row:
        verify_password(hash_password("timing-equaliser"), password)  # keep timing similar
        return None, generic
    if row["locked_until"] and parse_dt(row["locked_until"]) > now():
        return None, "Too many failed attempts. Try again in a few minutes or ask a super admin."
    if not row["active"]:
        return None, generic
    if not verify_password(row["password_hash"], password):
        failed = row["failed_logins"] + 1
        locked = None
        if failed >= MAX_FAILED:
            locked = (now() + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
            failed = 0
        conn.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?", (failed, locked, row["id"]))
        return None, generic
    conn.execute(
        "UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
        (now_str(), row["id"]),
    )
    return row, None


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if current_app.config.get("TESTING") and current_app.config.get("CSRF_DISABLED"):
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="Your form expired. Please go back, refresh the page and try again.")


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.user.must_change_password and request.endpoint not in ("auth.change_password", "auth.logout"):
            return redirect(url_for("auth.change_password"))
        return view(*args, **kwargs)

    return wrapped


def require(*perms: str, any_of: bool = False):
    """Server-side permission check. Aborts with 403 when the user lacks access."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            checks = [g.user.can(p) for p in perms]
            ok = any(checks) if any_of else all(checks)
            if not ok:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_super_admin(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user.is_super_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped

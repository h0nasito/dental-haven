"""Command-line tasks: `flask --app wsgi <command>`."""
from __future__ import annotations

import getpass
import os

import click

from .db import standalone_connection


def _conn(app):
    return standalone_connection(app.config["DATABASE_URL"])


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Apply database migrations."""
        from .migrate import run_migrations
        conn = _conn(app)
        done = run_migrations(conn)
        click.echo("Database up to date." if not done else f"Applied {len(done)} migration(s).")

    @app.cli.command("seed-base")
    def seed_base_cmd():
        """Branches, services, placeholder website content, templates and role defaults. Safe for production."""
        from .seed import seed_base
        with app.app_context():
            conn = _conn(app)
            seed_base(conn)
        click.echo("Base configuration seeded (placeholders marked '[to be confirmed]').")

    @app.cli.command("seed-demo")
    @click.option("--password", default=None, help="Password for all demo users (default: random, printed once).")
    def seed_demo_cmd(password):
        """Synthetic demo users, patients, appointments, billing and attendance. Never use in production."""
        if app.config["APP_ENV"] == "production":
            raise click.ClickException("Refusing to load demo data when APP_ENV=production.")
        from .seed import seed_demo
        with app.app_context():
            conn = _conn(app)
            pw = seed_demo(conn, password or os.environ.get("SEED_DEMO_PASSWORD"))
        click.echo(f"Demo data loaded. All demo accounts use the password: {pw}")
        click.echo("Accounts: admin@demo.dentalhaven.test, dentist.malolos@..., reception.malolos@..., staff.malolos@... (see README).")

    @app.cli.command("create-superadmin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    def create_superadmin(email, name):
        """Create the first super admin (interactive password prompt)."""
        from .auth import hash_password, password_problems
        from .util import now_str
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            raise click.ClickException("Passwords do not match.")
        problems = password_problems(pw)
        if problems:
            raise click.ClickException(" ".join(problems))
        conn = _conn(app)
        if conn.one("SELECT id FROM users WHERE lower(email) = lower(?)", (email,)):
            raise click.ClickException("A user with that email already exists.")
        with app.app_context():
            uid = conn.insert("users", {"email": email.lower(), "name": name, "password_hash": hash_password(pw), "role": "super_admin",
                                        "active": 1, "must_change_password": 0, "created_at": now_str()})
            from . import audit
            audit.record("user_created", "user", uid, f"Created super admin {email} via CLI", actor_id=None, conn=conn)
        click.echo("Super admin created.")

    @app.cli.command("ensure-admin")
    def ensure_admin():
        """Create the first super admin from INITIAL_ADMIN_EMAIL / INITIAL_ADMIN_NAME / INITIAL_ADMIN_PASSWORD,
        only if no active super admin exists yet. They must change the password at first sign-in."""
        from .auth import hash_password, password_problems
        from .util import now_str
        conn = _conn(app)
        if conn.one("SELECT id FROM users WHERE role = 'super_admin' AND active = 1"):
            click.echo("A super admin already exists; INITIAL_ADMIN_* settings are ignored (you can remove them).")
            return
        email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip().lower()
        name = os.environ.get("INITIAL_ADMIN_NAME", "").strip() or "Clinic administrator"
        pw = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
        if not email or not pw:
            click.echo("No super admin yet. Set INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD, then restart.", err=True)
            return
        problems = password_problems(pw)
        if problems:
            raise click.ClickException("INITIAL_ADMIN_PASSWORD: " + " ".join(problems))
        if conn.one("SELECT id FROM users WHERE lower(email) = ?", (email,)):
            raise click.ClickException(f"A user with {email} already exists but isn't an active super admin.")
        with app.app_context():
            uid = conn.insert("users", {"email": email, "name": name, "password_hash": hash_password(pw), "role": "super_admin",
                                        "active": 1, "must_change_password": 1, "created_at": now_str()})
            from . import audit
            audit.record("user_created", "user", uid, f"Created first super admin {email} from server settings", actor_id=None, conn=conn)
        click.echo(f"Created the first super admin: {email}. They must change the password at first sign-in.")

    @app.cli.command("generate-reminders")
    def generate_reminders():
        """Queue reminder rows for upcoming confirmed appointments (for a daily cron). Sends nothing."""
        from datetime import timedelta

        from .messaging import schedule_appointment_reminders
        from .util import fmt_dt, now, now_str
        with app.app_context():
            conn = _conn(app)
            appts = conn.all("SELECT id FROM appointments WHERE status = 'confirmed' AND start_at >= ? AND start_at < ?",
                             (now_str(), fmt_dt(now() + timedelta(days=14))))
            n = sum(schedule_appointment_reminders(conn, a["id"]) for a in appts)
        click.echo(f"Queued {n} reminder(s) for manual sending.")

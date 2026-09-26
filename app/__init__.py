"""Dental Haven clinic operations platform (Flask application factory)."""
from __future__ import annotations

import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, render_template, request

from .db import Database, close_db

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Minimal .env loader (no third-party dependency). Existing env vars win."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def create_app(test_config: dict | None = None) -> Flask:
    _load_dotenv()
    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    env = os.environ.get("APP_ENV", "development")
    # DATA_DIR: one folder (e.g. a Render persistent disk) for everything that must survive restarts and deploys.
    data_dir = os.environ.get("DATA_DIR", "").strip()
    base_data = Path(data_dir) if data_dir else BASE_DIR / "instance"
    secret = os.environ.get("SECRET_KEY")
    if not secret:
        if env in ("production", "demo"):
            raise RuntimeError("SECRET_KEY must be set in production (see .env.example).")
        secret = secrets.token_hex(32)  # dev only: sessions reset on restart
    app.config.update(
        APP_ENV=env,
        SECRET_KEY=secret,
        DATA_DIR=str(base_data),
        DATABASE_URL=os.environ.get("DATABASE_URL", f"sqlite:///{base_data / 'dental_haven.db'}"),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", str(base_data / "uploads")),
        # Public website images (gallery). Served at /static/uploads/...
        PUBLIC_UPLOAD_DIR=os.environ.get("PUBLIC_UPLOAD_DIR", str(base_data / "public") if data_dir
                                         else str(BASE_DIR / "app" / "static" / "uploads")),
        IMPORT_DIR=str(base_data / "imports"),
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_REQUEST_MB", "100")) * 1024 * 1024,
        MAX_DOCUMENT_MB=int(os.environ.get("MAX_UPLOAD_MB", "10")),
        CLINIC_TIMEZONE=os.environ.get("CLINIC_TIMEZONE", "Asia/Manila"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=env in ("production", "demo"),
        SESSION_COOKIE_NAME="dh_session",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_IDLE_MINUTES=int(os.environ.get("SESSION_IDLE_MINUTES", "60")),
        SESSION_MAX_HOURS=int(os.environ.get("SESSION_MAX_HOURS", "12")),
        PUBLIC_RATE_LIMIT=int(os.environ.get("PUBLIC_RATE_LIMIT", "8")),  # form submissions / IP / hour
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PUBLIC_UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    @app.route("/static/uploads/<path:filename>")
    def public_upload(filename):
        """Gallery images, served from PUBLIC_UPLOAD_DIR (which may live outside the code, on a disk)."""
        from flask import send_from_directory
        return send_from_directory(app.config["PUBLIC_UPLOAD_DIR"], filename, max_age=86400)

    app.extensions["database"] = Database(app.config["DATABASE_URL"])
    app.teardown_appcontext(close_db)

    # Logging: never log request bodies or patient data.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    from . import auth
    from .jinja import register_jinja

    @app.before_request
    def _before():
        auth.load_user()
        auth.check_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'self'",
        )
        if request.path.startswith("/staff"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    register_jinja(app)

    if os.environ.get("TRUST_PROXY") == "1":
        # Behind one reverse proxy (Render, nginx): use its X-Forwarded-* headers for client IP and HTTPS.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def _demo_noindex(resp):
        if app.config["APP_ENV"] == "demo":
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    from .views import register_blueprints
    register_blueprints(app)

    @app.errorhandler(400)
    def _400(e):
        return render_template("error.html", code=400, message=getattr(e, "description", "Bad request")), 400

    @app.errorhandler(403)
    def _403(_e):
        return render_template("error.html", code=403,
                               message="You don't have access to this page or record."), 403

    @app.errorhandler(404)
    def _404(_e):
        return render_template("error.html", code=404, message="We couldn't find that page."), 404

    @app.errorhandler(413)
    def _413(_e):
        return render_template("error.html", code=413, message="That file is too large."), 413

    @app.errorhandler(500)
    def _500(_e):
        app.logger.error("Unhandled error on %s %s", request.method, request.endpoint)
        return render_template("error.html", code=500,
                               message="Something went wrong. The error was logged without patient details."), 500

    from .cli import register_cli
    register_cli(app)

    @app.context_processor
    def _ctx():
        return {"current_user": g.get("user"), "demo_mode": app.config["APP_ENV"] == "demo"}

    return app

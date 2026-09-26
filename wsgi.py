"""WSGI entry point: `flask --app wsgi run` for development; `gunicorn wsgi:app` (or waitress) in production."""
from app import create_app

app = create_app()

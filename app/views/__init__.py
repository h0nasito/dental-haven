from flask import Flask


def register_blueprints(app: Flask):
    from . import admin, auth_views, billing, chart, clinical_docs, dashboard, expenses, inventory, labs, leads, patients, people, public, quotes, reportcards, scheduling
    from .common import register_context

    for module in (public, auth_views, dashboard, scheduling, patients, chart, clinical_docs, leads, billing, quotes, expenses, inventory, labs, people, reportcards, admin):
        app.register_blueprint(module.bp)
    register_context(app)

from flask import Flask


def register_blueprints(app: Flask):
    from . import about, admin, deposits, inventory_orders, auth_views, billing, chart, clinical_docs, dashboard, emails, evaluations, expenses, fees, inventory, lab_works, labs, leads, notifications, patients, people, public, quotes, reportcards, scheduling, timeclock
    from .common import register_context

    for module in (public, auth_views, dashboard, scheduling, patients, chart, clinical_docs, leads, billing, quotes, expenses, evaluations, fees, inventory, labs, lab_works, notifications, people, timeclock, reportcards, emails, admin, about, inventory_orders, deposits):
        app.register_blueprint(module.bp)
    register_context(app)

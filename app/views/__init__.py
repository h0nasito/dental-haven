from flask import Flask


def register_blueprints(app: Flask):
    from . import about, admin, announcements, chat, profile, cases, deposits, leave, reimburse, inventory_orders, auth_views, billing, chart, clinical_docs, dashboard, emails, evaluations, expenses, fees, inventory, lab_expenses, lab_works, labs, leads, notifications, patients, people, public, quotes, reportcards, scheduling, timeclock
    from .common import register_context

    for module in (public, auth_views, dashboard, scheduling, patients, chart, clinical_docs, leads, billing, quotes, expenses, evaluations, fees, inventory, labs, lab_works, lab_expenses, notifications, people, timeclock, reportcards, emails, admin, about, inventory_orders, deposits, leave, reimburse, cases, announcements, chat, profile):
        app.register_blueprint(module.bp)
    register_context(app)

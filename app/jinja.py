"""Template helpers."""
from __future__ import annotations

from datetime import datetime

from markupsafe import Markup, escape

from .auth import csrf_token
from .permissions import ROLES
from .scheduling import SOURCES, STATUSES
from .util import WEEKDAYS, peso


def _nl2br(value):
    if not value:
        return ""
    return Markup("<br>").join(escape(value).split("\n"))


def _dt(value, fmt="%b %d, %Y %I:%M %p"):
    if not value:
        return "—"
    if isinstance(value, str):
        for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                value = datetime.strptime(value, f)
                if f == "%Y-%m-%d" and "%I" in fmt:
                    fmt = "%b %d, %Y"
                break
            except ValueError:
                continue
        else:
            return value
    return value.strftime(fmt).replace(" 0", " ")


def _time(value):
    return _dt(value, "%I:%M %p").lstrip("0") if value else "—"


def _date(value):
    return _dt(value, "%b %d, %Y") if value else "—"


def _label(value):
    return (value or "").replace("_", " ").capitalize()


def _phones(value):
    """'+63 927 277 7833 / +63 942 381 1106' -> [(display, 'tel:+639272777833'), ...]; ignores placeholders."""
    if not value or value.strip().startswith("["):
        return []
    out = []
    for part in value.split("/"):
        part = part.strip()
        digits = "".join(c for c in part if c.isdigit() or c == "+")
        if len(digits.replace("+", "")) >= 7:
            out.append((part, "tel:" + digits))
    return out


def _contact(value):
    """Show patient contact details only to users with 'View patient contact number, email address and home address'."""
    from flask import g
    user = g.get("user")
    if user is not None and not user.can("patients.contact"):
        return "Hidden" if value else "—"
    return value or "—"


def _opts(rows, key="id", label="name"):
    return [(r[key], r[label]) for r in rows]


def register_jinja(app):
    app.jinja_env.globals.update(
        csrf_token=csrf_token, ROLES=ROLES, APPT_STATUSES=STATUSES, SOURCES=SOURCES, WEEKDAYS=WEEKDAYS,
    )
    app.jinja_env.filters.update(contact=_contact, phones=_phones, opts=_opts, peso=peso, nl2br=_nl2br, dt=_dt, time=_time, date=_date, label=_label)

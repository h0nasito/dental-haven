"""Public website, appointment requests and inquiries."""
from __future__ import annotations

import re
import secrets
import threading
import time
from datetime import datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session,
                   url_for)

from .. import audit, settings
from ..db import get_db
from ..scheduling import available_slots, ensure_assignment, free_resource, service_duration, validate_slot
from ..util import clean, fmt_dt, now, now_str, parse_date, to_int, today

bp = Blueprint("public", __name__)

PHONE_RE = re.compile(r"^[0-9+()\-\s]{7,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_rate_lock = threading.Lock()
_rate: dict[str, list[float]] = {}


def _rate_limited() -> bool:
    """Simple per-IP limit for public form submissions (in-process). Use a shared store behind a load balancer."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
    limit = current_app.config["PUBLIC_RATE_LIMIT"]
    cutoff = time.time() - 3600
    with _rate_lock:
        hits = [t for t in _rate.get(ip, []) if t > cutoff]
        if len(hits) >= limit:
            _rate[ip] = hits
            return True
        hits.append(time.time())
        _rate[ip] = hits
    return False


def _looks_like_bot() -> bool:
    if request.form.get("website"):  # honeypot field, hidden from people
        return True
    started = to_int(request.form.get("started"), 0)
    return started and (time.time() - started) < 2


def content(key: str):
    row = get_db().one("SELECT * FROM site_content WHERE key = ?", (key,))
    return row or {"title": "", "body": ""}


from .. import stock_photos  # noqa: E402


@bp.app_context_processor
def _public_ctx():
    if request.path.startswith("/staff"):
        return {}
    conn = get_db()
    return {
        "site_branches": conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order"),
        "site_services": conn.all("SELECT * FROM services WHERE active = 1 ORDER BY sort_order"),
        "content": content,
        "site_images": {r["key"]: r["image_path"] for r in conn.all("SELECT key, image_path FROM site_images")},
        "stock": stock_photos.url,
        "hours_lines": lambda b: _hours_summary(conn, b),
        "stock_samples": stock_photos.samples,
    }


@bp.app_template_filter("items")
def summary_items(text: str) -> list[str]:
    """'Check-ups, cleanings, and tooth fillings.' → ['Check-ups', 'Cleanings', 'Tooth fillings']."""
    text = (text or "").strip().rstrip(".")
    parts = [p.strip() for p in text.replace(", and ", ", ").split(",")] if "," in text else [p.strip() for p in text.split(" and ")]
    return [p[:1].upper() + p[1:] for p in parts if p]


@bp.app_template_filter("richtext")
def richtext(text: str):
    """Plain text → safe HTML. Blank line = new paragraph; '## ' line = heading; '- ' lines = bulleted list
    (a list can follow an intro line in the same paragraph)."""
    from markupsafe import Markup, escape
    if not text:
        return ""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        para, items = [], []

        def flush_para():
            if para:
                out.append("<p>" + "<br>".join(str(escape(x)) for x in para) + "</p>")
                para.clear()

        def flush_list():
            if items:
                out.append("<ul>" + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>")
                items.clear()

        for line in block.strip().split("\n"):
            st = line.strip()
            if st.startswith("## "):
                flush_para(); flush_list()
                out.append(f"<h2>{escape(st[3:])}</h2>")
            elif st.startswith("- "):
                flush_para()
                items.append(st[2:])
            else:
                flush_list()
                para.append(line)
        flush_para(); flush_list()
    return Markup("\n".join(out))


@bp.route("/")
def home():
    conn = get_db()
    testimonials = conn.all("SELECT t.*, b.name AS branch FROM testimonials t LEFT JOIN branches b ON b.id = t.branch_id "
                            "WHERE t.approved = 1 AND t.published = 1 ORDER BY t.id DESC LIMIT 6")
    # Featured case first, then before/after cases, then newest.
    works = conn.all("SELECT * FROM gallery_items WHERE published = 1 AND authorized = 1 AND image_path != '' "
                     "ORDER BY featured DESC, sort_order, CASE WHEN before_image_path != '' THEN 0 ELSE 1 END, id DESC LIMIT 24")
    # Spread cases across the page so each section shows different ones:
    # hero = featured case; specialty = next before/after cases; gallery = the rest.
    ba_all = [w for w in works if w["before_image_path"]]
    featured = ba_all[0] if ba_all else None
    ba_cases = ba_all[1:5] if len(ba_all) > 1 else ba_all[:1]
    shown = {w["id"] for w in ba_all[:5]}
    works = [w for w in works if w["id"] not in shown] or works
    if len(works) > 3:
        works = works[:len(works) // 3 * 3]  # whole rows only (the first tile is double size); the rest are in the gallery
    from .admin import PORTFOLIO_CATEGORIES
    used = {w["category"] for w in works}
    filters = [(k, label) for k, label in PORTFOLIO_CATEGORIES if k in used]
    all_guides = conn.all(GUIDE_SELECT + " ORDER BY s.sort_order, gd.sort_order, gd.id")
    firsts, seen = [], set()
    for gd in all_guides:  # one guide per service first, so every service is represented
        if gd["service_id"] not in seen:
            seen.add(gd["service_id"]); firsts.append(gd)
    guides = (firsts + [gd for gd in all_guides if gd not in firsts])[:6]
    return render_template("public/home.html", guides=guides, testimonials=testimonials, works=works, filters=filters,
                           featured=featured, ba_cases=ba_cases,
                           **_booking_defaults(conn),
                           category_labels=dict(PORTFOLIO_CATEGORIES))


def _booking_defaults(conn):
    """Context for an empty appointment-request form (used on the home page)."""
    max_days = int(settings.get("booking.max_days_ahead", conn) or 60)
    return {
        "branches": conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order"),
        "services": conn.all("SELECT * FROM services WHERE active = 1 AND bookable_online = 1 ORDER BY sort_order"),
        "dentists": _bookable_dentists(conn), "slots": [], "errors": {},
        "v": {"branch_id": None, "service_id": None, "dentist_id": None, "date": "", "time": "", "full_name": "", "phone": "",
              "email": "", "message": "", "consent_privacy": False, "consent_contact": False},
        "min_date": today().isoformat(), "max_date": (today() + timedelta(days=max_days)).isoformat(),
        "started": int(time.time()),
    }


@bp.route("/services/<slug>")
def service(slug):
    s = get_db().one("SELECT * FROM services WHERE slug = ? AND active = 1", (slug,))
    if not s:
        abort(404)
    guides = get_db().all("SELECT * FROM guides WHERE service_id = ? AND published = 1 ORDER BY sort_order, id", (s["id"],))
    return render_template("public/service.html", s=s, guides=guides)


GUIDE_SELECT = ("SELECT gd.*, s.name AS service, s.slug AS service_slug, s.image_path AS service_image FROM guides gd "
                "LEFT JOIN services s ON s.id = gd.service_id WHERE gd.published = 1")


@bp.route("/guides")
def guides():
    rows = get_db().all(GUIDE_SELECT + " ORDER BY s.sort_order, gd.sort_order, gd.id")
    return render_template("public/guides.html", guides=rows)


@bp.route("/guides/<slug>")
def guide(slug):
    conn = get_db()
    gd = conn.one(GUIDE_SELECT + " AND gd.slug = ?", (slug,))
    if not gd:
        abort(404)
    related = conn.all(GUIDE_SELECT + " AND gd.id != ? ORDER BY CASE WHEN gd.service_id = ? THEN 0 ELSE 1 END, gd.sort_order LIMIT 3",
                       (gd["id"], gd["service_id"] or 0))
    return render_template("public/guide.html", gd=gd, related=related)


@bp.route("/branches/<slug>")
def branch(slug):
    conn = get_db()
    b = conn.one("SELECT * FROM branches WHERE slug = ? AND active = 1", (slug,))
    if not b:
        abort(404)
    hours = conn.all("SELECT * FROM branch_hours WHERE branch_id = ? ORDER BY weekday", (b["id"],))
    return render_template("public/branch.html", b=b, hours=hours)


@bp.route("/laboratory")
def lab():
    return render_template("public/lab.html")


@bp.route("/gallery")
def gallery():
    items = get_db().all("SELECT * FROM gallery_items WHERE published = 1 AND authorized = 1 AND image_path != '' ORDER BY id DESC")
    return render_template("public/gallery.html", items=items)


@bp.route("/feedback")
def feedback():
    items = get_db().all("SELECT t.*, b.name AS branch FROM testimonials t LEFT JOIN branches b ON b.id = t.branch_id "
                         "WHERE t.approved = 1 AND t.published = 1 ORDER BY t.id DESC")
    return render_template("public/feedback.html", items=items)


@bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")


@bp.route("/contact")
def contact():
    return redirect(url_for("public.inquire"))


# ---------------------------------------------------------------------------
# Appointment requests
# ---------------------------------------------------------------------------

def _bookable_dentists(conn, branch_id=None):
    if branch_id:
        return conn.all("SELECT u.id, u.name FROM users u JOIN user_branches ub ON ub.user_id = u.id "
                        "WHERE u.role = 'dentist' AND u.active = 1 AND ub.branch_id = ? ORDER BY u.name", (branch_id,))
    return conn.all("SELECT id, name FROM users WHERE role = 'dentist' AND active = 1 ORDER BY name")


@bp.route("/book/slots")
def book_slots():
    conn = get_db()
    branch_id = to_int(request.args.get("branch_id"))
    service_id = to_int(request.args.get("service_id"))
    dentist_id = to_int(request.args.get("dentist_id"))
    day = parse_date(request.args.get("date"))
    max_days = int(settings.get("booking.max_days_ahead", conn) or 60)
    if not (branch_id and service_id and day) or day < today() or day > today() + timedelta(days=max_days):
        return jsonify({"slots": [], "labels": []})
    if not conn.one("SELECT id FROM branches WHERE id = ? AND active = 1", (branch_id,)) or \
            not conn.one("SELECT id FROM services WHERE id = ? AND active = 1 AND bookable_online = 1", (service_id,)):
        return jsonify({"slots": [], "labels": []})
    if dentist_id and not any(d["id"] == dentist_id for d in _bookable_dentists(conn, branch_id)):
        dentist_id = None
    slots = available_slots(conn, branch_id=branch_id, service_id=service_id, day=day, dentist_id=dentist_id)
    labels = [datetime.strptime(s, "%H:%M").strftime("%I:%M %p").lstrip("0") for s in slots]
    resp = jsonify({"slots": slots, "labels": labels})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/book", methods=["GET", "POST"])
def book():
    conn = get_db()
    services = conn.all("SELECT * FROM services WHERE active = 1 AND bookable_online = 1 ORDER BY sort_order")
    branches = conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")
    max_days = int(settings.get("booking.max_days_ahead", conn) or 60)
    v = {"branch_id": to_int(request.args.get("branch")), "service_id": to_int(request.args.get("service")),
         "dentist_id": None, "date": "", "time": "", "full_name": "", "phone": "", "email": "", "message": "",
         "consent_privacy": False, "consent_contact": False}
    errors: dict = {}
    slots = []
    if request.method == "POST":
        if _looks_like_bot():
            return redirect(url_for("public.book_received"))
        v = {
            "branch_id": to_int(request.form.get("branch_id")), "service_id": to_int(request.form.get("service_id")),
            "dentist_id": to_int(request.form.get("dentist_id")), "date": clean(request.form.get("date"), 10),
            "time": clean(request.form.get("time"), 5), "full_name": clean(request.form.get("full_name"), 120),
            "phone": clean(request.form.get("phone"), 25), "email": clean(request.form.get("email"), 200).lower(),
            "message": clean(request.form.get("message"), 1000),
            "consent_privacy": bool(request.form.get("consent_privacy")),
            "consent_contact": bool(request.form.get("consent_contact")),
        }
        if request.form.get("show"):
            # No-JavaScript path: just show open times for the chosen branch/service/date.
            day = parse_date(v["date"])
            if day and v["branch_id"] and v["service_id"]:
                slots = available_slots(conn, branch_id=v["branch_id"], service_id=v["service_id"], day=day,
                                        dentist_id=v["dentist_id"])
            labels = [datetime.strptime(s, "%H:%M").strftime("%I:%M %p").lstrip("0") for s in slots]
            return render_template("public/book.html", v=v, errors={}, services=services, branches=branches,
                                   dentists=_bookable_dentists(conn), slots=list(zip(slots, labels)),
                                   min_date=today().isoformat(), max_date=(today() + timedelta(days=max_days)).isoformat(),
                                   started=int(time.time()))
        if _rate_limited():
            errors["_form"] = ["Too many requests from this connection. Please call the branch or try again later."]
        if not any(b["id"] == v["branch_id"] for b in branches):
            errors["branch_id"] = "Choose a branch."
        if not any(s["id"] == v["service_id"] for s in services):
            errors["service_id"] = "Choose a service."
        if v["dentist_id"] and not any(d["id"] == v["dentist_id"] for d in _bookable_dentists(conn, v["branch_id"])):
            errors["dentist_id"] = "That dentist isn't available at this branch."
        day = parse_date(v["date"])
        if not day or day < today() or day > today() + timedelta(days=max_days):
            errors["date"] = f"Choose a date within the next {max_days} days."
        if not re.match(r"^\d{2}:\d{2}$", v["time"]):
            errors["time"] = "Choose an available time."
        if len(v["full_name"]) < 2:
            errors["full_name"] = "Enter your name."
        if not PHONE_RE.match(v["phone"]):
            errors["phone"] = "Enter a mobile number we can reach you on."
        if v["email"] and not EMAIL_RE.match(v["email"]):
            errors["email"] = "Check the email address."
        if not v["consent_privacy"]:
            errors["consent_privacy"] = "Please agree to the privacy notice so we can process your request."
        start = None
        if not errors:
            start = datetime.strptime(f"{v['date']} {v['time']}", "%Y-%m-%d %H:%M")
            allowed = available_slots(conn, branch_id=v["branch_id"], service_id=v["service_id"], day=day,
                                      dentist_id=v["dentist_id"])
            if v["time"] not in allowed:
                errors["time"] = "That time is no longer available. Please pick another."
        if not errors:
            ref = _new_ref(conn)
            auto = bool(settings.get("booking.auto_confirm", conn))
            with conn.transaction(immediate=True):
                req_id = conn.insert("booking_requests", {
                    "ref_code": ref, "full_name": v["full_name"], "phone": v["phone"], "email": v["email"],
                    "branch_id": v["branch_id"], "service_id": v["service_id"], "dentist_id": v["dentist_id"],
                    "preferred_start": fmt_dt(start), "message": v["message"],
                    "consent_privacy": 1, "consent_contact": 1 if v["consent_contact"] else 0,
                    "status": "pending", "created_at": now_str(),
                })
                confirmed = False
                if auto:
                    confirmed = _auto_confirm(conn, req_id, v, start)
                audit.record("booking_requested", "booking_request", req_id,
                             f"Online request {ref}" + (" (auto-confirmed)" if confirmed else ""),
                             branch_id=v["branch_id"], actor_id=None)
            session["last_booking"] = {"ref": ref, "confirmed": confirmed}
            return redirect(url_for("public.book_received"))
        if day and v["branch_id"] and v["service_id"]:
            slots = available_slots(conn, branch_id=v["branch_id"], service_id=v["service_id"], day=day,
                                    dentist_id=v["dentist_id"])
    elif request.args.get("date") and v["branch_id"] and v["service_id"]:
        day = parse_date(request.args.get("date"))
        v["date"] = request.args.get("date")
        v["dentist_id"] = to_int(request.args.get("dentist"))
        if day:
            slots = available_slots(conn, branch_id=v["branch_id"], service_id=v["service_id"], day=day,
                                    dentist_id=v["dentist_id"])
    labels = [datetime.strptime(s, "%H:%M").strftime("%I:%M %p").lstrip("0") for s in slots]
    return render_template("public/book.html", v=v, errors=errors, services=services, branches=branches,
                           dentists=_bookable_dentists(conn), slots=list(zip(slots, labels)),
                           min_date=today().isoformat(), max_date=(today() + timedelta(days=max_days)).isoformat(),
                           started=int(time.time()))


def _new_ref(conn) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        ref = "DH-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not conn.one("SELECT id FROM booking_requests WHERE ref_code = ?", (ref,)):
            return ref


def _auto_confirm(conn, req_id, v, start) -> bool:
    """Only when the clinic enables auto-confirm: create a patient record and a confirmed appointment
    if the slot is still free. Otherwise leave the request pending for staff."""
    minutes = service_duration(conn, v["service_id"], v["branch_id"], v["dentist_id"])
    end = start + timedelta(minutes=minutes)
    res_id, has_res = free_resource(conn, v["branch_id"], fmt_dt(start), fmt_dt(end))
    if has_res and res_id is None:
        return False
    if validate_slot(conn, branch_id=v["branch_id"], start=start, end=end, dentist_id=v["dentist_id"], resource_id=res_id):
        return False
    first, _, last = v["full_name"].partition(" ")
    from .patients import next_chart_no
    pid = conn.insert("patients", {
        "chart_no": next_chart_no(conn), "first_name": first, "last_name": last or "-", "phone": v["phone"],
        "email": v["email"], "preferred_branch_id": v["branch_id"], "consent_privacy": 1, "consent_privacy_at": now_str(),
        "contact_sms": 1 if v["consent_contact"] else 0, "contact_email": 1 if (v["consent_contact"] and v["email"]) else 0,
        "source": "website", "created_at": now_str(),
    })
    appt_id = conn.insert("appointments", {
        "patient_id": pid, "branch_id": v["branch_id"], "service_id": v["service_id"], "dentist_id": v["dentist_id"],
        "resource_id": res_id, "start_at": fmt_dt(start), "end_at": fmt_dt(end), "status": "confirmed",
        "source": "website", "booking_request_id": req_id, "created_at": now_str(),
    })
    ensure_assignment(conn, pid, v["dentist_id"])
    conn.execute("UPDATE booking_requests SET status='confirmed', appointment_id=?, patient_id=?, handled_at=? WHERE id=?",
                 (appt_id, pid, now_str(), req_id))
    return True


@bp.route("/book/received")
def book_received():
    info = session.pop("last_booking", None)
    return render_template("public/book_received.html", info=info)


# ---------------------------------------------------------------------------
# Inquiries (become leads)
# ---------------------------------------------------------------------------

@bp.route("/inquire", methods=["GET", "POST"])
def inquire():
    conn = get_db()
    services = conn.all("SELECT * FROM services WHERE active = 1 ORDER BY sort_order")
    branches = conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")
    v = {"full_name": "", "phone": "", "email": "", "branch_id": to_int(request.args.get("branch")),
         "service_id": to_int(request.args.get("service")), "message": "", "consent_privacy": False, "consent_contact": False}
    errors: dict = {}
    if request.method == "POST":
        if _looks_like_bot():
            return redirect(url_for("public.inquire_received"))
        v = {
            "full_name": clean(request.form.get("full_name"), 120), "phone": clean(request.form.get("phone"), 25),
            "email": clean(request.form.get("email"), 200).lower(), "branch_id": to_int(request.form.get("branch_id")),
            "service_id": to_int(request.form.get("service_id")), "message": clean(request.form.get("message"), 1500),
            "consent_privacy": bool(request.form.get("consent_privacy")),
            "consent_contact": bool(request.form.get("consent_contact")),
        }
        if _rate_limited():
            errors["_form"] = ["Too many messages from this connection. Please call the branch or try again later."]
        if len(v["full_name"]) < 2:
            errors["full_name"] = "Enter your name."
        if not v["phone"] and not v["email"]:
            errors["phone"] = "Give a mobile number or email so we can reply."
        if v["phone"] and not PHONE_RE.match(v["phone"]):
            errors["phone"] = "Check the mobile number."
        if v["email"] and not EMAIL_RE.match(v["email"]):
            errors["email"] = "Check the email address."
        if v["branch_id"] and not any(b["id"] == v["branch_id"] for b in branches):
            v["branch_id"] = None
        if v["service_id"] and not any(s["id"] == v["service_id"] for s in services):
            v["service_id"] = None
        if len(v["message"]) < 3:
            errors["message"] = "Tell us briefly how we can help."
        if not v["consent_privacy"]:
            errors["consent_privacy"] = "Please agree to the privacy notice so we can reply."
        if not errors:
            lead_id = conn.insert("leads", {
                "full_name": v["full_name"], "phone": v["phone"], "email": v["email"], "source": "website",
                "branch_id": v["branch_id"], "service_id": v["service_id"], "message": v["message"], "status": "new",
                "consent_contact": 1 if v["consent_contact"] else 0, "created_at": now_str(),
            })
            conn.execute("INSERT INTO lead_activities (lead_id, kind, body, created_at) VALUES (?, 'created', ?, ?)",
                         (lead_id, "Website inquiry form", now_str()))
            audit.record("lead_created", "lead", lead_id, "Website inquiry", branch_id=v["branch_id"], actor_id=None)
            return redirect(url_for("public.inquire_received"))
    return render_template("public/inquire.html", v=v, errors=errors, services=services, branches=branches,
                           started=int(time.time()))


# ---------------------------------------------------------------------------
# Website chat assistant (built-in: no outside service; answers from the site's own content)
# ---------------------------------------------------------------------------

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _t12(hm: str) -> str:
    h, m = int(hm[:2]), hm[3:5]
    return f"{(h - 1) % 12 + 1}{':' + m if m != '00' else ''} {'AM' if h < 12 else 'PM'}"


def _hours_summary(conn, branch) -> list[str]:
    text = (branch["hours_text"] or "").strip()
    if text and not text.startswith("["):
        return [line.strip() for line in text.splitlines() if line.strip()]
    rows = {r["weekday"]: r for r in conn.all("SELECT * FROM branch_hours WHERE branch_id = ?", (branch["id"],))}
    groups = []  # [start_day, end_day, label]
    for wd in range(7):
        r = rows.get(wd)
        label = "Closed" if not r or r["closed"] else f"{_t12(r['open_time'])} – {_t12(r['close_time'])}"
        if groups and groups[-1][2] == label and groups[-1][1] == wd - 1:
            groups[-1][1] = wd
        else:
            groups.append([wd, wd, label])
    return [(_DAYS[a] if a == b else f"{_DAYS[a]}–{_DAYS[b]}") + f": {label}" for a, b, label in groups]


@bp.route("/chat/info.json")
def chat_info():
    """Everything the chat assistant may say, taken from the website's own content. No patient data."""
    from ..jinja import _phones
    conn = get_db()
    branches = [{
        "id": b["id"], "slug": b["slug"], "name": b["name"].split(" (")[0], "address": "" if (b["address"] or "").startswith("[") else b["address"],
        "phones": [d for d, _ in _phones(b["phone"])], "tel": [t for _, t in _phones(b["phone"])], "hours": _hours_summary(conn, b),
        "map": b["map_url"] or "", "facebook": b["facebook_url"] or "", "url": url_for("public.branch", slug=b["slug"]),
        "waze": b["waze_url"] or "",
        "week": [{"wd": r["weekday"], "open": r["open_time"], "close": r["close_time"], "closed": bool(r["closed"])}
                 for r in conn.all("SELECT * FROM branch_hours WHERE branch_id = ? ORDER BY weekday", (b["id"],))],
    } for b in conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")]
    services = [{"id": s["id"], "slug": s["slug"], "name": s["name"], "summary": s["summary"] or "", "url": url_for("public.service", slug=s["slug"])}
                for s in conn.all("SELECT * FROM services WHERE active = 1 ORDER BY sort_order")]
    guides = [{"slug": g["slug"], "title": g["title"], "service": g["service_slug"] or "", "url": url_for("public.guide", slug=g["slug"])}
              for g in conn.all(GUIDE_SELECT + " ORDER BY gd.sort_order, gd.id")]
    # Guide sections, so the chat can answer from the articles (heading + text).
    sections = []
    for g in conn.all(GUIDE_SELECT + " ORDER BY gd.sort_order, gd.id"):
        head, buf = g["title"], []
        for line in (g["body"] or "").splitlines() + ["## "]:
            if line.startswith("## "):
                text = " ".join(x.strip().lstrip("- ").strip() for x in buf if x.strip())
                if text:
                    sections.append({"guide": g["slug"], "title": g["title"], "heading": head, "text": text[:900],
                                     "url": url_for("public.guide", slug=g["slug"]), "service": g["service_slug"] or ""})
                head, buf = line[3:].strip(), []
            else:
                buf.append(line)
    # Prices: only once the clinic has confirmed its real price list; the demo shows them labelled as samples.
    demo = current_app.config.get("APP_ENV") == "demo"
    show = bool(settings.get("prices.show_public", conn))
    prices = []
    if show or demo:
        for p in conn.all("SELECT p.*, s.slug AS service FROM price_items p LEFT JOIN services s ON s.id = p.service_id "
                          "WHERE p.published = 1 ORDER BY s.sort_order, p.sort_order, p.id"):
            amount = f"₱{p['price_from_cents'] // 100:,}"
            if p["price_to_cents"]:
                amount += f" – ₱{p['price_to_cents'] // 100:,}"
            prices.append({"name": p["name"], "amount": amount, "range": bool(p["price_to_cents"]), "unit": p["unit"],
                           "fixed": (p["kind"] == "fixed") and not p["price_to_cents"], "note": p["note"] or "",
                           "service": p["service"] or "", "sample": bool(p["sample"]) or not show,
                           "kw": [k.strip() for k in (p["keywords"] + "," + p["name"]).lower().split(",") if k.strip()]})
    from ..chat_faq import FAQ
    from ..chat_procedures import GENERIC, PROCEDURES
    from ..chat_lifespan import LIFE, RESTO_WORDS, TOPICS as LIFE_TOPICS
    resp = jsonify({"life": LIFE, "life_topics": LIFE_TOPICS, "resto": RESTO_WORDS, "branches": branches, "services": services, "guides": guides, "sections": sections, "faq": FAQ,
                    "procedures": PROCEDURES, "generic": GENERIC, "slots": url_for("public.book_slots"),
                    "prices": prices, "book": url_for("public.book"),
                    "inquire": url_for("public.inquire"), "privacy": url_for("public.privacy")})
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@bp.route("/chat/message", methods=["POST"])
def chat_message():
    """The chat's 'send to our team' form. Saved as a lead (source: Website chat), exactly like the inquiry form.
    The chat conversation itself is never stored."""
    conn = get_db()
    if request.form.get("website"):
        return jsonify({"ok": True})
    v = {"full_name": clean(request.form.get("full_name"), 120), "phone": clean(request.form.get("phone"), 25),
         "email": clean(request.form.get("email"), 200).lower(), "branch_id": to_int(request.form.get("branch_id")),
         "message": clean(request.form.get("message"), 1500), "consent_privacy": bool(request.form.get("consent_privacy")),
         "consent_contact": bool(request.form.get("consent_contact"))}
    errors = {}
    if len(v["full_name"]) < 2:
        errors["full_name"] = "Enter your name."
    if not v["phone"] and not v["email"]:
        errors["phone"] = "Give a mobile number or email so we can reply."
    if v["phone"] and not PHONE_RE.match(v["phone"]):
        errors["phone"] = "Check the mobile number."
    if v["email"] and not EMAIL_RE.match(v["email"]):
        errors["email"] = "Check the email address."
    if len(v["message"]) < 3:
        errors["message"] = "Tell us briefly how we can help."
    if not v["consent_privacy"]:
        errors["consent_privacy"] = "Please agree to the privacy notice so we can reply."
    if not errors and _rate_limited():
        errors["_form"] = "Too many messages from this connection. Please call the branch or try again later."
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    if v["branch_id"] and not conn.one("SELECT id FROM branches WHERE id = ? AND active = 1", (v["branch_id"],)):
        v["branch_id"] = None
    lead_id = conn.insert("leads", {
        "full_name": v["full_name"], "phone": v["phone"], "email": v["email"], "source": "chat", "branch_id": v["branch_id"],
        "service_id": None, "message": v["message"], "status": "new", "consent_contact": 1 if v["consent_contact"] else 0,
        "created_at": now_str()})
    conn.execute("INSERT INTO lead_activities (lead_id, kind, body, created_at) VALUES (?, 'created', ?, ?)",
                 (lead_id, "Website chat", now_str()))
    audit.record("lead_created", "lead", lead_id, "Website chat inquiry", branch_id=v["branch_id"], actor_id=None)
    return jsonify({"ok": True})


@bp.route("/inquire/received")
def inquire_received():
    return render_template("public/inquire_received.html")

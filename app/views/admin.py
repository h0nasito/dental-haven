"""Super-admin and configuration screens: users, role access, audit, branches, services, schedules,
website content and system settings."""
from __future__ import annotations

import json
import re
import secrets

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit, settings
from ..auth import hash_password, require, revoke_user_sessions
from ..db import get_db
from ..permissions import CATALOG, LOCKED, PERM_KEYS, ROLE_DEFAULTS, ROLES, grantable
from ..util import WEEKDAYS, clean, hm_to_min, now_str, parse_money, to_int
from .common import paginate

bp = Blueprint("admin", __name__, url_prefix="/staff/admin")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _temp_password() -> str:
    # Readable temporary password meeting the policy; must be changed at first sign-in.
    return "Dh-" + secrets.token_urlsafe(9).replace("-", "x").replace("_", "y") + "7a"


# ---------------------------------------------------------------------------
# Users (super admin only)
# ---------------------------------------------------------------------------

@bp.route("/users")
@require("users.manage")
def users():
    conn = get_db()
    rows = conn.all("SELECT * FROM users ORDER BY active DESC, role, name")
    ub = {}
    for r in conn.all("SELECT ub.user_id, b.name FROM user_branches ub JOIN branches b ON b.id = ub.branch_id ORDER BY b.sort_order"):
        ub.setdefault(r["user_id"], []).append(r["name"])
    return render_template("staff/admin/users.html", users=rows, user_branches=ub)


def _user_form_values(form):
    return {
        "name": clean(form.get("name"), 120),
        "email": clean(form.get("email"), 200).lower(),
        "role": form.get("role", ""),
        "branches": [int(b) for b in form.getlist("branches") if str(b).isdigit()],
        "active": 1 if form.get("active") else 0,
        "is_employee": bool(form.get("is_employee")),
        "position": clean(form.get("position"), 80),
        "license_no": clean(form.get("license_no"), 40), "ptr_no": clean(form.get("ptr_no"), 40), "s2_no": clean(form.get("s2_no"), 40),
        "labs": [int(x) for x in form.getlist("labs") if str(x).isdigit()],
        "notify_email": 1 if form.get("notify_email") else 0,
    }


def _validate_user(conn, v, user_id=None):
    errors = {}
    if not v["name"]:
        errors["name"] = "Enter a name."
    if not EMAIL_RE.match(v["email"]):
        errors["email"] = "Enter a valid email."
    elif conn.one("SELECT id FROM users WHERE lower(email) = ? AND id != ?", (v["email"], user_id or 0)):
        errors["email"] = "Another user already uses this email."
    if v["role"] not in ROLES:
        errors["role"] = "Choose a role."
    valid_branches = {r["id"] for r in conn.all("SELECT id FROM branches")}
    if any(b not in valid_branches for b in v["branches"]):
        errors["branches"] = "Unknown branch."
    if v["role"] != "super_admin" and not v["branches"] and not v.get("labs"):
        errors["branches"] = "Assign at least one branch (or a laboratory for lab staff)."
    return errors


@bp.route("/users/new", methods=["GET", "POST"])
@require("users.manage")
def user_new():
    conn = get_db()
    branches = conn.all("SELECT * FROM branches ORDER BY sort_order")
    labs = conn.all("SELECT * FROM laboratories WHERE active = 1 ORDER BY name")
    v = {"name": "", "email": "", "role": "", "branches": [], "active": 1, "is_employee": True, "position": "",
         "license_no": "", "ptr_no": "", "s2_no": "", "labs": [], "notify_email": 1}
    errors = {}
    if request.method == "POST":
        v = _user_form_values(request.form)
        v["active"] = 1
        errors = _validate_user(conn, v)
        if not errors:
            temp = _temp_password()
            with conn.transaction():
                uid = conn.insert("users", {
                    "email": v["email"], "name": v["name"], "password_hash": hash_password(temp), "role": v["role"],
                    "active": 1, "must_change_password": 1, "created_at": now_str(), "created_by": g.user.id,
                    "license_no": v["license_no"], "ptr_no": v["ptr_no"], "s2_no": v["s2_no"],
                    "notify_email": v["notify_email"],
                })
                for b in v["branches"]:
                    conn.execute("INSERT INTO user_branches (user_id, branch_id) VALUES (?, ?)", (uid, b))
                for lab in v["labs"]:
                    if any(l["id"] == lab for l in labs):
                        conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, lab))
                if v["is_employee"]:
                    conn.insert("employees", {
                        "user_id": uid, "full_name": v["name"], "position": v["position"] or ROLES[v["role"]],
                        "primary_branch_id": v["branches"][0] if v["branches"] else None, "active": 1,
                        "created_at": now_str(),
                    })
                audit.record("user_created", "user", uid, f"Created user {v['email']} as {ROLES[v['role']]}",
                             {"role": v["role"], "branches": v["branches"], "labs": v["labs"]})
            return render_template("staff/admin/user_created.html", email=v["email"], temp=temp, user_id=uid)
    return render_template("staff/admin/user_form.html", v=v, errors=errors, branches=branches, labs=labs, is_new=True)


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@require("users.manage")
def user_edit(user_id):
    conn = get_db()
    row = conn.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        abort(404)
    branches = conn.all("SELECT * FROM branches ORDER BY sort_order")
    current_branches = [r["branch_id"] for r in conn.all("SELECT branch_id FROM user_branches WHERE user_id = ?", (user_id,))]
    labs = conn.all("SELECT * FROM laboratories WHERE active = 1 ORDER BY name")
    current_labs = [r["lab_id"] for r in conn.all("SELECT lab_id FROM user_labs WHERE user_id = ?", (user_id,))]
    v = {"name": row["name"], "email": row["email"], "role": row["role"], "branches": current_branches,
         "active": row["active"], "is_employee": False, "position": "", "license_no": row["license_no"],
         "ptr_no": row["ptr_no"], "s2_no": row["s2_no"], "labs": current_labs,
         "notify_email": row["notify_email"]}
    errors = {}
    if request.method == "POST":
        v = _user_form_values(request.form)
        errors = _validate_user(conn, v, user_id)
        is_self = user_id == g.user.id
        if is_self and v["role"] != row["role"]:
            errors["role"] = "You cannot change your own role."
        if is_self and not v["active"]:
            errors["active"] = "You cannot deactivate your own account."
        if row["role"] == "super_admin" and (v["role"] != "super_admin" or not v["active"]):
            others = conn.scalar("SELECT COUNT(*) FROM users WHERE role='super_admin' AND active=1 AND id != ?", (user_id,))
            if not others:
                errors["role"] = "At least one active super admin must remain."
        if not errors:
            with conn.transaction():
                conn.update("users", user_id, {"name": v["name"], "email": v["email"], "role": v["role"],
                                               "active": v["active"], "license_no": v["license_no"], "ptr_no": v["ptr_no"],
                                               "s2_no": v["s2_no"], "notify_email": v["notify_email"]})
                conn.execute("DELETE FROM user_labs WHERE user_id = ?", (user_id,))
                for lab in v["labs"]:
                    if any(l["id"] == lab for l in labs):
                        conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (user_id, lab))
                conn.execute("DELETE FROM user_branches WHERE user_id = ?", (user_id,))
                for b in v["branches"]:
                    conn.execute("INSERT INTO user_branches (user_id, branch_id) VALUES (?, ?)", (user_id, b))
                changes = audit.diff(dict(row), v, ["name", "email", "role", "active", "license_no", "ptr_no", "s2_no", "notify_email"])
                if sorted(current_labs) != sorted(v["labs"]):
                    changes["labs"] = [current_labs, v["labs"]]
                if sorted(current_branches) != sorted(v["branches"]):
                    changes["branches"] = [current_branches, v["branches"]]
                if changes:
                    action = "role_changed" if "role" in changes else "user_updated"
                    audit.record(action, "user", user_id, f"Updated user {v['email']}", changes)
                if "role" in changes or "active" in changes or "branches" in changes:
                    revoke_user_sessions(user_id)  # new access applies at next sign-in
            flash("User updated." + (" Their sessions were signed out so new access applies." if user_id != g.user.id else ""), "success")
            return redirect(url_for("admin.users"))
    history = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                       "WHERE entity_type='user' AND entity_id = ? ORDER BY a.id DESC LIMIT 20", (user_id,))
    return render_template("staff/admin/user_form.html", v=v, errors=errors, branches=branches, labs=labs, is_new=False,
                           user=row, history=history)


@bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@require("users.manage")
def user_reset_password(user_id):
    conn = get_db()
    row = conn.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        abort(404)
    temp = _temp_password()
    conn.execute("UPDATE users SET password_hash = ?, must_change_password = 1, failed_logins = 0, locked_until = NULL "
                 "WHERE id = ?", (hash_password(temp), user_id))
    revoke_user_sessions(user_id)
    audit.record("password_reset", "user", user_id, f"Reset password for {row['email']}")
    return render_template("staff/admin/user_created.html", email=row["email"], temp=temp, user_id=user_id, reset=True)


# ---------------------------------------------------------------------------
# Role access (super admin only)
# ---------------------------------------------------------------------------

@bp.route("/roles", methods=["GET", "POST"])
@require("roles.manage")
def roles():
    conn = get_db()
    editable_roles = [r for r in ROLES if r != "super_admin"]
    current = {r: {p["permission"] for p in conn.all("SELECT permission FROM role_permissions WHERE role = ?", (r,))}
               for r in editable_roles}
    if request.method == "POST":
        submitted = {r: set() for r in editable_roles}
        for item in request.form.getlist("grant"):
            role, _, perm = item.partition(":")
            if role in submitted and grantable(role, perm):
                submitted[role].add(perm)
        with conn.transaction():
            for role in editable_roles:
                added = submitted[role] - current[role]
                removed = current[role] - submitted[role]
                if not added and not removed:
                    continue
                for p in added:
                    conn.execute("INSERT INTO role_permissions (role, permission) VALUES (?, ?)", (role, p))
                for p in removed:
                    conn.execute("DELETE FROM role_permissions WHERE role = ? AND permission = ?", (role, p))
                audit.record("role_access_changed", "role", None, f"Changed access for {ROLES[role]}",
                             {"role": role, "granted": sorted(added), "revoked": sorted(removed)})
        flash("Role access saved. Changes apply on each user's next page load.", "success")
        return redirect(url_for("admin.roles"))
    groups = {}
    for p in CATALOG:
        groups.setdefault(p.group, []).append(p)
    history = conn.all("SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                       "WHERE action='role_access_changed' ORDER BY a.id DESC LIMIT 15")
    for h in history:
        h["d"] = json.loads(h["details"] or "{}")
    return render_template("staff/admin/roles.html", groups=groups, roles=editable_roles, current=current,
                           locked=LOCKED, defaults=ROLE_DEFAULTS, history=history)


@bp.route("/roles/reset", methods=["POST"])
@require("roles.manage")
def roles_reset():
    conn = get_db()
    role = request.form.get("role")
    if role not in ROLE_DEFAULTS:
        abort(400)
    with conn.transaction():
        conn.execute("DELETE FROM role_permissions WHERE role = ?", (role,))
        for p in ROLE_DEFAULTS[role]:
            conn.execute("INSERT INTO role_permissions (role, permission) VALUES (?, ?)", (role, p))
        audit.record("role_access_changed", "role", None, f"Reset {ROLES[role]} to recommended defaults",
                     {"role": role, "reset_to_defaults": True})
    flash(f"{ROLES[role]} access reset to the recommended defaults.", "success")
    return redirect(url_for("admin.roles"))


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@bp.route("/audit")
@require("audit.view")
def audit_log():
    conn = get_db()
    where, params = ["1=1"], []
    etype = request.args.get("entity")
    if etype:
        where.append("a.entity_type = ?")
        params.append(etype)
    action = request.args.get("action")
    if action:
        where.append("a.action = ?")
        params.append(action)
    total = conn.scalar(f"SELECT COUNT(*) FROM audit_log a WHERE {' AND '.join(where)}", params)
    pg = paginate(total, 50)
    rows = conn.all(f"SELECT a.*, u.name AS actor FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id "
                    f"WHERE {' AND '.join(where)} ORDER BY a.id DESC LIMIT ? OFFSET ?", [*params, pg["limit"], pg["offset"]])
    entities = [r["entity_type"] for r in conn.all("SELECT DISTINCT entity_type FROM audit_log ORDER BY entity_type")]
    actions = [r["action"] for r in conn.all("SELECT DISTINCT action FROM audit_log ORDER BY action")]
    return render_template("staff/admin/audit.html", rows=rows, pg=pg, entities=entities, actions=actions)


# ---------------------------------------------------------------------------
# Branches, hours and rooms
# ---------------------------------------------------------------------------

@bp.route("/branches")
@require("settings.manage")
def branches():
    conn = get_db()
    rows = conn.all("SELECT * FROM branches ORDER BY sort_order")
    return render_template("staff/admin/branches.html", branches=rows)


def _uploaded_image(field="image"):
    """Save an optional uploaded website photo. Returns (path or None, error or None)."""
    from ..uploads import save_public_image
    f = request.files.get(field)
    if not f or not f.filename:
        return None, None
    return save_public_image(f)


SITE_IMAGE_KEYS = [
    ("hero", "Top of the home page (large background photo)", "A wide, bright photo: your clinic interior, a dentist with a patient, or a smile close-up. Landscape, at least 1600 px wide."),
    ("lab", "Laboratory section", "A photo of your lab: scanners, milling machine, technicians at work."),
    ("specialty", "Smile transformations (until before & after cases are added)", "A bright, natural smile, ideally one of your own veneer or makeover patients (with their written consent)."),
    ("tech_xray", "Technology: CBCT & panoramic X-ray", "Your CBCT / panoramic X-ray machine. Portrait or square works best."),
    ("tech_scanner", "Technology: intraoral scanner", "Your intraoral scanner in use, or on its cart."),
    ("tech_milling", "Technology: milling machine", "Your milling machine or 3D printer in the lab."),
]


@bp.route("/content/photos", methods=["POST"])
@require("content.manage")
def site_image_save():
    conn = get_db()
    key = request.form.get("key")
    if key not in dict((k, l) for k, l, _ in SITE_IMAGE_KEYS):
        abort(400)
    if request.form.get("action") == "remove":
        conn.execute("DELETE FROM site_images WHERE key = ?", (key,))
        audit.record("site_image_removed", "site_content", None, f"Removed website photo: {key}")
        flash("Photo removed.", "success")
    else:
        path, err = _uploaded_image()
        if err or not path:
            flash(err or "Choose a photo to upload.", "error")
        else:
            if conn.one("SELECT key FROM site_images WHERE key = ?", (key,)):
                conn.execute("UPDATE site_images SET image_path = ?, updated_at = ?, updated_by = ? WHERE key = ?", (path, now_str(), g.user.id, key))
            else:
                conn.execute("INSERT INTO site_images (key, image_path, updated_at, updated_by) VALUES (?, ?, ?, ?)", (key, path, now_str(), g.user.id))
            audit.record("site_image_updated", "site_content", None, f"Updated website photo: {key}")
            flash("Photo saved. It now shows on the website.", "success")
    return redirect(url_for("admin.content") + "#photos")


@bp.route("/branches/<int:branch_id>", methods=["GET", "POST"])
@require("settings.manage")
def branch_edit(branch_id):
    conn = get_db()
    b = conn.one("SELECT * FROM branches WHERE id = ?", (branch_id,))
    if not b:
        abort(404)
    if not g.user.is_super_admin and branch_id not in g.user.branch_ids:
        abort(403)
    errors = {}
    if request.method == "POST":
        section = request.form.get("section")
        if section == "details":
            vals = {k: clean(request.form.get(k), 1000) for k in ("name", "address", "phone", "email", "map_url", "facebook_url", "waze_url", "hours_text", "intro")}
            for k in ("map_url", "facebook_url", "waze_url"):
                if vals[k] and not vals[k].startswith("https://"):
                    errors[k] = "Link must start with https://"
            if not vals["name"]:
                errors["name"] = "Name is required."
            img, img_err = _uploaded_image()
            if img_err:
                errors["image"] = img_err
            elif img:
                vals["image_path"] = img
            elif request.form.get("remove_image"):
                vals["image_path"] = ""
            if not errors:
                changes = audit.diff(dict(b), vals, vals.keys())
                conn.update("branches", branch_id, vals)
                audit.record("branch_updated", "branch", branch_id, f"Updated {vals['name']} details", changes, branch_id)
                flash("Branch details saved.", "success")
                return redirect(url_for("admin.branch_edit", branch_id=branch_id))
        elif section == "hours":
            new_hours = []
            for wd in range(7):
                closed = 1 if request.form.get(f"closed_{wd}") else 0
                o, c = request.form.get(f"open_{wd}", "09:00"), request.form.get(f"close_{wd}", "18:00")
                if not closed and (not TIME_RE.match(o) or not TIME_RE.match(c) or hm_to_min(o) >= hm_to_min(c)):
                    errors["hours"] = f"Check the hours for {WEEKDAYS[wd]}."
                new_hours.append((wd, o, c, closed))
            if not errors:
                with conn.transaction():
                    conn.execute("DELETE FROM branch_hours WHERE branch_id = ?", (branch_id,))
                    for wd, o, c, closed in new_hours:
                        conn.execute("INSERT INTO branch_hours (branch_id, weekday, open_time, close_time, closed) VALUES (?,?,?,?,?)",
                                     (branch_id, wd, o, c, closed))
                    audit.record("branch_hours_updated", "branch", branch_id, "Updated operating hours",
                                 {"hours": new_hours}, branch_id)
                flash("Operating hours saved.", "success")
                return redirect(url_for("admin.branch_edit", branch_id=branch_id))
        elif section == "resource_add":
            name = clean(request.form.get("name"), 80)
            kind = request.form.get("kind", "chair")
            if name:
                rid = conn.insert("resources", {"branch_id": branch_id, "name": name, "kind": kind if kind in ("chair", "room", "equipment") else "chair", "active": 1})
                audit.record("resource_created", "resource", rid, f"Added {name}", branch_id=branch_id)
                flash("Room/resource added.", "success")
            return redirect(url_for("admin.branch_edit", branch_id=branch_id))
        elif section == "resource_toggle":
            rid = to_int(request.form.get("resource_id"))
            r = conn.one("SELECT * FROM resources WHERE id = ? AND branch_id = ?", (rid, branch_id))
            if r:
                conn.execute("UPDATE resources SET active = ? WHERE id = ?", (0 if r["active"] else 1, rid))
                audit.record("resource_updated", "resource", rid, f"{'Deactivated' if r['active'] else 'Activated'} {r['name']}", branch_id=branch_id)
            return redirect(url_for("admin.branch_edit", branch_id=branch_id))
    hours = {h["weekday"]: h for h in conn.all("SELECT * FROM branch_hours WHERE branch_id = ?", (branch_id,))}
    resources = conn.all("SELECT * FROM resources WHERE branch_id = ? ORDER BY active DESC, name", (branch_id,))
    seq = conn.one("SELECT * FROM invoice_sequences WHERE branch_id = ?", (branch_id,))
    return render_template("staff/admin/branch_edit.html", b=b, hours=hours, resources=resources, errors=errors, seq=seq)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@bp.route("/services")
@require("settings.manage")
def services():
    conn = get_db()
    rows = conn.all("SELECT * FROM services ORDER BY sort_order, name")
    overrides = conn.all(
        "SELECT sd.*, s.name AS service, b.name AS branch, u.name AS dentist FROM service_durations sd "
        "JOIN services s ON s.id = sd.service_id LEFT JOIN branches b ON b.id = sd.branch_id "
        "LEFT JOIN users u ON u.id = sd.dentist_id ORDER BY s.name")
    return render_template("staff/admin/services.html", services=rows, overrides=overrides,
                           branches=conn.all("SELECT * FROM branches ORDER BY sort_order"),
                           dentists=conn.all("SELECT id, name FROM users WHERE role='dentist' AND active=1 ORDER BY name"))


@bp.route("/services/<int:service_id>", methods=["GET", "POST"])
@bp.route("/services/new", methods=["GET", "POST"], defaults={"service_id": None})
@require("settings.manage")
def service_edit(service_id):
    conn = get_db()
    s = conn.one("SELECT * FROM services WHERE id = ?", (service_id,)) if service_id else None
    if service_id and not s:
        abort(404)
    errors = {}
    v = dict(s) if s else {"name": "", "slug": "", "category": "General dentistry", "summary": "", "body": "",
                           "default_duration_min": 30, "default_price_cents": None, "bookable_online": 1, "active": 1, "sort_order": 50}
    if request.method == "POST":
        v = {
            "name": clean(request.form.get("name"), 120),
            "slug": re.sub(r"[^a-z0-9-]", "", clean(request.form.get("slug"), 80).lower().replace(" ", "-")),
            "category": clean(request.form.get("category"), 80),
            "summary": clean(request.form.get("summary"), 400),
            "body": clean(request.form.get("body"), 5000),
            "default_duration_min": to_int(request.form.get("default_duration_min"), 0),
            "default_price_cents": parse_money(request.form.get("default_price")),
            "bookable_online": 1 if request.form.get("bookable_online") else 0,
            "active": 1 if request.form.get("active") else 0,
            "sort_order": to_int(request.form.get("sort_order"), 50),
        }
        if not v["name"]:
            errors["name"] = "Name is required."
        if not v["slug"]:
            errors["slug"] = "URL name is required (letters, numbers, dashes)."
        elif conn.one("SELECT id FROM services WHERE slug = ? AND id != ?", (v["slug"], service_id or 0)):
            errors["slug"] = "Another service uses this URL name."
        if not 5 <= v["default_duration_min"] <= 480:
            errors["default_duration_min"] = "Duration must be between 5 and 480 minutes."
        if request.form.get("default_price") and v["default_price_cents"] is None:
            errors["default_price"] = "Enter an amount like 1500 or 1500.00."
        img, img_err = _uploaded_image()
        if img_err:
            errors["image"] = img_err
        v["image_path"] = img or ("" if request.form.get("remove_image") else (s["image_path"] if s else ""))
        if not errors:
            if s:
                conn.update("services", service_id, v)
                audit.record("service_updated", "service", service_id, f"Updated service {v['name']}",
                             audit.diff(dict(s), v, v.keys()))
            else:
                service_id = conn.insert("services", v)
                audit.record("service_created", "service", service_id, f"Created service {v['name']}")
            flash("Service saved.", "success")
            return redirect(url_for("admin.services"))
    return render_template("staff/admin/service_form.html", v=v, s=s, errors=errors)


@bp.route("/services/durations", methods=["POST"])
@require("settings.manage")
def duration_override():
    conn = get_db()
    action = request.form.get("action")
    if action == "delete":
        oid = to_int(request.form.get("id"))
        conn.execute("DELETE FROM service_durations WHERE id = ?", (oid,))
        audit.record("duration_override_deleted", "service_duration", oid, "Removed duration override")
    else:
        sid = to_int(request.form.get("service_id"))
        minutes = to_int(request.form.get("minutes"), 0)
        branch_id = to_int(request.form.get("branch_id"))
        dentist_id = to_int(request.form.get("dentist_id"))
        if not sid or not 5 <= minutes <= 480:
            flash("Choose a service and a duration between 5 and 480 minutes.", "error")
        else:
            oid = conn.insert("service_durations", {"service_id": sid, "branch_id": branch_id, "dentist_id": dentist_id, "minutes": minutes})
            audit.record("duration_override_created", "service_duration", oid, f"Duration override {minutes} min",
                         {"service_id": sid, "branch_id": branch_id, "dentist_id": dentist_id})
            flash("Duration override added.", "success")
    return redirect(url_for("admin.services"))


# ---------------------------------------------------------------------------
# Dentist schedules
# ---------------------------------------------------------------------------

@bp.route("/schedules", methods=["GET", "POST"])
@require("settings.manage")
def schedules():
    conn = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            sid = to_int(request.form.get("id"))
            row = conn.one("SELECT * FROM dentist_schedules WHERE id = ?", (sid,))
            if row and (g.user.is_super_admin or row["branch_id"] in g.user.branch_ids):
                conn.execute("DELETE FROM dentist_schedules WHERE id = ?", (sid,))
                audit.record("dentist_schedule_deleted", "dentist_schedule", sid, "Removed schedule block",
                             dict(row), row["branch_id"])
        else:
            dentist_id = to_int(request.form.get("dentist_id"))
            branch_id = to_int(request.form.get("branch_id"))
            weekdays = [to_int(w) for w in request.form.getlist("weekday")]
            start, end = request.form.get("start_time", ""), request.form.get("end_time", "")
            if not (dentist_id and branch_id and weekdays and TIME_RE.match(start) and TIME_RE.match(end)
                    and hm_to_min(start) < hm_to_min(end)):
                flash("Choose a dentist, branch, at least one day and a valid time range.", "error")
            elif not g.user.is_super_admin and branch_id not in g.user.branch_ids:
                abort(403)
            else:
                clashes = []
                for wd in weekdays:
                    overlap = conn.one(
                        "SELECT ds.*, b.name AS branch FROM dentist_schedules ds JOIN branches b ON b.id = ds.branch_id "
                        "WHERE dentist_id = ? AND weekday = ? AND start_time < ? AND end_time > ?",
                        (dentist_id, wd, end, start))
                    if overlap:
                        clashes.append(f"{WEEKDAYS[wd]} ({overlap['branch']} {overlap['start_time']}–{overlap['end_time']})")
                        continue
                    sid = conn.insert("dentist_schedules", {"dentist_id": dentist_id, "branch_id": branch_id, "weekday": wd,
                                                            "start_time": start, "end_time": end})
                    audit.record("dentist_schedule_created", "dentist_schedule", sid,
                                 f"Schedule {WEEKDAYS[wd]} {start}-{end}", branch_id=branch_id)
                if clashes:
                    flash("Skipped overlapping blocks: " + ", ".join(clashes), "warning")
                else:
                    flash("Schedule saved.", "success")
        return redirect(url_for("admin.schedules"))
    rows = conn.all(
        "SELECT ds.*, u.name AS dentist, b.name AS branch FROM dentist_schedules ds JOIN users u ON u.id = ds.dentist_id "
        "JOIN branches b ON b.id = ds.branch_id ORDER BY u.name, ds.weekday, ds.start_time")
    by_dentist = {}
    for r in rows:
        by_dentist.setdefault(r["dentist"], []).append(r)
    return render_template("staff/admin/schedules.html", by_dentist=by_dentist,
                           dentists=conn.all("SELECT id, name FROM users WHERE role='dentist' AND active=1 ORDER BY name"),
                           branches=[b for b in conn.all("SELECT * FROM branches WHERE active=1 ORDER BY sort_order")
                                     if g.user.is_super_admin or b["id"] in g.user.branch_ids])


# ---------------------------------------------------------------------------
# Website content, gallery, testimonials
# ---------------------------------------------------------------------------

CONTENT_KEYS = [
    ("home_hero", "Home page — headline and intro"),
    ("home_about", "Home page — about the clinic"),
    ("lab", "Digital dental laboratory section"),
    ("contact", "Contact details (main)"),
    ("booking_note", "Booking page — note to patients"),
    ("privacy_notice", "Privacy notice (full page)"),
    ("consent_booking", "Consent text on booking/inquiry forms"),
    ("consent_contact", "Consent text for reminders/follow-up contact"),
]


# Portfolio filters on the home page (key, label)
PORTFOLIO_CATEGORIES = [
    ("cosmetic", "Cosmetic & Restorative"),
    ("prosthodontics", "Prosthodontics"),
    ("implants", "Implants & Surgery"),
    ("orthodontics", "Orthodontics & TMJ"),
    ("pediatric", "Pediatrics & Special Care"),
    ("general", "General & Preventive"),
    ("lab", "Digital lab"),
]


@bp.route("/content", methods=["GET", "POST"])
@require("content.manage")
def content():
    conn = get_db()
    if request.method == "POST":
        key = request.form.get("key")
        if key not in dict(CONTENT_KEYS):
            abort(400)
        title = clean(request.form.get("title"), 200)
        body = clean(request.form.get("body"), 20000)
        before = conn.one("SELECT * FROM site_content WHERE key = ?", (key,))
        if before:
            conn.execute("UPDATE site_content SET title = ?, body = ?, updated_at = ?, updated_by = ? WHERE key = ?",
                         (title, body, now_str(), g.user.id, key))
        else:
            conn.execute("INSERT INTO site_content (key, title, body, updated_at, updated_by) VALUES (?,?,?,?,?)",
                         (key, title, body, now_str(), g.user.id))
        audit.record("content_updated", "site_content", None, f"Updated website content: {key}")
        flash("Website content saved.", "success")
        return redirect(url_for("admin.content") + f"#c-{key}")
    items = {r["key"]: r for r in conn.all("SELECT * FROM site_content")}
    gallery = conn.all("SELECT * FROM gallery_items ORDER BY id DESC")
    testimonials = conn.all("SELECT t.*, b.name AS branch FROM testimonials t LEFT JOIN branches b ON b.id = t.branch_id ORDER BY t.id DESC")
    photos = {r["key"]: r for r in conn.all("SELECT * FROM site_images")}
    guides = conn.all("SELECT gd.*, s.name AS service FROM guides gd LEFT JOIN services s ON s.id = gd.service_id "
                      "ORDER BY s.sort_order, gd.sort_order, gd.id")
    from .. import stock_photos
    return render_template("staff/admin/content.html", branches=conn.all("SELECT id, name FROM branches ORDER BY sort_order"),
                           guides=guides, stock=stock_photos.url,
                           photo_keys=SITE_IMAGE_KEYS, photos=photos, keys=CONTENT_KEYS, items=items, gallery=gallery,
                           testimonials=testimonials, categories=PORTFOLIO_CATEGORIES,
                           category_labels=dict(PORTFOLIO_CATEGORIES))


@bp.route("/content/guides/new", methods=["GET", "POST"])
@bp.route("/content/guides/<int:guide_id>", methods=["GET", "POST"])
@require("content.manage")
def guide_edit(guide_id=None):
    """Patient guides: short articles shown on the website, linked to a service."""
    conn = get_db()
    gd = conn.one("SELECT * FROM guides WHERE id = ?", (guide_id,)) if guide_id else None
    if guide_id and not gd:
        abort(404)
    services = conn.all("SELECT id, name FROM services WHERE active = 1 ORDER BY sort_order")
    v = dict(gd) if gd else {"title": "", "slug": "", "service_id": None, "summary": "", "body": "", "image_path": "",
                             "sort_order": 0, "published": 0}
    errors = {}
    if request.method == "POST":
        v.update({"title": clean(request.form.get("title"), 160), "summary": clean(request.form.get("summary"), 400),
                  "body": clean(request.form.get("body"), 30000), "service_id": to_int(request.form.get("service_id")) or None,
                  "sort_order": to_int(request.form.get("sort_order"), 0), "published": 1 if request.form.get("published") else 0})
        slug = re.sub(r"[^a-z0-9]+", "-", (clean(request.form.get("slug"), 120) or v["title"]).lower()).strip("-")
        v["slug"] = slug
        if len(v["title"]) < 3:
            errors["title"] = "Give the guide a title."
        if not slug:
            errors["slug"] = "Enter a URL name (letters, numbers and dashes)."
        elif conn.one("SELECT id FROM guides WHERE slug = ? AND id != ?", (slug, guide_id or 0)):
            errors["slug"] = "Another guide already uses this URL name."
        if len(v["body"]) < 20:
            errors["body"] = "Write the guide text."
        if v["service_id"] and not any(x["id"] == v["service_id"] for x in services):
            v["service_id"] = None
        img, img_err = _uploaded_image()
        if img_err:
            errors["image"] = img_err
        if not errors:
            v["image_path"] = img or ("" if request.form.get("remove_image") else v.get("image_path", ""))
            vals = {k: v[k] for k in ("title", "slug", "service_id", "summary", "body", "image_path", "sort_order", "published")}
            vals.update({"updated_at": now_str(), "updated_by": g.user.id})
            if gd:
                conn.update("guides", gd["id"], vals)
                audit.record("guide_updated", "site_content", gd["id"], f"Updated patient guide: {v['title']}")
            else:
                gid = conn.insert("guides", {**vals, "created_at": now_str()})
                audit.record("guide_created", "site_content", gid, f"Added patient guide: {v['title']}")
            flash("Patient guide saved." + ("" if v["published"] else " It's hidden until you tick Published."), "success")
            return redirect(url_for("admin.content") + "#guides")
    return render_template("staff/admin/guide_form.html", gd=gd, v=v, errors=errors, services=services)


@bp.route("/content/gallery", methods=["POST"])
@require("content.manage")
def gallery_save():
    from ..uploads import save_public_image
    conn = get_db()
    action = request.form.get("action")
    if action == "add":
        title = clean(request.form.get("title"), 150)
        note = clean(request.form.get("authorization_note"), 500)
        authorized = 1 if request.form.get("authorized") else 0
        if not title or not note or not authorized:
            flash("Add a title, record who authorised the image, and confirm authorisation. Images need written "
                  "permission (and patient consent for any patient photos).", "error")
            return redirect(url_for("admin.content") + "#gallery")
        path = ""
        file = request.files.get("image")
        if file and file.filename:
            path, err = save_public_image(file)
            if err:
                flash(err, "error")
                return redirect(url_for("admin.content") + "#gallery")
        before_path = ""
        before = request.files.get("before_image")
        if before and before.filename:
            before_path, err = save_public_image(before)
            if err:
                flash(err, "error")
                return redirect(url_for("admin.content") + "#gallery")
        category = request.form.get("category", "")
        if category not in dict(PORTFOLIO_CATEGORIES):
            category = ""
        gid = conn.insert("gallery_items", {"title": title, "caption": clean(request.form.get("caption"), 400),
                                            "image_path": path, "before_image_path": before_path, "category": category,
                                            "authorization_note": note, "authorized": authorized,
                                            "published": 0, "created_at": now_str()})
        audit.record("gallery_added", "gallery_item", gid, f"Added gallery item {title}")
        flash("Gallery item added as unpublished. Publish it when ready.", "success")
    else:
        gid = to_int(request.form.get("id"))
        item = conn.one("SELECT * FROM gallery_items WHERE id = ?", (gid,))
        if not item:
            abort(404)
        if action == "toggle":
            if not item["authorized"] or not item["image_path"]:
                flash("Only authorised items with an image can be published.", "error")
            else:
                conn.execute("UPDATE gallery_items SET published = ? WHERE id = ?", (0 if item["published"] else 1, gid))
                audit.record("gallery_published" if not item["published"] else "gallery_unpublished", "gallery_item", gid, item["title"])
        elif action == "feature":
            if not (item["published"] and item["before_image_path"]):
                flash("Only a published case with a before photo can be featured on the home page.", "error")
            else:
                conn.execute("UPDATE gallery_items SET featured = CASE WHEN id = ? THEN 1 ELSE 0 END", (gid,))
                audit.record("gallery_featured", "gallery_item", gid, item["title"])
                flash("This case is now featured on the home page.", "success")
        elif action == "delete":
            conn.execute("DELETE FROM gallery_items WHERE id = ?", (gid,))
            audit.record("gallery_deleted", "gallery_item", gid, item["title"])
    return redirect(url_for("admin.content") + "#gallery")


@bp.route("/content/testimonials", methods=["POST"])
@require("content.manage")
def testimonial_save():
    conn = get_db()
    action = request.form.get("action")
    if action == "add":
        quote = clean(request.form.get("quote"), 1200)
        consent = clean(request.form.get("consent_note"), 500)
        if not quote or not consent:
            flash("Add the patient's own words and a note of their written consent. Do not write testimonials on a patient's behalf.", "error")
        else:
            rating = to_int(request.form.get("rating"))
            branch_id = to_int(request.form.get("branch_id"))
            if branch_id and not conn.one("SELECT id FROM branches WHERE id = ?", (branch_id,)):
                branch_id = None
            tid = conn.insert("testimonials", {"quote": quote, "attribution": clean(request.form.get("attribution"), 120),
                                               "consent_note": consent, "approved": 0, "published": 0, "created_at": now_str(),
                                               "rating": rating if rating in (1, 2, 3, 4, 5) else None,
                                               "source": clean(request.form.get("source"), 60), "branch_id": branch_id})
            audit.record("testimonial_added", "testimonial", tid, "Added testimonial (pending approval)")
            flash("Testimonial saved as pending approval.", "success")
    else:
        tid = to_int(request.form.get("id"))
        t = conn.one("SELECT * FROM testimonials WHERE id = ?", (tid,))
        if not t:
            abort(404)
        if action == "approve":
            conn.execute("UPDATE testimonials SET approved = 1 WHERE id = ?", (tid,))
            audit.record("testimonial_approved", "testimonial", tid, "Approved testimonial")
        elif action == "toggle":
            if not t["approved"]:
                flash("Approve the testimonial before publishing.", "error")
            else:
                conn.execute("UPDATE testimonials SET published = ? WHERE id = ?", (0 if t["published"] else 1, tid))
                audit.record("testimonial_published" if not t["published"] else "testimonial_unpublished", "testimonial", tid, "")
        elif action == "delete":
            conn.execute("DELETE FROM testimonials WHERE id = ?", (tid,))
            audit.record("testimonial_deleted", "testimonial", tid, "")
    return redirect(url_for("admin.content") + "#testimonials")


# ---------------------------------------------------------------------------
# System settings (super admin only)
# ---------------------------------------------------------------------------

BOOL_KEYS = {k for k, v in settings.DEFAULTS.items() if isinstance(v, bool)}
INT_KEYS = {k for k, v in settings.DEFAULTS.items() if isinstance(v, int) and not isinstance(v, bool)}


@bp.route("/system", methods=["GET", "POST"])
@require("system.settings")
def system():
    conn = get_db()
    current = settings.all_settings(conn)
    errors = {}
    if request.method == "POST":
        new = {}
        for key in settings.DEFAULTS:
            if key in BOOL_KEYS:
                new[key] = bool(request.form.get(key))
            elif key in INT_KEYS:
                val = to_int(request.form.get(key))
                if val is None or val < 0:
                    errors[key] = "Enter a whole number."
                new[key] = val
            else:
                new[key] = clean(request.form.get(key), 500)
        if new.get("messaging.provider") != "manual":
            errors["messaging.provider"] = "Only the manual provider is available until a messaging integration is configured."
        try:
            new["invoice.number_format"].format(prefix="MAL", year=2026, seq=1)
        except (KeyError, ValueError, IndexError):
            errors["invoice.number_format"] = "Use only {prefix}, {year} and {seq} placeholders, e.g. {prefix}-{year}-{seq:05d}."
        for k in ("messaging.quiet_start", "messaging.quiet_end"):
            if not TIME_RE.match(new.get(k) or ""):
                errors[k] = "Use HH:MM (24-hour)."
        if not errors:
            changed = {k: [current.get(k), v] for k, v in new.items() if current.get(k) != v}
            with conn.transaction():
                for k in changed:
                    settings.put(k, new[k], g.user.id, conn)
                # invoice prefixes per branch
                for b in conn.all("SELECT id FROM branches"):
                    prefix = clean(request.form.get(f"prefix_{b['id']}"), 10).upper()
                    if prefix and re.match(r"^[A-Z0-9]{1,10}$", prefix):
                        if conn.one("SELECT branch_id FROM invoice_sequences WHERE branch_id = ?", (b["id"],)):
                            conn.execute("UPDATE invoice_sequences SET prefix = ? WHERE branch_id = ?", (prefix, b["id"]))
                        else:
                            conn.execute("INSERT INTO invoice_sequences (branch_id, prefix, next_no) VALUES (?, ?, 1)", (b["id"], prefix))
                if changed:
                    audit.record("settings_changed", "settings", None, "Changed system settings", changed)
            flash("Settings saved.", "success")
            return redirect(url_for("admin.system"))
        current.update(new)
    seqs = conn.all("SELECT b.id, b.name, s.prefix, s.next_no FROM branches b LEFT JOIN invoice_sequences s ON s.branch_id = b.id ORDER BY b.sort_order")
    from .. import dentist_mail
    mail = {"state": dentist_mail.state(conn), "senders": dentist_mail.senders(conn)}
    return render_template("staff/admin/system.html", s=current, labels=settings.LABELS, errors=errors,
                           bool_keys=BOOL_KEYS, int_keys=INT_KEYS, seqs=seqs, mail=mail)


@bp.route("/system/backup", methods=["POST"])
@require("system.settings")
def download_backup():
    """Super admin: download a zip with a consistent copy of the database plus uploaded files.
    Contains all patient data: keep it encrypted and private."""
    import sqlite3
    import tempfile
    import zipfile
    from pathlib import Path

    from flask import after_this_request, current_app, send_file
    url = current_app.config["DATABASE_URL"]
    if not url.startswith("sqlite:///"):
        flash("Backup download works with the built-in database only. For PostgreSQL use pg_dump (docs/DEPLOYMENT.md).", "error")
        return redirect(url_for("admin.system"))
    stamp = now_str()[:16].replace(" ", "_").replace(":", "")
    tmpdir = Path(tempfile.mkdtemp(dir=current_app.config["DATA_DIR"]))
    db_copy = tmpdir / "dental_haven.db"
    src = sqlite3.connect(url[len("sqlite:///"):])
    dst = sqlite3.connect(db_copy)
    try:
        src.backup(dst)  # consistent snapshot even while the site is in use
    finally:
        dst.close()
        src.close()
    zpath = tmpdir / f"dental-haven-backup-{stamp}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_copy, "dental_haven.db")
        for key, arc in (("UPLOAD_DIR", "patient-documents"), ("PUBLIC_UPLOAD_DIR", "website-images")):
            root = Path(current_app.config[key])
            for f in root.rglob("*"):
                if f.is_file():
                    zf.write(f, f"{arc}/{f.relative_to(root)}")
    audit.record("backup_downloaded", "settings", None, "Downloaded a full backup (database and uploaded files)")

    @after_this_request
    def _cleanup(resp):
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        return resp
    return send_file(zpath, as_attachment=True, download_name=zpath.name, mimetype="application/zip", max_age=0)


@bp.route("/system/test-email", methods=["POST"])
@require("system.settings")
def email_test():
    """Send one test email from every configured sender to the signed-in super admin."""
    from .. import dentist_mail
    conn = get_db()
    if dentist_mail.state(conn) == "demo":
        flash("The demo site doesn't send emails.", "error")
        return redirect(url_for("admin.system"))
    tried = {}
    for b in conn.all("SELECT slug, name FROM branches WHERE active = 1 ORDER BY sort_order"):
        c = dentist_mail.config(b["slug"], b["name"])
        if c and c["sender"] not in tried:
            try:
                dentist_mail.send_email(g.user.email, f"Dental Haven: test email from {c['sender']}",
                                        f"Hi {g.user.name},\n\nThis test shows that Dental Haven can send dentist emails "
                                        f"from {c['sender']} ({b['name']}).\n", c)
                tried[c["sender"]] = None
            except Exception as exc:  # noqa: BLE001
                tried[c["sender"]] = f"{type(exc).__name__}: {str(exc)[:120]}"
    if not tried:
        flash("Email isn't set up on this server yet.", "error")
        return redirect(url_for("admin.system"))
    ok = [k for k, v in tried.items() if v is None]
    bad = {k: v for k, v in tried.items() if v}
    audit.record("email_test", "settings", None, f"Test emails: {len(ok)} sent, {len(bad)} failed", {"failed": list(bad)})
    if ok:
        flash(f"Test email sent to {g.user.email} from: {', '.join(ok)}. Check the inbox (and spam folder).", "success")
    for sender, err in bad.items():
        flash(f"Test email from {sender} failed ({err}). Check that account's app password.", "error")
    return redirect(url_for("admin.system"))
    try:
        dentist_mail.send_email(g.user.email, "Dental Haven: test email",
                                f"Hi {g.user.name},\n\nThis test shows that Dental Haven can send emails to dentists.\n")
    except Exception as exc:  # noqa: BLE001
        audit.record("email_test", "settings", None, "Test email failed", {"error": type(exc).__name__})
        flash(f"The test email failed ({type(exc).__name__}: {str(exc)[:160]}). Check MAIL_USERNAME and MAIL_PASSWORD.", "error")
    else:
        audit.record("email_test", "settings", None, "Sent a test email")
        flash(f"Test email sent to {g.user.email}. Check the inbox (and the spam folder).", "success")
    return redirect(url_for("admin.system"))


# ---------------------------------------------------------------------------
# Import from MyMedsPH (super admin only)
# ---------------------------------------------------------------------------

def _import_dir():
    from pathlib import Path
    from flask import current_app
    d = Path(current_app.config["IMPORT_DIR"])
    d.mkdir(parents=True, exist_ok=True)
    # remove uploads that were never confirmed (older than 1 day)
    import time
    for f in d.glob("*.upload"):
        if f.stat().st_mtime < time.time() - 86400:
            f.unlink(missing_ok=True)
    return d


def _load_pending(token):
    """Return ({files, branch_id, filename}, path) for a pending upload, or (None, path)."""
    import io
    import zipfile
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token):
        abort(400)
    path = _import_dir() / f"{token}.upload"
    if not path.exists():
        return None, path
    with zipfile.ZipFile(path) as zf:
        meta = json.loads(zf.read("_meta.json"))
        files = [(n, zf.read(n)) for n in zf.namelist() if n != "_meta.json"]
    return {"files": files, **meta}, path


def _save_pending(files, branch_id, filename):
    import zipfile
    token = secrets.token_urlsafe(24)
    path = _import_dir() / f"{token}.upload"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_meta.json", json.dumps({"branch_id": branch_id, "filename": filename}))
        for i, (name, data) in enumerate(files):
            zf.writestr(f"{i}_{secure_name(name)}", data)
    return token


def secure_name(name):
    from werkzeug.utils import secure_filename
    return secure_filename(name) or "file"


@bp.route("/import", methods=["GET", "POST"])
@require("system.settings")
def import_data():
    from ..importer import ImportFileError, read_export, run_import
    from flask import current_app
    demo = current_app.config["APP_ENV"] == "demo"
    if demo and request.method == "POST":
        abort(403)
    conn = get_db()
    branches = conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")
    runs = conn.all("SELECT r.*, u.name AS by_name, b.name AS branch FROM import_runs r LEFT JOIN users u ON u.id = r.started_by "
                    "LEFT JOIN branches b ON b.id = r.branch_id ORDER BY r.id DESC LIMIT 20")
    for r in runs:
        r["s"] = json.loads(r["summary"] or "{}")
    if request.method == "POST":
        branch_id = to_int(request.form.get("branch_id"))
        uploads = [f for f in request.files.getlist("files") if f and f.filename]
        if not branch_id or not any(b["id"] == branch_id for b in branches):
            flash("Choose the branch these patients belong to.", "error")
            return redirect(url_for("admin.import_data"))
        if not uploads:
            flash("Choose the MyMedsPH export file (.zip) or its CSV files.", "error")
            return redirect(url_for("admin.import_data"))
        files = [(f.filename, f.read()) for f in uploads]
        try:
            data = read_export(files)
        except ImportFileError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin.import_data"))
        summary = run_import(conn, data, branch_id=branch_id, user_id=g.user.id, commit=False)
        token = _save_pending(files, branch_id, ", ".join(f.filename for f in uploads)[:200])
        branch = next(b for b in branches if b["id"] == branch_id)
        return render_template("staff/admin/import_preview.html", s=summary, token=token, branch=branch,
                               filename=", ".join(f.filename for f in uploads))
    return render_template("staff/admin/import.html", branches=branches, runs=runs, demo=demo)


@bp.route("/import/confirm", methods=["POST"])
@require("system.settings")
def import_confirm():
    from ..importer import ImportFileError, read_export, run_import
    conn = get_db()
    from flask import current_app
    if current_app.config["APP_ENV"] == "demo":
        abort(403)
    token = request.form.get("token", "")
    pending, path = _load_pending(token)
    if request.form.get("action") == "cancel":
        path.unlink(missing_ok=True)
        flash("Import cancelled. Nothing was changed.", "info")
        return redirect(url_for("admin.import_data"))
    if pending is None:
        flash("That upload has expired. Please upload the file again.", "error")
        return redirect(url_for("admin.import_data"))
    run_id = conn.insert("import_runs", {"source": "mymedsph", "filename": pending["filename"], "branch_id": pending["branch_id"],
                                         "status": "running", "started_by": g.user.id, "started_at": now_str()})
    try:
        summary = run_import(conn, read_export(pending["files"]), branch_id=pending["branch_id"], user_id=g.user.id, commit=True)
    except Exception:
        conn.execute("UPDATE import_runs SET status = 'failed', finished_at = ? WHERE id = ?", (now_str(), run_id))
        path.unlink(missing_ok=True)
        raise
    path.unlink(missing_ok=True)  # the uploaded export is not kept
    conn.execute("UPDATE import_runs SET status = 'done', summary = ?, finished_at = ? WHERE id = ?",
                 (json.dumps(summary), now_str(), run_id))
    audit.record("data_imported", "import_run", run_id,
                 f"MyMedsPH import: {summary['patients_new']} new, {summary['patients_updated']} updated patients",
                 {k: v for k, v in summary.items() if k != "errors"})
    flash(f"Import finished: {summary['patients_new']} new patients, {summary['patients_updated']} updated, "
          f"{summary['procedures']} visit records, {summary['bills']} bill lines. The uploaded file was not kept.", "success")
    return redirect(url_for("admin.import_data"))

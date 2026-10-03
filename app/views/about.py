"""About us: team members (dentists, staff, lab) and clinic activities, edited by users with "Edit public website content".

Nothing is published until someone with that access ticks Publish, and publishing needs a consent record: team members
agree to have their name, photo and bio on the website; activity photos need everyone recognisable to have agreed.
"""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..util import clean, now_str, parse_date, to_int, today

bp = Blueprint("about_admin", __name__, url_prefix="/staff/admin/about")

GROUPS = {"dentist": "Dentists", "staff": "Clinic staff", "lab": "Laboratory team"}
KINDS = {"outreach": "Community outreach / dental mission", "training": "Training & seminars", "event": "Clinic event",
         "celebration": "Celebration / team building", "award": "Recognition", "other": "Other"}
MAX_PHOTOS = 12


def _image(field):
    from ..uploads import save_public_image
    f = request.files.get(field)
    if not f or not f.filename:
        return None, None
    return save_public_image(f)


def _branches(conn):
    return conn.all("SELECT id, name FROM branches WHERE active = 1 ORDER BY sort_order")


@bp.route("/")
@require("content.manage")
def index():
    conn = get_db()
    members = conn.all("SELECT * FROM team_members ORDER BY CASE grp WHEN 'dentist' THEN 0 WHEN 'staff' THEN 1 ELSE 2 END, sort_order, name")
    mb = {}
    for r in conn.all("SELECT mb.member_id, b.name FROM team_member_branches mb JOIN branches b ON b.id = mb.branch_id ORDER BY b.sort_order"):
        mb.setdefault(r["member_id"], []).append(r["name"].split(" (")[0])
    acts = conn.all("SELECT a.*, b.name AS branch, (SELECT COUNT(*) FROM activity_photos p WHERE p.activity_id = a.id) AS photos "
                    "FROM activities a LEFT JOIN branches b ON b.id = a.branch_id ORDER BY a.happened_on DESC, a.id DESC")
    return render_template("staff/about/index.html", members=members, member_branches=mb, acts=acts, groups=GROUPS, kinds=KINDS)


# ---------------------------------------------------------------- team members
@bp.route("/team/new", methods=["GET", "POST"], defaults={"member_id": None})
@bp.route("/team/<int:member_id>", methods=["GET", "POST"])
@require("content.manage")
def member(member_id):
    conn = get_db()
    m = conn.one("SELECT * FROM team_members WHERE id = ?", (member_id,)) if member_id else None
    if member_id and not m:
        abort(404)
    chosen = {r["branch_id"] for r in conn.all("SELECT branch_id FROM team_member_branches WHERE member_id = ?", (member_id,))} if m else set()
    errors = {}
    v = dict(m) if m else {"name": "", "title": "", "grp": "dentist", "credentials": "", "bio": "", "photo_path": "", "consent_note": "",
                           "published": 0, "sort_order": 0}
    if request.method == "POST":
        if request.form.get("action") == "delete" and m:
            conn.execute("DELETE FROM team_members WHERE id = ?", (m["id"],))
            audit.record("team_member_deleted", "team_member", m["id"], "Removed a team member from the website")
            flash("Removed from the website.", "success")
            return redirect(url_for("about_admin.index") + "#team")
        f = request.form
        v.update(name=clean(f.get("name"), 120), title=clean(f.get("title"), 120), credentials=clean(f.get("credentials"), 160),
                 bio=clean(f.get("bio"), 1500), consent_note=clean(f.get("consent_note"), 300),
                 grp=f.get("grp") if f.get("grp") in GROUPS else "dentist", sort_order=to_int(f.get("sort_order")) or 0,
                 published=1 if f.get("published") else 0)
        chosen = {b["id"] for b in _branches(conn) if str(b["id"]) in f.getlist("branches")}
        if not v["name"]:
            errors["name"] = "Enter the name as it should appear on the website."
        if v["published"] and not v["consent_note"]:
            errors["consent_note"] = "Write down the person's consent before publishing (e.g. Agreed in writing, 2026-10-03)."
        img, err = _image("photo")
        if err:
            errors["photo"] = err
        elif img:
            v["photo_path"] = img
        elif f.get("remove_photo"):
            v["photo_path"] = ""
        if not errors:
            data = {k: v[k] for k in ("name", "title", "grp", "credentials", "bio", "photo_path", "consent_note", "published", "sort_order")}
            with conn.transaction():
                if m:
                    conn.update("team_members", m["id"], {**data, "updated_at": now_str()})
                    mid = m["id"]
                else:
                    mid = conn.insert("team_members", {**data, "created_at": now_str(), "updated_at": now_str()})
                conn.execute("DELETE FROM team_member_branches WHERE member_id = ?", (mid,))
                for bid in chosen:
                    conn.execute("INSERT INTO team_member_branches (member_id, branch_id) VALUES (?, ?)", (mid, bid))
                audit.record("team_member_saved", "team_member", mid, ("Published " if v["published"] else "Saved (not published) ") + "team member")
            flash("Saved." + ("" if v["published"] else " Not on the website until you tick Publish."), "success")
            return redirect(url_for("about_admin.index") + "#team")
    return render_template("staff/about/member.html", m=m, v=v, errors=errors, groups=GROUPS, branches=_branches(conn), chosen=chosen)


# ---------------------------------------------------------------- activities
@bp.route("/activities/new", methods=["GET", "POST"], defaults={"act_id": None})
@bp.route("/activities/<int:act_id>", methods=["GET", "POST"])
@require("content.manage")
def activity(act_id):
    conn = get_db()
    a = conn.one("SELECT * FROM activities WHERE id = ?", (act_id,)) if act_id else None
    if act_id and not a:
        abort(404)
    photos = conn.all("SELECT * FROM activity_photos WHERE activity_id = ? ORDER BY sort_order, id", (act_id,)) if a else []
    errors = {}
    v = dict(a) if a else {"title": "", "happened_on": today().isoformat(), "kind": "outreach", "body": "", "branch_id": None,
                           "consent_note": "", "published": 0}
    if request.method == "POST":
        f = request.form
        action = f.get("action", "save")
        if action == "delete" and a:
            with conn.transaction():
                conn.execute("DELETE FROM activity_photos WHERE activity_id = ?", (a["id"],))
                conn.execute("DELETE FROM activities WHERE id = ?", (a["id"],))
                audit.record("activity_deleted", "activity", a["id"], "Deleted a website activity")
            flash("Activity deleted.", "success")
            return redirect(url_for("about_admin.index") + "#activities")
        if f.get("remove_photo") and a:
            conn.execute("DELETE FROM activity_photos WHERE id = ? AND activity_id = ?", (to_int(f.get("remove_photo")), a["id"]))
            flash("Photo removed.", "success")
            return redirect(url_for("about_admin.activity", act_id=a["id"]) + "#photos")
        happened = parse_date(f.get("happened_on"))
        v.update(title=clean(f.get("title"), 160), kind=f.get("kind") if f.get("kind") in KINDS else "other", body=clean(f.get("body"), 6000),
                 consent_note=clean(f.get("consent_note"), 300), published=1 if f.get("published") else 0,
                 branch_id=to_int(f.get("branch_id")) if any(str(b["id"]) == f.get("branch_id") for b in _branches(conn)) else None,
                 happened_on=happened.isoformat() if happened else f.get("happened_on") or "")
        if not v["title"]:
            errors["title"] = "Give the activity a title."
        if not happened:
            errors["happened_on"] = "Enter the date of the activity."
        elif happened > today():
            errors["happened_on"] = "Post activities after they happen."
        files = [x for x in request.files.getlist("photos") if x and x.filename]
        if len(photos) + len(files) > MAX_PHOTOS:
            errors["photos"] = f"Up to {MAX_PHOTOS} photos per activity."
        if v["published"] and (photos or files) and not v["consent_note"]:
            errors["consent_note"] = "Before publishing photos, confirm that everyone recognisable agreed (patients in writing)."
        saved = []
        if not errors:
            from ..uploads import save_public_image
            for x in files:
                path, err = save_public_image(x)
                if err:
                    errors["photos"] = f"{x.filename}: {err}"
                    break
                saved.append(path)
        if not errors:
            data = {k: v[k] for k in ("title", "happened_on", "kind", "body", "branch_id", "consent_note", "published")}
            with conn.transaction():
                if a:
                    conn.update("activities", a["id"], {**data, "updated_at": now_str()})
                    aid = a["id"]
                else:
                    aid = conn.insert("activities", {**data, "created_by": g.user.id, "created_at": now_str(), "updated_at": now_str()})
                start = len(photos)
                for i, path in enumerate(saved):
                    conn.insert("activity_photos", {"activity_id": aid, "image_path": path, "caption": "", "sort_order": start + i})
                for p in photos:
                    cap = f.get(f"caption_{p['id']}")
                    if cap is not None:
                        conn.execute("UPDATE activity_photos SET caption = ? WHERE id = ?", (clean(cap, 200), p["id"]))
                audit.record("activity_saved", "activity", aid, ("Published " if v["published"] else "Saved (not published) ") + "activity")
            flash("Activity saved." + ("" if v["published"] else " Not on the website until you tick Publish."), "success")
            return redirect(url_for("about_admin.activity", act_id=aid))
    return render_template("staff/about/activity.html", a=a, v=v, photos=photos, errors=errors, kinds=KINDS, branches=_branches(conn),
                           max_photos=MAX_PHOTOS)

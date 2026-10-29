"""X-ray section: X-rays of clinic patients and walk-ins, with their own receipts and payments.

X-rays are kept apart from progress notes and patient bills: an X-ray record (XR-000001) lists what was taken (type and
tooth), who asked for it (a clinic dentist or an outside referring dentist), who took it, the price and payments, and
the images. Outside dentists who refer patients earn a rebate (a referral fee) per X-ray, which is paid out in a batch,
usually at the end of December (Rebates page). Mistakes are voided with a reason, never deleted.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from .. import audit
from ..auth import login_required, require
from ..billing import PAYMENT_METHODS, pay_options, parse_pay
from ..db import get_db
from ..permissions import can_see_patient
from ..uploads import DOC_TYPES, SIGNATURES, _read_checked, document_path
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import date_range_args, dentists

bp = Blueprint("xray", __name__, url_prefix="/staff/xray")

MAX_ITEMS = 6
MAX_FILES = 20
MAX_IMAGE_MB = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pay_label(method: str, account: str = "") -> str:
    label = PAYMENT_METHODS.get(method, method)
    return f"{label} – {account}" if account and account != label else label


def _scope() -> list[int]:
    return list(g.user.scope_branch_ids)


def _marks(ids) -> str:
    return ",".join("?" * len(ids)) or "NULL"


def _need(perm: str):
    if not g.user.can(perm):
        abort(403)


def _load(xray_id: int):
    x = get_db().one("SELECT x.*, b.name AS branch, b.address AS branch_address, b.phone AS branch_phone, "
                     "p.first_name, p.last_name, p.chart_no, rq.name AS requested_name, r.name AS referrer_name, r.clinic AS referrer_clinic, "
                     "tk.name AS taken_name, cu.name AS created_name FROM xrays x JOIN branches b ON b.id = x.branch_id "
                     "LEFT JOIN patients p ON p.id = x.patient_id LEFT JOIN users rq ON rq.id = x.requested_by "
                     "LEFT JOIN xray_referrers r ON r.id = x.referrer_id LEFT JOIN users tk ON tk.id = x.taken_by "
                     "LEFT JOIN users cu ON cu.id = x.created_by WHERE x.id = ?", (xray_id,))
    if not x or not g.user.in_branch(x["branch_id"]):
        abort(404)
    if x["patient_id"] and not can_see_patient(get_db(), g.user, x["patient_id"]):
        abort(403)
    return x


def who(x) -> str:
    """The person X-rayed: the clinic patient, or the walk-in's name."""
    if x["patient_id"]:
        return f"{x['last_name']}, {x['first_name']}"
    return f"{x['walkin_name']} (walk-in)"


def requested_label(x) -> str:
    if x["referrer_id"]:
        return f"{x['referrer_name']}" + (f", {x['referrer_clinic']}" if x["referrer_clinic"] else "") + " (outside)"
    return x["requested_name"] or ""


def paid_of(conn, xray_ids) -> dict[int, int]:
    ids = list(xray_ids)
    if not ids:
        return {}
    return {r["xray_id"]: r["amt"] for r in conn.all(
        f"SELECT xray_id, SUM(amount_cents) AS amt FROM xray_payments WHERE status = 'valid' AND xray_id IN ({_marks(ids)}) "
        "GROUP BY xray_id", ids)}


def types(conn, active_only=True):
    return conn.all("SELECT * FROM xray_types" + (" WHERE active = 1" if active_only else "") + " ORDER BY sort_order, name")


def referrers(conn, active_only=True):
    return conn.all("SELECT * FROM xray_referrers" + (" WHERE active = 1" if active_only else "") + " ORDER BY name")


def staff_choices(conn, branch_ids):
    if not branch_ids:
        return []
    return conn.all(f"SELECT DISTINCT u.id, u.name FROM users u JOIN user_branches ub ON ub.user_id = u.id "
                    f"WHERE u.active = 1 AND ub.branch_id IN ({_marks(branch_ids)}) ORDER BY u.name", list(branch_ids))


def rebate_default(conn, referrer_id, total: int) -> int:
    if not referrer_id:
        return 0
    r = conn.one("SELECT rebate_bp FROM xray_referrers WHERE id = ?", (referrer_id,))
    return round(total * (r["rebate_bp"] or 0) / 10000) if r else 0


def _save_image(fs):
    """X-ray image or PDF -> (stored name, mime, size, original name, error)."""
    kind, data, err = _read_checked(fs, DOC_TYPES, MAX_IMAGE_MB)
    if err:
        return None, None, 0, None, err
    stored = f"xr-{secrets.token_hex(16)}.{kind}"
    folder = Path(current_app.config["UPLOAD_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored).write_bytes(data)
    return stored, SIGNATURES[kind][1], len(data), (secure_filename(fs.filename or "") or f"xray.{kind}")[:150], None


def _add_files(conn, xray_id, files) -> tuple[int, list[str]]:
    n, errors = 0, []
    have = conn.scalar("SELECT COUNT(*) FROM xray_files WHERE xray_id = ?", (xray_id,)) or 0
    for fs in files:
        if not fs or not fs.filename:
            continue
        if have + n >= MAX_FILES:
            errors.append(f"Up to {MAX_FILES} files per X-ray.")
            break
        stored, mime, size, original, err = _save_image(fs)
        if err:
            errors.append(f"{fs.filename}: {err}")
            continue
        conn.insert("xray_files", {"xray_id": xray_id, "stored_name": stored, "mime": mime, "size": size, "original_name": original,
                                   "uploaded_by": g.user.id, "uploaded_at": now_str()})
        n += 1
    return n, errors


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@bp.route("/")
@require("xray.view")
def index():
    conn = get_db()
    start, end = date_range_args(31)
    scope = _scope()
    q = clean(request.args.get("q"), 80)
    show = request.args.get("show", "")
    where = [f"x.branch_id IN ({_marks(scope)})", "x.taken_on BETWEEN ? AND ?"]
    params = [*scope, start.isoformat(), end.isoformat()]
    if q:
        like = f"%{q}%"
        where.append("(x.number LIKE ? OR x.walkin_name LIKE ? OR p.first_name || ' ' || p.last_name LIKE ? OR p.chart_no LIKE ?)")
        params += [like, like, like, like]
    if show != "void":
        where.append("x.status = 'ok'")
    rows = conn.all("SELECT x.*, b.name AS branch, p.first_name, p.last_name, p.chart_no, rq.name AS requested_name, r.name AS referrer_name, "
                    "r.clinic AS referrer_clinic, (SELECT group_concat(description || CASE WHEN tooth != '' THEN ' #' || tooth ELSE '' END, ', ') "
                    "FROM xray_items WHERE xray_id = x.id) AS what, (SELECT COUNT(*) FROM xray_files f WHERE f.xray_id = x.id) AS files "
                    "FROM xrays x JOIN branches b ON b.id = x.branch_id LEFT JOIN patients p ON p.id = x.patient_id "
                    "LEFT JOIN users rq ON rq.id = x.requested_by LEFT JOIN xray_referrers r ON r.id = x.referrer_id "
                    f"WHERE {' AND '.join(where)} ORDER BY x.taken_on DESC, x.id DESC LIMIT 500", params)
    paid = paid_of(conn, [r["id"] for r in rows])
    items = [{**dict(r), "who": who(r), "requested": requested_label(r), "paid": paid.get(r["id"], 0),
              "balance": (r["total_cents"] - paid.get(r["id"], 0)) if r["status"] == "ok" else 0} for r in rows]
    if show == "balance":
        items = [i for i in items if i["balance"] > 0]
    ok = [i for i in items if i["status"] == "ok"]
    totals = {"n": len(ok), "total": sum(i["total_cents"] for i in ok), "paid": sum(i["paid"] for i in ok),
              "balance": sum(i["balance"] for i in ok)}
    return render_template("staff/xray/index.html", items=items, totals=totals, start=start, end=end, q=q, show=show)


# ---------------------------------------------------------------------------
# New / edit
# ---------------------------------------------------------------------------

def _form_values(conn, x=None):
    v = {"branch_id": g.user.active_branch_id or (g.user.branch_ids[0] if g.user.branch_ids else None), "patient_id": None,
         "chart_no": "", "walkin_name": "", "walkin_phone": "", "taken_on": today().isoformat(), "requested": "",
         "taken_by": g.user.id, "discount": "", "rebate": "", "notes": "", "items": [{"type_id": None, "tooth": "", "price": ""}]}
    if x:
        v.update(branch_id=x["branch_id"], patient_id=x["patient_id"], chart_no=x["chart_no"] or "", walkin_name=x["walkin_name"],
                 walkin_phone=x["walkin_phone"], taken_on=x["taken_on"], taken_by=x["taken_by"], notes=x["notes"],
                 requested=(f"r:{x['referrer_id']}" if x["referrer_id"] else (f"d:{x['requested_by']}" if x["requested_by"] else "")),
                 discount=f"{x['discount_cents'] / 100:.2f}" if x["discount_cents"] else "",
                 rebate=f"{x['rebate_cents'] / 100:.2f}" if x["rebate_cents"] else "",
                 items=[{"type_id": i["type_id"], "tooth": i["tooth"], "price": f"{i['price_cents'] / 100:.2f}", "description": i["description"]}
                        for i in conn.all("SELECT * FROM xray_items WHERE xray_id = ? ORDER BY id", (x["id"],))])
    return v


def _read_form(conn, x=None):
    """Form -> (values, record, items, errors)."""
    f = request.form
    errors = []
    tmap = {t["id"]: t for t in types(conn, active_only=False)}
    v = {"branch_id": to_int(f.get("branch_id")), "patient_id": to_int(f.get("patient_id")), "chart_no": clean(f.get("chart_no"), 40),
         "walkin_name": clean(f.get("walkin_name"), 120), "walkin_phone": clean(f.get("walkin_phone"), 40),
         "taken_on": f.get("taken_on") or "", "requested": f.get("requested") or "", "taken_by": to_int(f.get("taken_by")),
         "discount": f.get("discount") or "", "rebate": f.get("rebate") or "", "notes": clean(f.get("notes"), 1000), "items": [],
         "new_ref_name": clean(f.get("new_ref_name"), 120), "new_ref_clinic": clean(f.get("new_ref_clinic"), 150)}
    if v["branch_id"] not in g.user.branch_ids:
        errors.append("Choose the branch.")
    # who is X-rayed
    patient_id = v["patient_id"] if (x is None or x["patient_id"]) else None
    if patient_id is None and v["chart_no"]:
        p = conn.one("SELECT id FROM patients WHERE lower(chart_no) = lower(?) AND deleted_at IS NULL", (v["chart_no"],))
        if not p:
            errors.append(f"No patient with chart no. {v['chart_no']}. Leave it empty for a walk-in.")
        patient_id = p["id"] if p else None
    if patient_id:
        if not can_see_patient(conn, g.user, patient_id):
            abort(403)
        v["walkin_name"] = v["walkin_phone"] = ""
    elif not v["walkin_name"]:
        errors.append("Enter the walk-in's name (or the chart no. of a clinic patient).")
    d = parse_date(v["taken_on"])
    if not d or d > today():
        errors.append("Enter the date the X-ray was taken (not a future date).")
    # requested by
    requested_by = referrer_id = None
    kind, _, rid = v["requested"].partition(":")
    if kind == "d":
        requested_by = to_int(rid)
        if not conn.one("SELECT id FROM users WHERE id = ? AND role = 'dentist'", (requested_by,)):
            errors.append("Choose the dentist who asked for the X-ray.")
    elif kind == "r":
        referrer_id = to_int(rid)
        if not conn.one("SELECT id FROM xray_referrers WHERE id = ?", (referrer_id,)):
            errors.append("Choose the referring dentist.")
    elif v["requested"] == "new":
        if not v["new_ref_name"]:
            errors.append("Enter the name of the new referring dentist.")
    if v["taken_by"] and not conn.one("SELECT id FROM users WHERE id = ?", (v["taken_by"],)):
        v["taken_by"] = None
    # what was taken
    items = []
    for i in range(MAX_ITEMS):
        tid = to_int(f.get(f"type_{i}"))
        tooth = clean(f.get(f"tooth_{i}"), 60)
        raw = (f.get(f"price_{i}") or "").strip()
        if not tid and not raw and not tooth:
            continue
        v["items"].append({"type_id": tid, "tooth": tooth, "price": raw})
        t = tmap.get(tid)
        if not t:
            errors.append(f"Line {i + 1}: choose the X-ray type.")
            continue
        price = parse_money(raw) if raw else t["price_cents"]
        if price is None or price < 0:
            errors.append(f"Line {i + 1} ({t['name']}): enter the price (no price is set for this type yet).")
            continue
        items.append({"type_id": tid, "description": t["name"], "tooth": tooth, "price_cents": price})
    if not v["items"]:
        v["items"] = [{"type_id": None, "tooth": "", "price": ""}]
        errors.append("Add at least one X-ray.")
    subtotal = sum(i["price_cents"] for i in items)
    discount = parse_money(v["discount"]) if v["discount"].strip() else 0
    if discount is None or discount < 0 or discount > subtotal:
        errors.append("The discount must be between 0 and the total.")
        discount = 0
    total = subtotal - discount
    rebate = None
    if v["rebate"].strip():
        rebate = parse_money(v["rebate"])
        if rebate is None or rebate < 0 or rebate > total:
            errors.append("The rebate must be between 0 and the amount after discount.")
            rebate = 0
    if not (referrer_id or v["requested"] == "new") and rebate:
        errors.append("A rebate is only for X-rays referred by an outside dentist.")
    rec = {"branch_id": v["branch_id"], "patient_id": patient_id, "walkin_name": v["walkin_name"], "walkin_phone": v["walkin_phone"],
           "taken_on": d.isoformat() if d else "", "requested_by": requested_by, "referrer_id": referrer_id, "taken_by": v["taken_by"],
           "notes": v["notes"], "subtotal_cents": subtotal, "discount_cents": discount, "total_cents": total,
           "rebate_cents": rebate}
    return v, rec, items, errors


def _new_referrer(conn, v) -> int:
    rid = conn.insert("xray_referrers", {"name": v["new_ref_name"], "clinic": v["new_ref_clinic"], "created_at": now_str()})
    audit.record("xray_referrer_added", "xray_referrer", rid, f"Added referring dentist {v['new_ref_name']}")
    return rid


def _form_ctx(conn, v, x=None, patient=None, errors=()):
    scope = list(g.user.branch_ids)
    return {"v": v, "x": x, "patient": patient, "errors": errors, "types": types(conn), "referrers": referrers(conn),
            "dentists": dentists(), "staff": staff_choices(conn, scope), "branches": conn.all(
                f"SELECT id, name FROM branches WHERE active = 1 AND id IN ({_marks(scope)}) ORDER BY sort_order", scope),
            "pay_opts": pay_options(conn), "max_items": MAX_ITEMS}


@bp.route("/new", methods=["GET", "POST"])
@require("xray.manage")
def new():
    conn = get_db()
    patient = None
    pid = to_int(request.values.get("patient_id"))
    if pid:
        if not can_see_patient(conn, g.user, pid):
            abort(403)
        patient = conn.one("SELECT id, first_name, last_name, chart_no, preferred_branch_id FROM patients WHERE id = ?", (pid,))
        if not patient:
            abort(404)
    v = _form_values(conn)
    if patient:
        v.update(patient_id=patient["id"], chart_no=patient["chart_no"] or "")
        if patient["preferred_branch_id"] in g.user.branch_ids and not g.user.active_branch_id:
            v["branch_id"] = patient["preferred_branch_id"]
    if request.method == "POST":
        v, rec, items, errors = _read_form(conn)
        pay_amt = parse_money(request.form.get("pay_amount")) if (request.form.get("pay_amount") or "").strip() else 0
        pay = parse_pay(request.form.get("pay_method"), conn) if pay_amt else None
        if pay_amt and (pay_amt < 0 or pay_amt > rec["total_cents"]):
            errors.append("The payment can't be more than the amount to pay.")
        elif pay_amt and not pay:
            errors.append("Choose how the payment was made.")
        if not errors:
            with conn.transaction(immediate=True):
                if v["requested"] == "new":
                    rec["referrer_id"] = _new_referrer(conn, v)
                if rec["rebate_cents"] is None:
                    rec["rebate_cents"] = rebate_default(conn, rec["referrer_id"], rec["total_cents"])
                nxt = (conn.scalar("SELECT MAX(id) FROM xrays") or 0) + 1
                xid = conn.insert("xrays", {**rec, "number": f"XR-{nxt:06d}", "status": "ok", "created_by": g.user.id, "created_at": now_str()})
                for it in items:
                    conn.insert("xray_items", {"xray_id": xid, **it})
                if pay_amt:
                    conn.insert("xray_payments", {"xray_id": xid, "branch_id": rec["branch_id"], "amount_cents": pay_amt, "method": pay[0],
                                                  "account": pay[1], "received_at": now_str(), "received_by": g.user.id,
                                                  "created_at": now_str()})
                n, ferr = _add_files(conn, xid, request.files.getlist("files"))
            audit.record("xray_created", "xray", xid, f"Recorded X-ray XR-{nxt:06d}", {"items": len(items), "total": rec["total_cents"],
                                                                                        "images": n})
            for e in ferr:
                flash(e, "error")
            flash(f"X-ray XR-{nxt:06d} saved." + (" Payment recorded." if pay_amt else ""), "success")
            return redirect(url_for("xray.detail", xray_id=xid))
        return render_template("staff/xray/form.html", **_form_ctx(conn, v, patient=patient, errors=errors))
    return render_template("staff/xray/form.html", **_form_ctx(conn, v, patient=patient))


@bp.route("/<int:xray_id>/edit", methods=["GET", "POST"])
@require("xray.manage")
def edit(xray_id):
    """Change an X-ray record. Once a payment is recorded the amounts stay (void the payment first to change them)."""
    conn = get_db()
    x = _load(xray_id)
    if x["status"] != "ok":
        abort(404)
    paid = paid_of(conn, [xray_id]).get(xray_id, 0)
    locked = x["rebate_payout_id"] is not None
    patient = conn.one("SELECT id, first_name, last_name, chart_no FROM patients WHERE id = ?", (x["patient_id"],)) if x["patient_id"] else None
    if request.method == "POST":
        v, rec, items, errors = _read_form(conn, x)
        if rec["total_cents"] < paid:
            errors.append(f"The total can't be less than what's already paid ({paid / 100:,.2f}). Void a payment first.")
        if locked and (rec["rebate_cents"] if rec["rebate_cents"] is not None else x["rebate_cents"]) != x["rebate_cents"]:
            errors.append("The rebate was already paid out, so it can't be changed.")
        if not errors:
            with conn.transaction(immediate=True):
                if v["requested"] == "new":
                    rec["referrer_id"] = _new_referrer(conn, v)
                if rec["rebate_cents"] is None:
                    rec["rebate_cents"] = rebate_default(conn, rec["referrer_id"], rec["total_cents"])
                if locked:
                    rec["referrer_id"] = x["referrer_id"]
                rec["updated_at"] = now_str()
                conn.update("xrays", xray_id, rec)
                conn.execute("DELETE FROM xray_items WHERE xray_id = ?", (xray_id,))
                for it in items:
                    conn.insert("xray_items", {"xray_id": xray_id, **it})
            audit.record("xray_edited", "xray", xray_id, f"Edited X-ray {x['number']}",
                         audit.diff(dict(x), rec, ["taken_on", "requested_by", "referrer_id", "taken_by", "total_cents", "discount_cents", "rebate_cents"]))
            flash("X-ray updated.", "success")
            return redirect(url_for("xray.detail", xray_id=xray_id))
        return render_template("staff/xray/form.html", **_form_ctx(conn, v, x=x, patient=patient, errors=errors))
    return render_template("staff/xray/form.html", **_form_ctx(conn, _form_values(conn, x), x=x, patient=patient))


# ---------------------------------------------------------------------------
# Detail, payments, images, void
# ---------------------------------------------------------------------------

@bp.route("/<int:xray_id>")
@require("xray.view")
def detail(xray_id):
    conn = get_db()
    x = _load(xray_id)
    items = conn.all("SELECT * FROM xray_items WHERE xray_id = ? ORDER BY id", (xray_id,))
    pays = conn.all("SELECT p.*, u.name AS received_name FROM xray_payments p LEFT JOIN users u ON u.id = p.received_by "
                    "WHERE p.xray_id = ? ORDER BY p.received_at, p.id", (xray_id,))
    files = conn.all("SELECT * FROM xray_files WHERE xray_id = ? ORDER BY id", (xray_id,))
    paid = sum(p["amount_cents"] for p in pays if p["status"] == "valid")
    payout = conn.one("SELECT * FROM xray_rebate_payouts WHERE id = ?", (x["rebate_payout_id"],)) if x["rebate_payout_id"] else None
    return render_template("staff/xray/detail.html", x=x, who=who(x), requested=requested_label(x), items=items, pays=pays, files=files,
                           paid=paid, balance=x["total_cents"] - paid if x["status"] == "ok" else 0, pay_opts=pay_options(conn),
                           pay_label=pay_label, payout=payout)


@bp.route("/<int:xray_id>/pay", methods=["POST"])
@require("xray.manage")
def pay(xray_id):
    conn = get_db()
    x = _load(xray_id)
    paid = paid_of(conn, [xray_id]).get(xray_id, 0)
    amt = parse_money(request.form.get("amount"))
    method = parse_pay(request.form.get("method"), conn)
    if x["status"] != "ok":
        flash("This X-ray is voided.", "error")
    elif not amt or amt <= 0 or amt > x["total_cents"] - paid:
        flash(f"Enter an amount up to the balance ({(x['total_cents'] - paid) / 100:,.2f}).", "error")
    elif not method:
        flash("Choose how the payment was made.", "error")
    else:
        pid = conn.insert("xray_payments", {"xray_id": xray_id, "branch_id": x["branch_id"], "amount_cents": amt, "method": method[0],
                                            "account": method[1], "reference": clean(request.form.get("reference"), 80),
                                            "received_at": now_str(), "received_by": g.user.id, "created_at": now_str()})
        audit.record("xray_payment", "xray", xray_id, f"Payment on X-ray {x['number']}", {"payment": pid, "amount": amt})
        flash("Payment recorded.", "success")
    return redirect(url_for("xray.detail", xray_id=xray_id))


@bp.route("/<int:xray_id>/payments/<int:pay_id>/void", methods=["POST"])
@require("xray.void")
def pay_void(xray_id, pay_id):
    conn = get_db()
    x = _load(xray_id)
    p = conn.one("SELECT * FROM xray_payments WHERE id = ? AND xray_id = ? AND status = 'valid'", (pay_id, xray_id))
    reason = clean(request.form.get("reason"), 300)
    if not p:
        abort(404)
    if len(reason) < 3:
        flash("Write why the payment is voided.", "error")
    else:
        conn.execute("UPDATE xray_payments SET status = 'void', void_reason = ? WHERE id = ?", (reason, pay_id))
        audit.record("xray_payment_voided", "xray", xray_id, f"Voided a payment on X-ray {x['number']}", {"payment": pay_id, "reason": reason})
        flash("Payment voided.", "success")
    return redirect(url_for("xray.detail", xray_id=xray_id))


@bp.route("/<int:xray_id>/void", methods=["POST"])
@require("xray.void")
def void(xray_id):
    conn = get_db()
    x = _load(xray_id)
    reason = clean(request.form.get("reason"), 300)
    if x["status"] != "ok":
        abort(404)
    if paid_of(conn, [xray_id]).get(xray_id, 0):
        flash("Void its payments first.", "error")
    elif x["rebate_payout_id"]:
        flash("Its rebate was already paid out. Void that payout first (Rebates).", "error")
    elif len(reason) < 3:
        flash("Write why this X-ray is voided.", "error")
    else:
        conn.execute("UPDATE xrays SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                     (reason, g.user.id, now_str(), xray_id))
        audit.record("xray_voided", "xray", xray_id, f"Voided X-ray {x['number']}", {"reason": reason})
        flash("X-ray voided.", "success")
    return redirect(url_for("xray.detail", xray_id=xray_id))


@bp.route("/<int:xray_id>/files", methods=["POST"])
@require("xray.manage")
def files_add(xray_id):
    conn = get_db()
    x = _load(xray_id)
    if x["status"] != "ok":
        abort(404)
    n, errors = _add_files(conn, xray_id, request.files.getlist("files"))
    for e in errors:
        flash(e, "error")
    if n:
        audit.record("xray_images_added", "xray", xray_id, f"Added {n} image(s) to X-ray {x['number']}")
        flash(f"{n} file(s) added.", "success")
    elif not errors:
        flash("Choose the image files.", "error")
    return redirect(url_for("xray.detail", xray_id=xray_id))


def _file(file_id):
    f = get_db().one("SELECT * FROM xray_files WHERE id = ?", (file_id,))
    if not f:
        abort(404)
    _load(f["xray_id"])
    return f


@bp.route("/files/<int:file_id>")
@require("xray.view")
def file(file_id):
    f = _file(file_id)
    try:
        path = document_path(f["stored_name"])
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    resp = send_file(path, mimetype=f["mime"], as_attachment=request.args.get("download") == "1", download_name=f["original_name"])
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/files/<int:file_id>/delete", methods=["POST"])
@require("xray.manage")
def file_delete(file_id):
    conn = get_db()
    f = _file(file_id)
    conn.execute("DELETE FROM xray_files WHERE id = ?", (file_id,))
    try:
        document_path(f["stored_name"]).unlink(missing_ok=True)
    except ValueError:
        pass
    audit.record("xray_image_deleted", "xray", f["xray_id"], f"Deleted X-ray image {f['original_name']}")
    flash("File deleted.", "success")
    return redirect(url_for("xray.detail", xray_id=f["xray_id"]))


@bp.route("/<int:xray_id>/receipt")
@require("xray.view")
def receipt(xray_id):
    conn = get_db()
    x = _load(xray_id)
    items = conn.all("SELECT * FROM xray_items WHERE xray_id = ? ORDER BY id", (xray_id,))
    pays = conn.all("SELECT * FROM xray_payments WHERE xray_id = ? AND status = 'valid' ORDER BY received_at, id", (xray_id,))
    paid = sum(p["amount_cents"] for p in pays)
    return render_template("staff/xray/receipt.html", x=x, who=who(x), requested=requested_label(x), items=items, pays=pays, paid=paid,
                           pay_label=pay_label)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@bp.route("/report")
@require("xray.view")
def report():
    conn = get_db()
    start, end = date_range_args(31)
    scope = _scope()
    s, e = start.isoformat(), end.isoformat()
    base = f"FROM xrays x WHERE x.status = 'ok' AND x.branch_id IN ({_marks(scope)}) AND x.taken_on BETWEEN ? AND ?"
    args = [*scope, s, e]
    sums = conn.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(subtotal_cents), 0) AS gross, COALESCE(SUM(discount_cents), 0) AS discount, "
                    f"COALESCE(SUM(total_cents), 0) AS net, COALESCE(SUM(rebate_cents), 0) AS rebates, "
                    f"SUM(CASE WHEN patient_id IS NULL THEN 1 ELSE 0 END) AS walkins, "
                    f"SUM(CASE WHEN referrer_id IS NOT NULL THEN 1 ELSE 0 END) AS referred {base}", args)
    by_type = conn.all(f"SELECT i.description AS name, COUNT(*) AS n, SUM(i.price_cents) AS amt FROM xray_items i JOIN xrays x ON x.id = i.xray_id "
                       f"WHERE x.status = 'ok' AND x.branch_id IN ({_marks(scope)}) AND x.taken_on BETWEEN ? AND ? GROUP BY i.description ORDER BY n DESC", args)
    by_branch = conn.all(f"SELECT b.name, COUNT(*) AS n, SUM(x.total_cents) AS net FROM xrays x JOIN branches b ON b.id = x.branch_id "
                         f"WHERE x.status = 'ok' AND x.branch_id IN ({_marks(scope)}) AND x.taken_on BETWEEN ? AND ? GROUP BY b.name ORDER BY b.name", args)
    by_ref = conn.all(f"SELECT r.name, r.clinic, COUNT(*) AS n, SUM(x.total_cents) AS net, SUM(x.rebate_cents) AS rebate FROM xrays x "
                      f"JOIN xray_referrers r ON r.id = x.referrer_id WHERE x.status = 'ok' AND x.branch_id IN ({_marks(scope)}) "
                      f"AND x.taken_on BETWEEN ? AND ? GROUP BY r.id ORDER BY n DESC", args)
    by_taker = conn.all(f"SELECT COALESCE(u.name, 'Not recorded') AS name, COUNT(*) AS n FROM xrays x LEFT JOIN users u ON u.id = x.taken_by "
                        f"WHERE x.status = 'ok' AND x.branch_id IN ({_marks(scope)}) AND x.taken_on BETWEEN ? AND ? GROUP BY u.id ORDER BY n DESC", args)
    pays = conn.all(f"SELECT method, account, SUM(amount_cents) AS amt, COUNT(*) AS n FROM xray_payments WHERE status = 'valid' "
                    f"AND branch_id IN ({_marks(scope)}) AND substr(received_at, 1, 10) BETWEEN ? AND ? GROUP BY method, account ORDER BY amt DESC", args)
    rows = conn.all(f"SELECT x.id, x.total_cents FROM xrays x WHERE x.status = 'ok' AND x.branch_id IN ({_marks(scope)})", scope)
    paid = paid_of(conn, [r["id"] for r in rows])
    open_bal = [r["total_cents"] - paid.get(r["id"], 0) for r in rows if r["total_cents"] > paid.get(r["id"], 0)]
    return render_template("staff/xray/report.html", start=start, end=end, sums=sums, by_type=by_type, by_branch=by_branch, by_ref=by_ref,
                           by_taker=by_taker, pays=[{**dict(p), "label": pay_label(p["method"], p["account"])} for p in pays],
                           collected=sum(p["amt"] for p in pays), open_n=len(open_bal), open_total=sum(open_bal))


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

@bp.route("/prices", methods=["GET", "POST"])
@require("fees.manage")
def prices():
    conn = get_db()
    if request.method == "POST":
        changed = 0
        for t in types(conn, active_only=False):
            raw = (request.form.get(f"price_{t['id']}") or "").strip()
            price = parse_money(raw) if raw else None
            if raw and (price is None or price < 0):
                flash(f"{t['name']}: the price isn't a valid amount.", "error")
                continue
            active = 1 if request.form.get(f"active_{t['id']}") else 0
            if price != t["price_cents"] or active != t["active"]:
                conn.update("xray_types", t["id"], {"price_cents": price, "active": active})
                changed += 1
        name = clean(request.form.get("new_name"), 80)
        if name:
            if conn.one("SELECT id FROM xray_types WHERE lower(name) = lower(?)", (name,)):
                flash(f"{name} is already on the list.", "error")
            else:
                raw = (request.form.get("new_price") or "").strip()
                conn.insert("xray_types", {"name": name, "price_cents": parse_money(raw) if raw else None,
                                           "sort_order": (conn.scalar("SELECT MAX(sort_order) FROM xray_types") or 0) + 1})
                changed += 1
        if changed:
            audit.record("xray_prices_changed", "xray_type", None, f"Changed the X-ray price list ({changed} change(s))")
            flash("X-ray price list saved.", "success")
        return redirect(url_for("xray.prices"))
    return render_template("staff/xray/prices.html", types=types(conn, active_only=False))


# ---------------------------------------------------------------------------
# Referring dentists and rebates
# ---------------------------------------------------------------------------

def _year():
    y = to_int(request.values.get("year")) or today().year
    return y if 2000 <= y <= 2100 else today().year


@bp.route("/rebates", methods=["GET", "POST"])
@require("xray.rebates")
def rebates():
    conn = get_db()
    if request.method == "POST":           # add a referring dentist
        name = clean(request.form.get("name"), 120)
        bp_ = _rate(request.form.get("rate"))
        if not name:
            flash("Enter the dentist's name.", "error")
        elif bp_ is False:
            flash("The rebate % must be between 0 and 100.", "error")
        else:
            rid = conn.insert("xray_referrers", {"name": name, "clinic": clean(request.form.get("clinic"), 150),
                                                 "phone": clean(request.form.get("phone"), 40), "rebate_bp": bp_, "created_at": now_str()})
            audit.record("xray_referrer_added", "xray_referrer", rid, f"Added referring dentist {name}")
            flash(f"{name} added.", "success")
        return redirect(url_for("xray.rebates", year=_year()))
    year = _year()
    rows = conn.all("SELECT r.*, COUNT(x.id) AS n, COALESCE(SUM(x.total_cents), 0) AS net, COALESCE(SUM(x.rebate_cents), 0) AS earned, "
                    "COALESCE(SUM(CASE WHEN x.rebate_payout_id IS NOT NULL THEN x.rebate_cents ELSE 0 END), 0) AS paid_out "
                    "FROM xray_referrers r LEFT JOIN xrays x ON x.referrer_id = r.id AND x.status = 'ok' AND substr(x.taken_on, 1, 4) = ? "
                    "GROUP BY r.id ORDER BY r.active DESC, r.name", (str(year),))
    unpaid_before = {r["referrer_id"]: r["amt"] for r in conn.all(
        "SELECT referrer_id, SUM(rebate_cents) AS amt FROM xrays WHERE status = 'ok' AND rebate_payout_id IS NULL AND rebate_cents > 0 "
        "AND substr(taken_on, 1, 4) < ? GROUP BY referrer_id", (str(year),))}
    return render_template("staff/xray/rebates.html", rows=rows, year=year, unpaid_before=unpaid_before,
                           years=list(range(today().year, today().year - 6, -1)))


def _rate(raw):
    raw = (raw or "").strip().rstrip("%")
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        return False
    return round(v * 100) if 0 <= v <= 100 else False


@bp.route("/rebates/<int:ref_id>", methods=["GET", "POST"])
@require("xray.rebates")
def referrer(ref_id):
    conn = get_db()
    r = conn.one("SELECT * FROM xray_referrers WHERE id = ?", (ref_id,))
    if not r:
        abort(404)
    year = _year()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "edit":
            bp_ = _rate(request.form.get("rate"))
            name = clean(request.form.get("name"), 120)
            if not name or bp_ is False:
                flash("Enter the name, and a rebate % between 0 and 100.", "error")
            else:
                vals = {"name": name, "clinic": clean(request.form.get("clinic"), 150), "phone": clean(request.form.get("phone"), 40),
                        "rebate_bp": bp_, "active": 1 if request.form.get("active") else 0}
                conn.update("xray_referrers", ref_id, vals)
                audit.record("xray_referrer_edited", "xray_referrer", ref_id, f"Edited referring dentist {name}",
                             audit.diff(dict(r), vals, vals.keys()))
                flash("Saved.", "success")
        elif action == "payout":
            ids = [i for i in (to_int(x) for x in request.form.getlist("ids")) if i]
            pay = parse_pay(request.form.get("method"), conn)
            paid_on = parse_date(request.form.get("paid_on"))
            rows = conn.all(f"SELECT id, rebate_cents FROM xrays WHERE id IN ({_marks(ids)}) AND referrer_id = ? AND status = 'ok' "
                            f"AND rebate_payout_id IS NULL AND rebate_cents > 0", [*ids, ref_id]) if ids else []
            if not rows:
                flash("Tick the X-rays whose rebate you are paying.", "error")
            elif not pay or not paid_on:
                flash("Enter the date and how the rebate was paid.", "error")
            else:
                amt = sum(x["rebate_cents"] for x in rows)
                with conn.transaction(immediate=True):
                    po = conn.insert("xray_rebate_payouts", {"referrer_id": ref_id, "paid_on": paid_on.isoformat(), "amount_cents": amt,
                                                             "method": pay[0], "account": pay[1], "reference": clean(request.form.get("reference"), 80),
                                                             "notes": clean(request.form.get("notes"), 300), "created_by": g.user.id,
                                                             "created_at": now_str()})
                    conn.execute(f"UPDATE xrays SET rebate_payout_id = ? WHERE id IN ({_marks([x['id'] for x in rows])})",
                                 [po, *[x["id"] for x in rows]])
                audit.record("xray_rebate_paid", "xray_referrer", ref_id, f"Paid rebate to {r['name']}", {"payout": po, "amount": amt,
                                                                                                        "xrays": len(rows)})
                flash(f"Rebate payout of {amt / 100:,.2f} recorded for {len(rows)} X-ray(s).", "success")
        return redirect(url_for("xray.referrer", ref_id=ref_id, year=year))
    xs = conn.all("SELECT x.*, p.first_name, p.last_name, p.chart_no, b.name AS branch FROM xrays x JOIN branches b ON b.id = x.branch_id "
                  "LEFT JOIN patients p ON p.id = x.patient_id WHERE x.referrer_id = ? AND x.status = 'ok' "
                  "AND (substr(x.taken_on, 1, 4) = ? OR (x.rebate_payout_id IS NULL AND x.rebate_cents > 0 AND substr(x.taken_on, 1, 4) < ?)) "
                  "ORDER BY x.taken_on, x.id", (ref_id, str(year), str(year)))
    paid = paid_of(conn, [x["id"] for x in xs])
    items = [{**dict(x), "who": who(x), "fully_paid": paid.get(x["id"], 0) >= x["total_cents"]} for x in xs]
    payouts = conn.all("SELECT po.*, u.name AS by_name, (SELECT COUNT(*) FROM xrays WHERE rebate_payout_id = po.id) AS n "
                       "FROM xray_rebate_payouts po LEFT JOIN users u ON u.id = po.created_by WHERE po.referrer_id = ? ORDER BY po.paid_on DESC, po.id DESC",
                       (ref_id,))
    return render_template("staff/xray/referrer.html", r=r, year=year, items=items, payouts=payouts, pay_opts=pay_options(conn),
                           pay_label=pay_label, years=list(range(today().year, today().year - 6, -1)),
                           default_paid_on=today().isoformat())


@bp.route("/rebates/payouts/<int:payout_id>/void", methods=["POST"])
@require("xray.rebates")
def payout_void(payout_id):
    conn = get_db()
    po = conn.one("SELECT * FROM xray_rebate_payouts WHERE id = ? AND status = 'ok'", (payout_id,))
    if not po:
        abort(404)
    reason = clean(request.form.get("reason"), 300)
    if len(reason) < 3:
        flash("Write why the payout is voided.", "error")
    else:
        with conn.transaction(immediate=True):
            conn.execute("UPDATE xray_rebate_payouts SET status = 'void', void_reason = ? WHERE id = ?", (reason, payout_id))
            conn.execute("UPDATE xrays SET rebate_payout_id = NULL WHERE rebate_payout_id = ?", (payout_id,))
        audit.record("xray_rebate_payout_voided", "xray_referrer", po["referrer_id"], "Voided a rebate payout", {"payout": payout_id, "reason": reason})
        flash("Payout voided. Its X-rays are unpaid again.", "success")
    return redirect(url_for("xray.referrer", ref_id=po["referrer_id"], year=request.form.get("year") or ""))


# ---------------------------------------------------------------------------
# X-rays added in a progress note
# ---------------------------------------------------------------------------

def type_for(conn, desc: str):
    """The X-ray type of a progress-note service ('PANORAMIC XRAY', 'Cephalo Xray - PA View', 'CBCT SCAN'...), or None.
    Periapicals stay procedures billed with the visit."""
    import re
    d = (desc or "").lower()
    if not d or "periapical" in d:
        return None
    ts = {t["name"].lower(): t for t in types(conn)}
    if d.strip() in ts:
        return ts[d.strip()]
    xray_word = bool(re.search(r"x-?\s?ray", d))
    if "cbct" in d:
        return ts.get("cbct")
    if "panoram" in d:
        return ts.get("panoramic")
    if "ceph" in d:
        return ts.get("cephalometric - pa view") if re.search(r"\bpa\b|postero", d) else ts.get("cephalometric - lateral")
    if "tmj" in d and xray_word:
        return ts.get("tmj")
    if xray_word:
        for name, t in ts.items():
            if len(name) > 3 and name in d:
                return t
    return None


def create_from_visit(conn, patient_id, branch_id, dentist_id, visit_date, xlines, visit_note_id=None) -> tuple[int, str]:
    """An unpaid X-ray record for the X-rays a dentist added in a progress note. Returns (id, number)."""
    nxt = (conn.scalar("SELECT MAX(id) FROM xrays") or 0) + 1
    number = f"XR-{nxt:06d}"
    items = []
    for ln, t in xlines:
        unit = ln["unit"] if ln["unit"] > 0 else (t["price_cents"] or 0)
        items.append({"type_id": t["id"], "description": t["name"], "tooth": ln.get("tooth") or "",
                      "price_cents": max(0, unit * ln["qty"] - ln["disc_cents"])})
    total = sum(i["price_cents"] for i in items)
    xid = conn.insert("xrays", {"number": number, "branch_id": branch_id, "patient_id": patient_id, "taken_on": visit_date,
                                "requested_by": dentist_id, "notes": "From progress note", "subtotal_cents": total, "discount_cents": 0,
                                "total_cents": total, "rebate_cents": 0, "status": "ok", "created_by": g.user.id, "created_at": now_str(),
                                "visit_note_id": visit_note_id})
    for it in items:
        conn.insert("xray_items", {"xray_id": xid, **it})
    return xid, number

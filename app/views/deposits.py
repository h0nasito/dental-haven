"""Bank deposits of cash collections, per branch, with the deposit slip; and the cash book (cash on hand)."""
from __future__ import annotations

import csv
import io

from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, send_file, url_for

from .. import audit
from ..auth import require
from ..cash_deposits import book, net_cash, on_hand, since
from ..db import get_db
from ..uploads import IMAGE_TYPES, document_path, save_document, save_private_photo, sniff
from ..util import clean, now_str, parse_date, parse_money, to_int, today
from .common import branches_for_user, date_range_args

bp = Blueprint("deposits", __name__, url_prefix="/staff/deposits")
MAX_PHOTOS = 4


def bank_list(conn):
    from ..billing import banks
    return banks(conn)


def _branch(conn):
    branches = branches_for_user(g.user)
    ids = [b["id"] for b in branches]
    bid = to_int(request.values.get("branch"))
    if bid not in ids:
        scope = [i for i in (g.user.scope_branch_ids or []) if i in ids]
        bid = scope[0] if scope else (ids[0] if ids else None)
    if not bid:
        abort(403)
    return bid, branches


def _save_slip(f):
    """A deposit slip: a photo (made small) or a PDF scan. Returns (stored name, error)."""
    head = f.stream.read(16)
    f.stream.seek(0)
    if sniff(head) in IMAGE_TYPES:
        return save_private_photo(f, "deposits")
    stored, _mime, _size, _orig, err = save_document(f)
    return stored, err


@bp.route("/", methods=["GET", "POST"])
@require("deposits.view", "deposits.manage", any_of=True)
def index():
    conn = get_db()
    bid, branches = _branch(conn)
    if request.method == "POST" and request.form.get("action") == "since":
        if not g.user.is_super_admin:
            abort(403)
        d = parse_date(request.form.get("since"))
        if d and d <= today():
            from .. import settings
            settings.put("deposits.since", d.isoformat(), g.user.id, conn)
            audit.record("cash_deposits_since", "cash_deposit", None, f"Cash on hand counted from {d.isoformat()}")
            flash("Saved.", "success")
        return redirect(url_for("deposits.index", branch=bid))
    if request.method == "POST":
        if not g.user.can("deposits.manage"):
            abort(403)
        f = request.form
        d = parse_date(f.get("deposit_date"))
        amt = parse_money(f.get("amount"))
        c_from, c_to = parse_date(f.get("cash_from")), parse_date(f.get("cash_to"))
        if c_from and not c_to:
            c_to = c_from
        if c_to and not c_from:
            c_from = c_to
        slips = [x for x in request.files.getlist("slip") if x and x.filename][:MAX_PHOTOS]
        if not d or d > today():
            flash("Enter the deposit date (not in the future).", "error")
        elif amt is None or amt <= 0:
            flash("Enter the amount deposited.", "error")
        elif clean(f.get("bank"), 80) not in bank_list(conn):
            flash("Choose the bank.", "error")
        elif c_from and c_from > c_to:
            flash("The collection dates are the wrong way round.", "error")
        elif not slips:
            flash("Attach a picture of the deposit slip.", "error")
        else:
            saved = []
            for x in slips:
                stored, err = _save_slip(x)
                if err:
                    flash(f"Deposit slip picture: {err}", "error")
                    return redirect(url_for("deposits.index", branch=bid))
                saved.append(stored)
            expected = net_cash(conn, bid, c_from.isoformat(), c_to.isoformat()) if c_from else 0
            with conn.transaction():
                did = conn.insert("cash_deposits", {
                    "branch_id": bid, "deposit_date": d.isoformat(), "cash_from": c_from.isoformat() if c_from else "",
                    "cash_to": c_to.isoformat() if c_to else "", "bank": clean(f.get("bank"), 80), "account": clean(f.get("account"), 40),
                    "slip_no": clean(f.get("slip_no"), 60), "amount_cents": amt, "expected_cents": expected,
                    "deposited_by": clean(f.get("deposited_by"), 120) or g.user.name, "notes": clean(f.get("notes"), 500),
                    "slip_stored": saved[0], "created_by": g.user.id, "created_at": now_str()})
                for stored in saved:
                    conn.insert("cash_deposit_photos", {"deposit_id": did, "stored_name": stored, "uploaded_by": g.user.id, "created_at": now_str()})
                audit.record("cash_deposit_recorded", "cash_deposit", did, f"Bank deposit ₱{amt / 100:,.2f} on {d.isoformat()}"
                             + (f" for cash of {c_from} to {c_to}" if c_from else ""))
            if c_from and expected != amt:
                diff = amt - expected
                flash(f"Deposit saved. It is ₱{abs(diff) / 100:,.2f} {'more' if diff > 0 else 'less'} than the cash for those days "
                      f"(₱{expected / 100:,.2f}). Add a note if this is expected.", "warning")
            else:
                flash("Deposit saved.", "success")
            return redirect(url_for("deposits.index", branch=bid))
    start, end = date_range_args(default_days=31)
    if "from" not in request.args:
        start = today().replace(day=1)
    cb = book(conn, bid, start, end)
    deposits = conn.all("SELECT d.*, u.name AS by_name FROM cash_deposits d LEFT JOIN users u ON u.id = d.created_by "
                        "WHERE d.branch_id = ? AND d.deposit_date BETWEEN ? AND ? ORDER BY d.deposit_date DESC, d.id DESC",
                        (bid, start.isoformat(), end.isoformat()))
    photos: dict[int, list] = {}
    if deposits:
        ids = [d["id"] for d in deposits]
        for ph in conn.all(f"SELECT * FROM cash_deposit_photos WHERE deposit_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids):
            photos.setdefault(ph["deposit_id"], []).append(ph)
    banks = [r["bank"] for r in conn.all("SELECT bank, MAX(id) AS m FROM cash_deposits WHERE bank != '' GROUP BY bank ORDER BY m DESC LIMIT 10")]
    last = conn.one("SELECT bank, account FROM cash_deposits WHERE branch_id = ? AND status = 'ok' ORDER BY id DESC LIMIT 1", (bid,))
    last_cov = conn.scalar("SELECT MAX(cash_to) FROM cash_deposits WHERE branch_id = ? AND status = 'ok' AND cash_to != ''", (bid,))
    yesterday = (today() - timedelta(days=1)).isoformat()
    sugg_from = max(since(conn), (parse_date(last_cov) + timedelta(days=1)).isoformat() if last_cov else since(conn))
    sugg_to = max(sugg_from, yesterday) if sugg_from <= yesterday else today().isoformat()
    if request.args.get("format") == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Cash collected", "Cash refunds", "Cash expenses", "Net cash", "Deposited", "Cash on hand"])
        w.writerow(["Opening", "", "", "", "", "", cb["opening"] / 100])
        for r in cb["rows"]:
            w.writerow([r["day"], r["in"] / 100, r["refunds"] / 100, r["expenses"] / 100, r["net"] / 100, r["deposited"] / 100, r["balance"] / 100])
        w.writerow([])
        w.writerow(["Deposit date", "Bank", "Account", "Slip no.", "Cash of", "Expected", "Deposited", "Difference", "Deposited by", "Status", "Notes"])
        safe = lambda x: ("'" + x) if isinstance(x, str) and x[:1] in ("=", "+", "-", "@") else x  # noqa: E731
        for d in deposits:
            cov = f"{d['cash_from']} to {d['cash_to']}" if d["cash_from"] else ""
            w.writerow([safe(x) for x in (d["deposit_date"], d["bank"], d["account"], d["slip_no"], cov,
                                          d["expected_cents"] / 100 if cov else "", d["amount_cents"] / 100,
                                          (d["amount_cents"] - d["expected_cents"]) / 100 if cov else "", d["deposited_by"],
                                          "Void" if d["status"] == "void" else "OK", d["notes"])])
        audit.record("cash_deposits_exported", "cash_deposit", None, f"Exported cash book {start} to {end}")
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="cash-book-{start}-to-{end}.csv"', "Cache-Control": "no-store"})
    return render_template("staff/deposits/index.html", bid=bid, branches=branches, cb=cb, deposits=deposits, start=start, end=end,
                           on_hand=on_hand(conn, bid), banks=banks, last=last, today=today().isoformat(), sugg_from=sugg_from, sugg_to=sugg_to,
                           sugg_amount=net_cash(conn, bid, sugg_from, sugg_to), can_manage=g.user.can("deposits.manage"),
                           photos=photos, max_photos=MAX_PHOTOS, bank_list=bank_list(conn))


def _load(deposit_id):
    d = get_db().one("SELECT * FROM cash_deposits WHERE id = ?", (deposit_id,))
    if not d or not g.user.in_branch(d["branch_id"]):
        abort(404)
    return d


@bp.route("/<int:deposit_id>/slip")
@bp.route("/<int:deposit_id>/slip/<int:photo_id>")
@require("deposits.view", "deposits.manage", any_of=True)
def slip(deposit_id, photo_id=None):
    d = _load(deposit_id)
    ph = get_db().one("SELECT * FROM cash_deposit_photos WHERE deposit_id = ?" + (" AND id = ?" if photo_id else " ORDER BY id LIMIT 1"),
                      (d["id"], photo_id) if photo_id else (d["id"],))
    if not ph:
        abort(404)
    resp = send_file(document_path(ph["stored_name"]), max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/<int:deposit_id>/photos", methods=["POST"])
@require("deposits.manage")
def add_photos(deposit_id):
    """Add pictures to a deposit later (e.g. the bank-validated copy of the slip)."""
    d = _load(deposit_id)
    conn = get_db()
    have = conn.scalar("SELECT COUNT(*) FROM cash_deposit_photos WHERE deposit_id = ?", (d["id"],)) or 0
    files = [x for x in request.files.getlist("slip") if x and x.filename][:max(0, MAX_PHOTOS - have)]
    if d["status"] != "ok" or not files:
        flash(f"Choose a picture (up to {MAX_PHOTOS} per deposit).", "error")
        return redirect(url_for("deposits.index", branch=d["branch_id"]))
    n = 0
    for x in files:
        stored, err = _save_slip(x)
        if err:
            flash(f"Picture: {err}", "error")
            break
        conn.insert("cash_deposit_photos", {"deposit_id": d["id"], "stored_name": stored, "uploaded_by": g.user.id, "created_at": now_str()})
        if not d["slip_stored"]:
            conn.execute("UPDATE cash_deposits SET slip_stored = ? WHERE id = ?", (stored, d["id"]))
        n += 1
    if n:
        audit.record("cash_deposit_photo_added", "cash_deposit", d["id"], f"Added {n} picture(s) to the deposit of {d['deposit_date']}")
        flash("Picture added.", "success")
    return redirect(url_for("deposits.index", branch=d["branch_id"]))


@bp.route("/<int:deposit_id>/void", methods=["POST"])
@require("deposits.manage")
def void(deposit_id):
    d = _load(deposit_id)
    reason = clean(request.form.get("reason"), 300)
    if d["status"] != "ok":
        abort(400)
    if len(reason) < 3:
        flash("Enter the reason for voiding.", "error")
    else:
        conn = get_db()
        with conn.transaction():
            conn.execute("UPDATE cash_deposits SET status = 'void', void_reason = ?, voided_by = ?, voided_at = ? WHERE id = ?",
                         (reason, g.user.id, now_str(), d["id"]))
            audit.record("cash_deposit_voided", "cash_deposit", d["id"], f"Voided deposit of ₱{d['amount_cents'] / 100:,.2f} on {d['deposit_date']}: {reason}")
        flash("Deposit voided.", "success")
    return redirect(url_for("deposits.index", branch=d["branch_id"]))

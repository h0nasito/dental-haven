"""My cases (dentists): the cases that are assigned AND billed to the dentist: patients assigned to them, and only the
types of case (Orthodontics, Prosthodontics, ...) where they are the dentist on the bill. Nothing else is listed.

Read-only. For each case: visits in that category, what was billed and paid (each bill's payments are shared over its
lines in proportion), and for orthodontic cases whether the patient comes every month for the adjustment.
Dentists see their own cases; a super admin can choose a dentist.
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, g, render_template, request

from ..auth import login_required
from ..db import get_db
from ..util import clean, parse_date, to_int, today

bp = Blueprint("cases", __name__, url_prefix="/staff/my-cases")

from ..case_types import GENERAL, ORTHO, Classifier  # noqa: E402  (type of case: fee schedule groups, see case_types.py)


def _dentist():
    """The dentist whose cases are shown: yourself, or (super admin) the one chosen."""
    conn = get_db()
    dentists = conn.all("SELECT id, name FROM users WHERE role = 'dentist' AND active = 1 ORDER BY name")
    if g.user.role == "dentist":
        return g.user.id, dentists
    if g.user.is_super_admin:
        did = to_int(request.args.get("dentist"))
        return (did if did in {d["id"] for d in dentists} else (dentists[0]["id"] if dentists else None)), dentists
    abort(403)


def _months_between(a: date, b: date) -> list[str]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _commissions(conn, dentist_id: int, lines: dict) -> dict:
    """The dentist's commission per (bill, type of case), counted the way payroll counts it: per procedure (bill lines,
    System settings → Payroll) or per payment (what the cashier recorded on the payments). Manual commission entries on a
    bill always count. An entry for a whole bill is shared over the dentist's types of case on it, in proportion."""
    from ..payroll import commission_items, dentist_rates, per_procedure
    emp = conn.one("SELECT id FROM employees WHERE user_id = ?", (dentist_id,))
    out: dict = {}
    by_inv: dict[int, list] = {}
    for k, x in lines.items():
        by_inv.setdefault(k[0], []).append((k, x["billed"]))

    weights = _commission_weights(conn, emp["id"] if emp else None, lines)

    def share(inv, amount):
        """Split the bill's commission over the dentist's types of case by what each earns (its commission base after the
        lab fee, or its fixed amount), not by price: a ₱16,000 retainer with a ₱1,760 lab fee and ₱3,050 of fillings
        earning 30% get ₱4,272 and ₱915."""
        parts = [(k, weights.get(k, 0)) for k, _ in (by_inv.get(inv) or [])]
        if not sum(w for _, w in parts):
            parts = [(k, b) for k, b in (by_inv.get(inv) or [])]
        tot = sum(w for _, w in parts)
        for k, w in parts:
            out[k] = out.get(k, 0) + (round(amount * w / tot) if tot else (amount if len(parts) == 1 else 0))

    if per_procedure(conn):
        r = dentist_rates(conn, emp["id"], today().isoformat()) if emp else None
        svc = {s["service_id"]: s["commission_bp"] for s in conn.all("SELECT * FROM dentist_service_rates WHERE employee_id = ?", (emp["id"],))} if emp else {}
        per_line = {i["id"]: i["commission_cents"] or 0
                    for i in commission_items(conn, dentist_id, "0000-01-01", "9999-12-31", None, (r["commission_bp"] or 0) if r else 0, svc)}
        for k, x in lines.items():
            out[k] = out.get(k, 0) + sum(per_line.get(lid, 0) for lid in x["line_ids"])
    if emp and by_inv:
        marks = ",".join("?" * len(by_inv))
        for m in conn.all(f"SELECT invoice_id, SUM(amount_cents) AS amt FROM dentist_commissions WHERE employee_id = ? AND status = 'valid' "
                          f"AND invoice_id IN ({marks}) GROUP BY invoice_id", [emp["id"], *by_inv]):
            share(m["invoice_id"], m["amt"] or 0)
    return out


def _commission_weights(conn, emp_id, lines: dict) -> dict:
    """What each (bill, type of case) would earn: per line, its fixed commission, or (amount − lab fee) × its rate
    (the line's own %, else the dentist's rate). X-ray and "no commission" lines earn nothing."""
    from ..billing import line_no_commission, no_commission_names
    from ..payroll import dentist_rates
    ids = [lid for x in lines.values() for lid in x["line_ids"]]
    if not ids:
        return {}
    r = dentist_rates(conn, emp_id, today().isoformat()) if emp_id else None
    base_bp = (r["commission_bp"] if r else 0) or 10000
    names = no_commission_names(conn)
    by_id = {l["id"]: l for l in conn.all(f"SELECT * FROM invoice_items WHERE id IN ({','.join('?' * len(ids))})", ids)}
    out = {}
    for k, x in lines.items():
        w = 0.0
        for lid in x["line_ids"]:
            l = by_id.get(lid)
            if not l or l["xray"] == 1 or line_no_commission(l, names):
                continue
            mode = l["commission_mode"] or "auto"
            if mode == "amount" and l["commission_cents"] is not None:
                w += l["commission_cents"]
            else:
                bp = l["commission_bp"] if mode == "percent" and l["commission_bp"] is not None else base_bp
                w += max(0, (l["amount_cents"] or 0) - (l["lab_fee_cents"] or 0)) * bp / 10000
        out[k] = w
    return out


def _commission_breakdown(conn, dentist_id: int, cat: str, groups: dict, inv_ids: list[int]) -> list[dict]:
    """Every commission entry behind a case's total: the bill, date, what it was for, the full entry and the part that
    counts for this type of case (a bill with work of several types shares its commission by what each earns)."""
    from ..payroll import per_procedure
    emp = conn.one("SELECT id FROM employees WHERE user_id = ?", (dentist_id,))
    if not emp or not inv_ids or per_procedure(conn):
        return []
    weights = _commission_weights(conn, emp["id"], groups)
    out = []
    for m in conn.all(f"SELECT c.*, i.number, p.amount_cents AS paid, p.method FROM dentist_commissions c JOIN invoices i ON i.id = c.invoice_id "
                      f"LEFT JOIN payments p ON p.id = c.payment_id WHERE c.employee_id = ? AND c.status = 'valid' "
                      f"AND c.invoice_id IN ({','.join('?' * len(inv_ids))}) ORDER BY c.earned_on, c.id", [emp["id"], *inv_ids]):
        parts = {k: w for k, w in weights.items() if k[0] == m["invoice_id"]}
        if not sum(parts.values()):
            parts = {k: x["billed"] for k, x in groups.items() if k[0] == m["invoice_id"]}
        tot = sum(parts.values())
        mine = parts.get((m["invoice_id"], cat), 0)
        counted = round(m["amount_cents"] * mine / tot) if tot else m["amount_cents"]
        out.append({"date": m["earned_on"], "bill": m["number"], "invoice_id": m["invoice_id"], "for": m["description"] or "",
                    "kind": "Payment" if m["payment_id"] else "Manual", "paid": m["paid"], "amount": m["amount_cents"], "counted": counted})
    return out


def build_cases(conn, dentist_id: int) -> list[dict]:
    """One case per (patient, type of case), only where both are true: the patient is assigned to the dentist (patient
    profile → assigned dentist) AND the dentist is on the bill for that type of case (bill line → dentist). Visits,
    amounts and appointments count only the dentist's own work."""
    assigned = {r["patient_id"] for r in conn.all("SELECT patient_id FROM patient_assignments WHERE dentist_id = ?", (dentist_id,))}

    def mine(pid, owner) -> bool:
        return pid in assigned and owner == dentist_id

    pats = set(assigned)
    if not pats:
        return []
    kind = Classifier(conn)
    marks = ",".join("?" * len(pats))
    P = list(pats)
    cases: dict[tuple, dict] = {}

    def case(pid, cat):
        return cases.setdefault((pid, cat), {"patient_id": pid, "category": cat, "visits": [], "billed": 0, "paid": 0, "next": None})

    for r in conn.all(f"SELECT p.patient_id, p.performed_by, p.description, s.name AS service, s.category AS scat, "
                      f"substr(COALESCE(p.performed_at, p.created_at), 1, 10) AS d "
                      f"FROM procedures p LEFT JOIN services s ON s.id = p.service_id WHERE p.status = 'completed' AND p.patient_id IN ({marks})", P):
        if mine(r["patient_id"], r["performed_by"]):
            case(r["patient_id"], kind(r["description"] or r["service"], r["scat"]))["visits"].append(r["d"])
    # saved progress notes (visits) with no coded procedure still count as a visit
    # (only notes with something in them: written notes or a recall; a note whose procedures were all deleted is not a visit)
    for r in conn.all(f"SELECT v.patient_id, v.dentist_id, v.visit_date AS d FROM visit_notes v WHERE v.status = 'saved' AND v.cancelled_at IS NULL "
                      f"AND v.patient_id IN ({marks}) AND (TRIM(COALESCE(v.body, '')) != '' OR v.recall_date IS NOT NULL) "
                      f"AND NOT EXISTS (SELECT 1 FROM procedures p WHERE p.visit_note_id = v.id AND p.status = 'completed')", P):
        if mine(r["patient_id"], r["dentist_id"]):
            case(r["patient_id"], GENERAL)["visits"].append(r["d"][:10])
    # bill lines that are theirs, by type of case; each bill's payments are shared over its lines in proportion
    lines: dict[tuple, dict] = {}
    for r in conn.all(f"SELECT i.patient_id, i.id AS inv, i.total_cents, ii.id AS line_id, ii.amount_cents, ii.description, ii.dentist_id, s.category AS scat, "
                      "ii.done_on AS d, ii.tooth, i.issued_at, "
                      "(SELECT COALESCE(SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END), 0) FROM payments "
                      " WHERE invoice_id = i.id AND status = 'valid') AS paid "
                      f"FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN services s ON s.id = ii.service_id "
                      f"WHERE i.status = 'issued' AND i.patient_id IN ({marks})", P):
        if not mine(r["patient_id"], r["dentist_id"]):
            continue
        k = (r["inv"], kind(r["description"], r["scat"]))
        x = lines.setdefault(k, {"patient_id": r["patient_id"], "billed": 0, "paid": r["paid"], "total": r["total_cents"], "line_ids": []})
        x["line_ids"].append(r["line_id"])
        c_ = case(r["patient_id"], k[1])
        c_["has_bill"] = True
        if r["d"]:
            c_["visits"].append(r["d"][:10])   # the day the billed work was done is a visit (imported records often have no procedure)
        x["billed"] += r["amount_cents"]
        what = (r["description"] or "").split(" · ")[0] + (f" #{r['tooth']}" if r["tooth"] else "")
        c_.setdefault("items", []).append({"d": (r["d"] or r["issued_at"] or "")[:10], "what": what, "amount": r["amount_cents"]})
    comm = _commissions(conn, dentist_id, lines)
    # installments (e.g. braces adjustments paid each visit): the days the dentist earned a commission on the bill are visits
    emp = conn.one("SELECT id FROM employees WHERE user_id = ?", (dentist_id,))
    inv_cats: dict[int, set] = {}
    for (inv, cat_) in lines:
        inv_cats.setdefault(inv, set()).add(cat_)
    if emp and inv_cats:
        ids_ = list(inv_cats)
        for m in conn.all(f"SELECT invoice_id, earned_on FROM dentist_commissions WHERE employee_id = ? AND status = 'valid' "
                          f"AND invoice_id IN ({','.join('?' * len(ids_))})", [emp["id"], *ids_]):
            for cat_ in inv_cats.get(m["invoice_id"], ()):
                case(lines[(m["invoice_id"], cat_)]["patient_id"], cat_)["visits"].append((m["earned_on"] or "")[:10])
    for (inv, cat_), x in lines.items():
        c = case(x["patient_id"], cat_)
        c["billed"] += x["billed"]
        c["paid"] += round(x["paid"] * x["billed"] / x["total"]) if x["total"] else 0
        c["commission"] = c.get("commission", 0) + comm.get((inv, cat_), 0)
    for r in conn.all(f"SELECT a.patient_id, a.dentist_id, s.name AS service, s.category AS scat, a.start_at FROM appointments a "
                      f"LEFT JOIN services s ON s.id = a.service_id "
                      f"WHERE a.patient_id IN ({marks}) AND a.status IN ('requested', 'confirmed') AND a.start_at >= ? ORDER BY a.start_at",
                      [*P, today().isoformat()]):
        if not mine(r["patient_id"], r["dentist_id"]):
            continue
        k = (r["patient_id"], kind(r["service"], r["scat"]) if r["service"] else GENERAL)
        if k in cases and not cases[k]["next"]:
            cases[k]["next"] = r["start_at"]
    info = {r["id"]: r for r in conn.all(f"SELECT p.id, p.first_name, p.last_name, p.chart_no, b.name AS branch FROM patients p "
                                         f"LEFT JOIN branches b ON b.id = p.preferred_branch_id WHERE p.id IN ({marks}) AND p.deleted_at IS NULL", P)}
    out = []
    t = today()
    for c in cases.values():
        p = info.get(c["patient_id"])
        if not p or not c.get("has_bill"):
            continue            # only cases billed to this dentist
        v = sorted(set(c["visits"]))          # a visit = a day the patient came, however many procedures were done
        c.update(patient=p, first=v[0] if v else None, last=v[-1] if v else None, n=len(v), balance=max(0, c["billed"] - c["paid"]))
        c["days_since"] = (t - date.fromisoformat(c["last"])).days if c["last"] else None
        if c["category"] == ORTHO and c["first"]:
            months = _months_between(date.fromisoformat(c["first"]), t)
            seen = {d[:7] for d in v}
            c["months"] = [(m, m in seen) for m in months]
            # this month doesn't count as missed yet
            c["missed"] = sum(1 for m, ok in c["months"][:-1] if not ok)
            ds = c["days_since"]
            c["adjust"] = "ok" if ds is not None and ds <= 35 else ("due" if ds is not None and ds <= 45 else "overdue")
        out.append(c)
    out.sort(key=lambda c: (c["category"] == GENERAL, c["category"], c["patient"]["last_name"], c["patient"]["first_name"]))
    return out


@bp.route("/")
@login_required
def index():
    conn = get_db()
    did, dentists = _dentist()
    allc = build_cases(conn, did) if did else []
    cats = sorted({c["category"] for c in allc})
    cat = request.args.get("type") or ""
    q = clean(request.args.get("q"), 60).lower()
    flt = request.args.get("filter") or ""
    d_from, d_to = parse_date(request.args.get("from")), parse_date(request.args.get("to"))
    if d_from and d_to and d_from > d_to:
        d_from, d_to = d_to, d_from
    lo, hi = (d_from.isoformat() if d_from else "0000"), (d_to.isoformat() if d_to else "9999")
    dated = bool(d_from or d_to)
    rows = [c for c in allc if (not cat or c["category"] == cat)
            and (not q or q in f"{c['patient']['first_name']} {c['patient']['last_name']} {c['patient']['chart_no']}".lower())
            and (flt != "balance" or c["balance"] > 0)
            and (flt != "overdue" or c.get("adjust") == "overdue")
            and (flt != "active" or (c["days_since"] is not None and c["days_since"] <= 90))
            and (not dated or any(lo <= v <= hi for v in c["visits"]))]
    for c in rows:   # the procedures and their prices: the ones in the chosen dates, else the latest
        its = sorted(c.get("items", []), key=lambda i: i["d"], reverse=True)
        if dated:
            its = [i for i in its if lo <= i["d"] <= hi] or its
        c["shown_items"], c["more_items"] = its[:6], max(0, len(its) - 6)
    counts = {k: sum(1 for c in allc if c["category"] == k) for k in cats}
    ortho = [c for c in rows if c["category"] == ORTHO]           # the boxes count what the filters show
    summary = {"cases": len(rows), "ortho": len(ortho), "ortho_overdue": sum(1 for c in ortho if c.get("adjust") == "overdue"),
               "balance": sum(c["balance"] for c in rows)}
    return render_template("staff/cases/index.html", rows=rows, cats=cats, cat=cat, q=q, flt=flt, counts=counts, summary=summary,
                           dentists=dentists, did=did, ORTHO=ORTHO,
                           d_from=d_from.isoformat() if d_from else "", d_to=d_to.isoformat() if d_to else "", shown=len(rows))


@bp.route("/<int:patient_id>")
@login_required
def detail(patient_id):
    conn = get_db()
    did, dentists = _dentist()
    cat = request.args.get("type") or ""
    allc = {(c["patient_id"], c["category"]): c for c in build_cases(conn, did)} if did else {}
    c = allc.get((patient_id, cat))
    if not c:
        abort(404)        # only your own cases
    kind = Classifier(conn)
    is_assigned = bool(conn.one("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (patient_id, did)))

    def mine(owner) -> bool:   # the dentist's own work on a patient assigned to them
        return is_assigned and owner == did

    visits = [v for v in conn.all("SELECT COALESCE(p.performed_at, p.created_at) AS at, p.performed_by AS owner, p.description, p.tooth, s.name AS service, s.category AS scat, "
                                  "u.name AS dentist, b.name AS branch FROM procedures p LEFT JOIN services s ON s.id = p.service_id "
                                  "LEFT JOIN users u ON u.id = p.performed_by LEFT JOIN branches b ON b.id = p.branch_id "
                                  "WHERE p.patient_id = ? AND p.status = 'completed' ORDER BY at DESC, p.id", (patient_id,))
              if mine(v["owner"]) and kind(v["description"] or v["service"], v["scat"]) == cat]
    if cat == GENERAL:
        visits = list(visits) + [x for x in conn.all(
            "SELECT v.visit_date AS at, v.dentist_id AS owner, 'Progress note' AS description, '' AS tooth, NULL AS service, u.name AS dentist, b.name AS branch "
            "FROM visit_notes v LEFT JOIN users u ON u.id = v.dentist_id LEFT JOIN branches b ON b.id = v.branch_id WHERE v.patient_id = ? "
            "AND v.status = 'saved' AND v.cancelled_at IS NULL AND (TRIM(COALESCE(v.body, '')) != '' OR v.recall_date IS NOT NULL) AND NOT EXISTS (SELECT 1 FROM procedures p WHERE p.visit_note_id = v.id "
            "AND p.status = 'completed')", (patient_id,)) if mine(x["owner"])]
        visits.sort(key=lambda r: r["at"] or "", reverse=True)
    # the dentist's billed lines of this type count as visits too (imported MyMeds records often have only the bill)
    proc_days = {(v["at"] or "")[:10] for v in visits}
    for r in conn.all("SELECT ii.done_on AS at, ii.dentist_id AS owner, "
                      "ii.description, ii.tooth, NULL AS service, s.category AS scat, u.name AS dentist, b.name AS branch FROM invoice_items ii "
                      "JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN services s ON s.id = ii.service_id LEFT JOIN users u ON u.id = ii.dentist_id "
                      "LEFT JOIN branches b ON b.id = i.branch_id WHERE i.patient_id = ? AND i.status = 'issued' AND ii.done_on IS NOT NULL", (patient_id,)):
        if mine(r["owner"]) and kind(r["description"], r["scat"]) == cat and (r["at"] or "")[:10] not in proc_days:
            visits = list(visits) + [r]
    visits = sorted(visits, key=lambda r: r["at"] or "", reverse=True)
    # one visit per day, with what was done that day
    days: dict[str, dict] = {}
    for v in visits:
        day = (v["at"] or "")[:10]
        g_ = days.setdefault(day, {"date": day, "items": [], "dentists": [], "branches": []})
        g_["items"].append({"name": v["service"] or v["description"], "tooth": v["tooth"],
                            "note": v["description"] if v["service"] and v["description"] and v["description"].strip().lower() != v["service"].strip().lower() else ""})
        for k, x in (("dentists", v["dentist"]), ("branches", v["branch"])):
            if x and x not in g_[k]:
                g_[k].append(x)
    visit_days = sorted(days.values(), key=lambda d: d["date"], reverse=True)
    amounts: dict[int, int] = {}
    groups: dict[tuple, dict] = {}            # (bill, type of case) → the dentist's lines, to split each bill's commission
    for r in conn.all("SELECT ii.id, ii.invoice_id, ii.amount_cents, ii.description, ii.dentist_id, s.category AS scat FROM invoice_items ii "
                      "JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN services s ON s.id = ii.service_id "
                      "WHERE i.patient_id = ? AND i.status = 'issued'", (patient_id,)):
        if not mine(r["dentist_id"]):
            continue
        k_ = kind(r["description"], r["scat"])
        gx = groups.setdefault((r["invoice_id"], k_), {"billed": 0, "line_ids": []})
        gx["billed"] += r["amount_cents"]
        gx["line_ids"].append(r["id"])
        if k_ == cat:
            amounts[r["invoice_id"]] = amounts.get(r["invoice_id"], 0) + r["amount_cents"]
    bills = [dict(b, case_amount=amounts[b["id"]]) for b in conn.all(
        "SELECT i.id, i.number, i.issued_at, i.total_cents, b.name AS branch, "
        "(SELECT COALESCE(SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END), 0) FROM payments "
        " WHERE invoice_id = i.id AND status = 'valid') AS paid "
        "FROM invoices i LEFT JOIN branches b ON b.id = i.branch_id WHERE i.patient_id = ? AND i.status = 'issued' ORDER BY i.issued_at DESC",
        (patient_id,)) if b["id"] in amounts]
    inv_ids = [x["id"] for x in bills]
    payments = conn.all(f"SELECT p.*, i.number FROM payments p JOIN invoices i ON i.id = p.invoice_id WHERE p.status = 'valid' "
                        f"AND p.invoice_id IN ({','.join('?' * len(inv_ids)) or 'NULL'}) ORDER BY p.received_at DESC", inv_ids)
    comm_rows = _commission_breakdown(conn, did, cat, groups, list(amounts))
    upcoming = [a for a in conn.all("SELECT a.start_at, a.status, a.dentist_id AS owner, s.name AS service, s.category AS scat, u.name AS dentist, b.name AS branch FROM appointments a "
                                    "LEFT JOIN services s ON s.id = a.service_id LEFT JOIN users u ON u.id = a.dentist_id LEFT JOIN branches b ON b.id = a.branch_id "
                                    "WHERE a.patient_id = ? AND a.status IN ('requested','confirmed') AND a.start_at >= ? ORDER BY a.start_at",
                                    (patient_id, today().isoformat()))
                if mine(a["owner"]) and (kind(a["service"], a["scat"]) if a["service"] else GENERAL) == cat]
    return render_template("staff/cases/detail.html", c=c, visits=visit_days, bills=bills, payments=payments, upcoming=upcoming, ORTHO=ORTHO,
                           comm_rows=comm_rows,
                           did=did if g.user.is_super_admin else None)

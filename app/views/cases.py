"""My cases (dentists): the patients assigned to a dentist, grouped by type of case (Orthodontics, Prosthodontics, ...).

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


def build_cases(conn, dentist_id: int) -> list[dict]:
    """One case per (patient, category) for patients assigned to the dentist or treated by them."""
    assigned = {r["patient_id"] for r in conn.all("SELECT patient_id FROM patient_assignments WHERE dentist_id = ?", (dentist_id,))}
    pats = set(assigned)
    pats |= {r["patient_id"] for r in conn.all("SELECT DISTINCT patient_id FROM procedures WHERE performed_by = ?", (dentist_id,))}
    pats |= {r["patient_id"] for r in conn.all("SELECT DISTINCT patient_id FROM visit_notes WHERE dentist_id = ? AND status = 'saved' "
                                               "AND cancelled_at IS NULL", (dentist_id,))}
    # patients whose bill lines name this dentist (e.g. from the MyMedsPH collection reports, which say who did the
    # procedure): only the types of case of those lines are theirs
    kind = Classifier(conn)
    by_bill: dict[int, set] = {}
    for r in conn.all("SELECT i.patient_id, ii.description, s.category AS scat FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id "
                      "LEFT JOIN services s ON s.id = ii.service_id WHERE ii.dentist_id = ? AND i.status = 'issued'", (dentist_id,)):
        by_bill.setdefault(r["patient_id"], set()).add(kind(r["description"], r["scat"]))
    only = {pid: cats for pid, cats in by_bill.items() if pid not in pats}
    pats |= set(by_bill)
    if not pats:
        return []
    marks = ",".join("?" * len(pats))
    P = list(pats)
    cases: dict[tuple, dict] = {}

    def case(pid, cat):
        return cases.setdefault((pid, cat), {"patient_id": pid, "category": cat, "visits": [], "billed": 0, "paid": 0, "next": None})

    for r in conn.all(f"SELECT p.patient_id, p.description, s.name AS service, s.category AS scat, substr(COALESCE(p.performed_at, p.created_at), 1, 10) AS d "
                      f"FROM procedures p LEFT JOIN services s ON s.id = p.service_id WHERE p.status = 'completed' AND p.patient_id IN ({marks})", P):
        case(r["patient_id"], kind(r["description"] or r["service"], r["scat"]))["visits"].append(r["d"])
    # saved progress notes (visits) with no coded procedure still count as a visit
    for r in conn.all(f"SELECT v.patient_id, v.visit_date AS d FROM visit_notes v WHERE v.status = 'saved' AND v.cancelled_at IS NULL "
                      f"AND v.patient_id IN ({marks}) AND NOT EXISTS (SELECT 1 FROM procedures p WHERE p.visit_note_id = v.id AND p.status = 'completed')", P):
        case(r["patient_id"], GENERAL)["visits"].append(r["d"][:10])
    # assigned patients with nothing recorded yet are still the dentist's cases
    for pid in assigned:
        if not any(k[0] == pid for k in cases):
            case(pid, GENERAL)
    # each bill's lines by type of case; its payments are shared over the lines in proportion
    lines: dict[tuple, dict] = {}
    for r in conn.all(f"SELECT i.patient_id, i.id AS inv, i.total_cents, ii.amount_cents, ii.description, s.category AS scat, "
                      "(SELECT COALESCE(SUM(CASE WHEN kind = 'payment' THEN amount_cents ELSE -amount_cents END), 0) FROM payments "
                      " WHERE invoice_id = i.id AND status = 'valid') AS paid "
                      f"FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN services s ON s.id = ii.service_id "
                      f"WHERE i.status = 'issued' AND i.patient_id IN ({marks})", P):
        k = (r["inv"], kind(r["description"], r["scat"]))
        x = lines.setdefault(k, {"patient_id": r["patient_id"], "billed": 0, "paid": r["paid"], "total": r["total_cents"]})
        x["billed"] += r["amount_cents"]
    for (inv, cat_), x in lines.items():
        c = case(x["patient_id"], cat_)
        c["billed"] += x["billed"]
        c["paid"] += round(x["paid"] * x["billed"] / x["total"]) if x["total"] else 0
    for r in conn.all(f"SELECT a.patient_id, s.name AS service, s.category AS scat, a.start_at FROM appointments a LEFT JOIN services s ON s.id = a.service_id "
                      f"WHERE a.patient_id IN ({marks}) AND a.status IN ('requested', 'confirmed') AND a.start_at >= ? ORDER BY a.start_at",
                      [*P, today().isoformat()]):
        k = (r["patient_id"], kind(r["service"], r["scat"]) if r["service"] else GENERAL)
        if k in cases and not cases[k]["next"]:
            cases[k]["next"] = r["start_at"]
    info = {r["id"]: r for r in conn.all(f"SELECT p.id, p.first_name, p.last_name, p.chart_no, b.name AS branch FROM patients p "
                                         f"LEFT JOIN branches b ON b.id = p.preferred_branch_id WHERE p.id IN ({marks}) AND p.deleted_at IS NULL", P)}
    out = []
    t = today()
    for c in cases.values():
        p = info.get(c["patient_id"])
        if not p or not (c["visits"] or c["billed"] or (c["patient_id"] in assigned and c["category"] == GENERAL)):
            continue
        if c["patient_id"] in only and c["category"] not in only[c["patient_id"]]:
            continue            # another dentist's procedure for this patient
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
    visits = [v for v in conn.all("SELECT COALESCE(p.performed_at, p.created_at) AS at, p.description, p.tooth, s.name AS service, s.category AS scat, "
                                  "u.name AS dentist, b.name AS branch FROM procedures p LEFT JOIN services s ON s.id = p.service_id "
                                  "LEFT JOIN users u ON u.id = p.performed_by LEFT JOIN branches b ON b.id = p.branch_id "
                                  "WHERE p.patient_id = ? AND p.status = 'completed' ORDER BY at DESC, p.id", (patient_id,))
              if kind(v["description"] or v["service"], v["scat"]) == cat]
    if cat == GENERAL:
        visits = list(visits) + conn.all(
            "SELECT v.visit_date AS at, 'Progress note' AS description, '' AS tooth, NULL AS service, u.name AS dentist, b.name AS branch "
            "FROM visit_notes v LEFT JOIN users u ON u.id = v.dentist_id LEFT JOIN branches b ON b.id = v.branch_id WHERE v.patient_id = ? "
            "AND v.status = 'saved' AND v.cancelled_at IS NULL AND NOT EXISTS (SELECT 1 FROM procedures p WHERE p.visit_note_id = v.id "
            "AND p.status = 'completed')", (patient_id,))
        visits.sort(key=lambda r: r["at"] or "", reverse=True)
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
    for r in conn.all("SELECT ii.invoice_id, ii.amount_cents, ii.description, s.category AS scat FROM invoice_items ii "
                      "JOIN invoices i ON i.id = ii.invoice_id LEFT JOIN services s ON s.id = ii.service_id "
                      "WHERE i.patient_id = ? AND i.status = 'issued'", (patient_id,)):
        if kind(r["description"], r["scat"]) == cat:
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
    upcoming = [a for a in conn.all("SELECT a.start_at, a.status, s.name AS service, s.category AS scat, u.name AS dentist, b.name AS branch FROM appointments a "
                                    "LEFT JOIN services s ON s.id = a.service_id LEFT JOIN users u ON u.id = a.dentist_id LEFT JOIN branches b ON b.id = a.branch_id "
                                    "WHERE a.patient_id = ? AND a.status IN ('requested','confirmed') AND a.start_at >= ? ORDER BY a.start_at",
                                    (patient_id, today().isoformat()))
                if (kind(a["service"], a["scat"]) if a["service"] else GENERAL) == cat]
    return render_template("staff/cases/detail.html", c=c, visits=visit_days, bills=bills, payments=payments, upcoming=upcoming, ORTHO=ORTHO,
                           did=did if g.user.is_super_admin else None)

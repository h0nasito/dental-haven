"""Dental chart: per-tooth findings and treatments (FDI numbering, adult and child)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..permissions import can_see_clinical
from ..util import clean, now_str, parse_date, to_int, today

bp = Blueprint("chart", __name__, url_prefix="/staff/patients")

ADULT = {"upper": [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28],
         "lower": [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]}
CHILD = {"upper": [55, 54, 53, 52, 51, 61, 62, 63, 64, 65], "lower": [85, 84, 83, 82, 81, 71, 72, 73, 74, 75]}
VALID_TEETH = {str(t) for rows in (ADULT, CHILD) for row in rows.values() for t in row}
SURFACES = {"M": "Mesial", "O": "Occlusal / incisal", "D": "Distal", "B": "Buccal / facial", "L": "Lingual / palatal"}
# code: (label, short tag, css class)
CONDITIONS = {
    "sound": ("Sound / healthy", "✓", "c-sound"),
    "caries": ("Caries (decay)", "C", "c-caries"),
    "restoration": ("Restoration / filling", "F", "c-filled"),
    "crown": ("Crown", "Cr", "c-crown"),
    "rct": ("Root canal treated", "RCT", "c-rct"),
    "extraction_needed": ("For extraction", "X?", "c-extract"),
    "missing": ("Missing / extracted", "M", "c-missing"),
    "implant": ("Implant", "Im", "c-implant"),
    "bridge": ("Bridge (abutment / pontic)", "Br", "c-crown"),
    "veneer": ("Veneer", "V", "c-filled"),
    "sealant": ("Sealant", "S", "c-filled"),
    "fractured": ("Fractured", "Fx", "c-caries"),
    "impacted": ("Impacted / unerupted", "Imp", "c-missing"),
    "denture": ("Replaced by denture", "D", "c-implant"),
    "mobility": ("Mobile tooth", "Mo", "c-extract"),
    "other": ("Other (see note)", "•", "c-other"),
}


def _check(patient_id):
    if not can_see_clinical(get_db(), g.user, patient_id):
        abort(403)


def chart_state(conn, patient_id):
    rows = conn.all("SELECT c.*, u.name AS by_name FROM chart_entries c LEFT JOIN users u ON u.id = c.recorded_by "
                    "WHERE c.patient_id = ? AND c.deleted = 0 ORDER BY c.recorded_on DESC, c.id DESC", (patient_id,))
    latest = {}
    for r in rows:
        latest.setdefault(r["tooth"], r)
    return rows, latest


@bp.route("/<int:patient_id>/chart", methods=["POST"])
@require("chart.edit")
def add_entry(patient_id):
    conn = get_db()
    _check(patient_id)
    teeth = [t.strip() for t in request.form.getlist("tooth") if t.strip() in VALID_TEETH]
    condition = request.form.get("condition")
    surfaces = "".join(s for s in SURFACES if request.form.get(f"surface_{s}"))
    d = parse_date(request.form.get("recorded_on")) or today()
    if not teeth or condition not in CONDITIONS or d > today():
        flash("Choose a tooth, a condition and a date that isn't in the future.", "error")
    else:
        with conn.transaction():
            for t in teeth:
                conn.insert("chart_entries", {"patient_id": patient_id, "tooth": t, "surfaces": surfaces, "condition": condition,
                                              "note": clean(request.form.get("note"), 500), "recorded_by": g.user.id,
                                              "recorded_on": d.isoformat(), "created_at": now_str()})
            audit.record("chart_updated", "patient", patient_id, f"Chart: {CONDITIONS[condition][0]} on tooth {', '.join(teeth)}")
        flash("Chart updated.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="chart", tooth=teeth[0] if teeth else None,
                            dentition=request.form.get("dentition", "adult")))


@bp.route("/<int:patient_id>/chart/delete", methods=["POST"])
@require("chart.delete")
def delete(patient_id):
    conn = get_db()
    _check(patient_id)
    entry_id = to_int(request.form.get("entry_id"))
    if request.form.get("scope") == "all":
        n = conn.scalar("SELECT COUNT(*) FROM chart_entries WHERE patient_id = ? AND deleted = 0", (patient_id,))
        conn.execute("UPDATE chart_entries SET deleted = 1 WHERE patient_id = ?", (patient_id,))
        audit.record("chart_deleted", "patient", patient_id, f"Deleted the whole dental chart ({n} entries)")
        flash("Dental chart cleared. The entries are kept in the audit trail.", "success")
    else:
        e = conn.one("SELECT * FROM chart_entries WHERE id = ? AND patient_id = ? AND deleted = 0", (entry_id, patient_id))
        if not e:
            abort(404)
        conn.execute("UPDATE chart_entries SET deleted = 1 WHERE id = ?", (entry_id,))
        audit.record("chart_entry_deleted", "patient", patient_id, f"Deleted chart entry on tooth {e['tooth']}", {"entry": dict(e)})
        flash("Chart entry deleted.", "success")
    return redirect(url_for("patients.detail", patient_id=patient_id, tab="chart"))

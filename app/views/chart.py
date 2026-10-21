"""Dental chart: per-tooth findings and treatments (FDI numbering, adult and child)."""
from __future__ import annotations

import math

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .. import audit
from ..auth import require
from ..db import get_db
from ..permissions import can_see_clinical
from ..uploads import document_path, save_document
from ..util import clean, now_str, parse_date, to_int, today

bp = Blueprint("chart", __name__, url_prefix="/staff/patients")

ADULT = {"upper": [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28],
         "lower": [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]}
CHILD = {"upper": [55, 54, 53, 52, 51, 61, 62, 63, 64, 65], "lower": [85, 84, 83, 82, 81, 71, 72, 73, 74, 75]}
VALID_TEETH = {str(t) for rows in (ADULT, CHILD) for row in rows.values() for t in row}
MAX_PHOTOS = 6
SURFACES = {"M": "Mesial", "O": "Occlusal / incisal", "D": "Distal", "B": "Buccal / facial", "L": "Lingual / palatal"}
# code: (label, short tag, css class)
CONDITIONS = {
    "sound": ("Sound / healthy", "✓", "c-sound"),
    "caries": ("Caries (decay)", "C", "c-caries"),
    "incipient_caries": ("Incipient caries (stage 1 decay)", "IC", "c-caries"),
    "restoration": ("Restoration / filling", "F", "c-filled"),
    "amalgam": ("Amalgam filling", "Am", "c-filled"),
    "temp_filling": ("Temporary filling", "TF", "c-filled"),
    "crown": ("Crown", "Cr", "c-crown"),
    "rct": ("Root canal treated", "RCT", "c-rct"),
    "extraction_needed": ("For extraction", "XO", "c-extract"),
    "missing": ("Missing / extracted", "M", "c-missing"),
    "implant": ("Implant", "Im", "c-implant"),
    "bridge": ("Bridge (abutment / pontic)", "Br", "c-crown"),
    "veneer": ("Veneer", "V", "c-filled"),
    "sealant": ("Sealant", "S", "c-filled"),
    "fractured": ("Fractured", "Fx", "c-caries"),
    "abrasion": ("Abrasion", "Ab", "c-other"),
    "attrition": ("Attrition", "Att", "c-other"),
    "impacted": ("Impacted", "Imp", "c-missing"),
    "unerupted": ("Unerupted", "Un", "c-missing"),
    "denture": ("Replaced by denture", "D", "c-implant"),
    "mobility": ("Mobile tooth", "Mo", "c-extract"),
    "other": ("Other (see note)", "•", "c-other"),
}


# Surface colours on the round tooth diagram (fill class per condition). Conditions that mean "the tooth is there and fine"
# reset earlier surface marks; whole-tooth conditions without surfaces colour the whole tooth or draw a mark over it.
FILL = {"sound": "", "caries": "f-caries", "incipient_caries": "f-incipient", "restoration": "f-filled", "amalgam": "f-amalgam",
        "temp_filling": "f-temp", "abrasion": "f-wear", "attrition": "f-wear", "crown": "f-crown", "rct": "f-rct", "extraction_needed": "f-extract",
        "missing": "", "implant": "f-implant", "bridge": "f-crown", "veneer": "f-filled", "sealant": "f-sealant", "fractured": "f-fracture",
        "impacted": "", "unerupted": "", "denture": "f-implant", "mobility": "", "other": "f-other"}
MARK = {"missing": "x", "extraction_needed": "x-red", "impacted": "ring-solid", "unerupted": "ring", "mobility": "ring-red"}
RESET = {"sound", "missing", "implant", "denture", "crown"}
UPPER_Q, RIGHT_Q = {"1", "2", "5", "6"}, {"1", "4", "5", "8"}


def regions(tooth) -> dict:
    """Which surface is drawn where on the round diagram (seen from the front, patient's right on your left):
    top/bottom = buccal or lingual by jaw, left/right = mesial or distal by side, centre = occlusal/incisal."""
    q = str(tooth)[0]
    top, bottom = ("B", "L") if q in UPPER_Q else ("L", "B")
    left, right = ("D", "M") if q in RIGHT_Q else ("M", "D")
    return {"top": top, "bottom": bottom, "left": left, "right": right, "center": "O"}


def _seg(a0, a1, r_out=20.0, r_in=8.5, c=22.0) -> str:
    p = lambda r, a: f"{c + r * math.cos(math.radians(a)):.2f} {c + r * math.sin(math.radians(a)):.2f}"  # noqa: E731
    return f"M{p(r_out, a0)} A{r_out} {r_out} 0 0 1 {p(r_out, a1)} L{p(r_in, a1)} A{r_in} {r_in} 0 0 0 {p(r_in, a0)} Z"


# the four outer parts of the tooth circle, split on the diagonals (SVG angles: 0 = right, 90 = down)
SEG_PATHS = {"top": _seg(225, 315), "right": _seg(315, 405), "bottom": _seg(45, 135), "left": _seg(135, 225)}


def tooth_views(entries) -> dict:
    """Per tooth: the colour of each surface, a whole-tooth colour or mark, and the short code shown under it.
    Entries are applied oldest first, so a later filling on a decayed surface turns it from red to blue."""
    out: dict[str, dict] = {}
    for e in sorted(entries, key=lambda e: (e["recorded_on"], e["id"])):
        v = out.setdefault(e["tooth"], {"surf": {}, "whole": "", "mark": "", "tag": "", "label": ""})
        cond, surf = e["condition"], e["surfaces"] or ""
        v["tag"], v["label"] = CONDITIONS[cond][1], CONDITIONS[cond][0] + (f" ({surf})" if surf else "")
        if surf:
            for k in surf:
                v["surf"][k] = FILL.get(cond, "")
            continue
        if cond in RESET:
            v["surf"], v["mark"] = {}, ""
        v["whole"] = FILL.get(cond, "") if cond not in ("sound",) else ""
        v["mark"] = MARK.get(cond, "" if cond in RESET else v["mark"])
    return out


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
    photos = [f for f in request.files.getlist("photos") if f and f.filename][:MAX_PHOTOS]
    if not teeth or condition not in CONDITIONS or d > today():
        flash("Choose a tooth, a condition and a date that isn't in the future.", "error")
    else:
        saved = []
        for f in photos:
            stored, mime, size, original, err = save_document(f)
            if err:
                for x in saved:
                    document_path(x[0]).unlink(missing_ok=True)
                flash(f"{f.filename}: {err} Nothing was saved.", "error")
                return redirect(url_for("patients.detail", patient_id=patient_id, tab="chart", tooth=teeth[0]) + "#rec")
            saved.append((stored, mime, size, original))
        with conn.transaction():
            first = None
            for t in teeth:
                eid = conn.insert("chart_entries", {"patient_id": patient_id, "tooth": t, "surfaces": surfaces, "condition": condition,
                                                    "note": clean(request.form.get("note"), 500), "recorded_by": g.user.id,
                                                    "recorded_on": d.isoformat(), "created_at": now_str()})
                first = first or eid
            title = f"Tooth {', '.join(teeth)} · {CONDITIONS[condition][0]}" + (f" ({surfaces})" if surfaces else "")
            for stored, mime, size, original in saved:
                conn.insert("patient_documents", {"patient_id": patient_id, "category": "clinical_photo", "clinical": 1, "title": title[:120],
                                                  "original_name": original, "stored_name": stored, "mime": mime, "size_bytes": size,
                                                  "uploaded_by": g.user.id, "uploaded_at": now_str(), "chart_entry_id": first})
            audit.record("chart_updated", "patient", patient_id, f"Chart: {CONDITIONS[condition][0]} on tooth {', '.join(teeth)}"
                         + (f", {len(saved)} photo{'s' if len(saved) > 1 else ''}" if saved else ""))
        flash("Chart updated." + (f" {len(saved)} photo{'s' if len(saved) > 1 else ''} added (also in Uploads)." if saved else ""), "success")
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

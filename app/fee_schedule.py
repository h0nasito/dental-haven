"""Fee schedule helpers: sort a service into a category by its name (used when the admin adds or imports prices)."""
from __future__ import annotations

import re

from .fee_schedule_data import CATEGORIES

RULES = [  # (regex on NAME, category) — first match wins
    (r"CROWN LENGTHENING", "Extraction & Oral Surgery"),
    (r"^ASEPSIS", "Braces, Aligners & Orthodontics"),
    (r"^PEDIATRIC|^PULPO[- ]|DISKING", "Pediatric (Kids)"),
    (r"BANK PERCENTAGE|RUSH FEE|HMO|^ASEPSIS", "Fees & Charges"),
    (r"CONSULTATION|CHECK UP|FOLLOW UP", "Consultation & Check-up"),
    (r"X-?RAY|XRAY|CBCT|RADIOGRAPH|PHOTO|IMPRESSION|MODEL CAST|ORTHO CAST|INDIVIDUAL TRAY|BITE \(REGISTRATION\)|MOCK UP|CLINCHECK", "X-ray, Scans, Impressions & Records"),
    (r"IMPLANT|BOME GRAFT|BONE GRAFT", "Implants & Bone Graft"),
    (r"DENTURE", "Dentures"),
    (r"OCCLUSAL SPLINT|NIGHT GUARD|MOUTHGUARD|DEPROGRAMMER|DEMOGRAPHER|INSTALL - SPLINT", "TMJ, Splints & Guards"),
    (r"RETAINER|EXPANDER|BITE PLANE|ORTHO SPLINT", "Retainers & Ortho Appliances"),
    (r"BRACES|BRACKET|BUCCAL|ORTHODONTIC|ALIGNER|TADS|ELASTICS|LINGUAL|LIGUAL|INSTALL LOWER", "Braces, Aligners & Orthodontics"),
    (r"WHITENING|BLEACHING", "Whitening & Cosmetic"),
    (r"INLAY|ONLAY|OVERLAY", "Inlays, Onlays & Overlays"),
    (r"CROWN|BRIDGE|VENEER|PONTIC", "Crowns, Bridges & Veneers"),
    (r"RCT|ROOT CANAL|PULPOTOMY|OBTURATION|APICOECTOMY|POST AND CORE", "Root Canal (Endodontics)"),
    (r"EXTRACTION|ODONTECTOMY|FRENECTOMY|GINGIVECTOMY|SUTURE|ANESTHESIA|SEDATION", "Extraction & Oral Surgery"),
    (r"RESTORATION|BASE/GI|CAVITY LINER|BUILD UP|RESIN INFILTRATION", "Fillings & Restorations"),
    (r"PROPHYLAXIS|FLUORIDE|NICOTINE|SCALLING|SCALING|GUM CARE|SILVER DIAMINE", "Cleaning & Prevention"),
]


def classify(name: str) -> str:
    n = (name or "").upper()
    for rx, cat in RULES:
        if re.search(rx, n):
            return cat
    return "Other"


def is_per_count(unit: str) -> bool:
    """Whether the quantity should follow the number of teeth entered (per tooth / unit / surface / canal / bracket)."""
    u = (unit or "").lower()
    if any(w in u for w in ("arch", "case", "cycle", "quadrant", "minimum", "complete", "missing", "upper", "lower")):
        return False
    return any(w in u for w in ("tooth", "unit", "surface", "canal", "crown", "bracket", "pontic", "buccal", "suture", "tads"))


def picker_options(conn):
    """Fee schedule items for the pickers. Names that appear more than once get their unit added so each is unique."""
    from .views.fees import active_fees
    rows = active_fees(conn)
    names = {}
    for r in rows:
        names[r["name"].upper()] = names.get(r["name"].upper(), 0) + 1
    out = []
    for r in rows:
        label = r["name"] + (f" ({r['unit']})" if names[r["name"].upper()] > 1 and r["unit"] else "")
        out.append({"name": label, "price": r["price_cents"], "unit": r["unit"], "category": r["category"],
                    "per_count": is_per_count(r["unit"]), "service_id": None})
    return out

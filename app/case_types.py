"""The type of case a procedure, bill line or appointment belongs to (for My cases).

The groups are the clinic's fee schedule categories (Braces, Aligners & Orthodontics; Fillings & Restorations; …), so
procedures imported from MyMedsPH, which carry the same names as the fee schedule, are sorted correctly. In order:
1. the name matches a fee schedule item exactly (first line of the text, case and spacing ignored);
2. keywords in the name (e.g. "braces", "pasta", "bunot", "RCT");
3. the website service it is linked to (Orthodontics & TMJ → braces …);
4. otherwise General / other. Check-ups, X-rays, impressions and fees are General / other too: they belong to every case.
"""
from __future__ import annotations

import re

GENERAL = "General / other"
ORTHO = "Braces, Aligners & Orthodontics"
GENERAL_GROUPS = {"Consultation & Check-up", "X-ray, Scans, Impressions & Records", "Fees & Charges", ""}

# keyword rules, checked in this order (the first that matches wins)
RULES = [
    ("Pediatric (Kids)", r"PEDIATRIC|PEDIA\b|PULPO[- ]|STAINLESS STEEL CROWN|SPACE MAINTAI"),
    ("Dentures", r"DENTURE|PUSTISO|\bRPD\b"),
    ("Retainers & Ortho Appliances", r"RETAINER|HAWLEY|EXPANDER|BITE PLANE|CATLAN"),
    (ORTHO, r"BRACES|BRACKET|ORTHODONT|ALIGNER|\bORTHO\b|ARCH ?WIRE|POWER ?CHAIN|ELASTIC|ADJUSTMENT"),
    ("Root Canal (Endodontics)", r"\bRCT\b|ROOT CANAL|PULPECTOMY|PULPOTOMY|APICOECTOMY|OBTURATION|POST AND CORE|ENDODONT"),
    ("Extraction & Oral Surgery", r"EXTRACT|BUNOT|ODONTECTOMY|SURGERY|SURGICAL|GINGIVECTOMY|FRENECTOMY|SUTURE|IMPACT|ALVEOLECTOMY"),
    ("Inlays, Onlays & Overlays", r"\bINLAY|\bONLAY|OVERLAY"),
    ("Implants & Bone Graft", r"IMPLANT|BONE GRAFT|BOME GRAFT"),
    ("Crowns, Bridges & Veneers", r"CROWN|BRIDGE|VENEER|PONTIC|JACKET|PROSTHODONT"),
    ("Whitening & Cosmetic", r"WHITENING|BLEACH|COSMETIC"),
    ("Fillings & Restorations", r"RESTORATI|PASTA|FILLING|COMPOSITE|BUILD ?UP|\bGI\b|LINER|DIASTEMA"),
    ("Cleaning & Prevention", r"PROPHYLAXIS|CLEANING|LINIS|SCAL+ING|FLUORIDE|SEALANT|GUM CARE|PERIODONT|PREVENTIVE|NICOTINE STAIN|SDF|SILVER DIAMINE"),
    ("TMJ, Splints & Guards", r"NIGHT ?GUARD|MOUTH ?GUARD|SPLINT|\bTMJ\b|DEPROGRAMMER"),
]
RULES = [(name, re.compile(rx)) for name, rx in RULES]

# the website's service categories, when that is all we know
SERVICE_CATEGORY = {
    "Orthodontics & TMJ": ORTHO,
    "Restorative": "Fillings & Restorations",
    "Preventive & Diagnostic": "Cleaning & Prevention",
    "Periodontal (Gum) Care": "Cleaning & Prevention",
    "Prosthodontics & Tooth Replacement": "Crowns, Bridges & Veneers",
    "Oral Surgery": "Extraction & Oral Surgery",
    "Cosmetic Dentistry": "Whitening & Cosmetic",
    "Pediatrics & Special Care": "Pediatric (Kids)",
}


def norm(text: str | None) -> str:
    """First line, without a "(#16)" tooth note or "Case #… ·" prefix, upper case, single spaces."""
    t = (text or "").split("\n", 1)[0]
    t = t.split(" · ", 1)[0]
    t = re.sub(r"\s*\(#[^)]*\)\s*$", "", t)
    return re.sub(r"\s+", " ", t).strip().upper()


class Classifier:
    """Load the fee schedule once, then classify many texts (results cached)."""

    def __init__(self, conn):
        self.names = {}
        for r in conn.all("SELECT name, category FROM fee_schedule"):
            k = norm(r["name"])
            if k and k not in self.names:
                self.names[k] = r["category"] or ""
        self.cache: dict[tuple, str] = {}

    def __call__(self, text: str | None, service_category: str | None = None) -> str:
        key = (text or "", service_category or "")
        if key in self.cache:
            return self.cache[key]
        n = norm(text)
        out = None
        if n in self.names:
            cat = self.names[n]
            out = GENERAL if cat in GENERAL_GROUPS else cat
        if out is None and n:
            out = next((name for name, rx in RULES if rx.search(n)), None)
        if out is None and service_category:
            out = SERVICE_CATEGORY.get(service_category)
        out = out or GENERAL
        self.cache[key] = out
        return out

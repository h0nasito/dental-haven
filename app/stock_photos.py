"""Placeholder photos for the public website, from Unsplash (free to use, including commercially,
under the Unsplash License: https://unsplash.com/license). They load straight from images.unsplash.com.

Every one is replaced automatically as soon as the clinic uploads its own photo for that spot
(Administration → Website content). Stock photos are never presented as Dental Haven patient results:
the portfolio shows them as "Sample photos" until real cases are added.
Set STOCK_PHOTOS=off on the server to hide them all (the drawn template images are used instead).
"""
from __future__ import annotations

import os

_BASE = "https://images.unsplash.com/photo-{id}?auto=format&fit=crop&w={w}&q=75"

PHOTOS = {
    # site_images keys
    "hero": "1489278353717-f64c6ee8a4d2",          # woman smiling, close-up
    "lab": "1771442873035-474765b40ac6",           # gloved hand holding a dental implant and crown
    "tech_xray": "1777445374290-eedda5be8e5b",     # panoramic dental x-ray
    "tech_scanner": "1667133295315-820bb6481730",  # dentist examining patient with dental scanner
    "tech_milling": "1776406987595-ba14f3510c07",  # technician crafting a dental prosthesis
    "specialty": "1654373535457-383a0a4d00f9",     # close-up of a bright white smile
    # services (by slug)
    "service:aesthetic-dentistry": "1677026010083-78ec7f1b84ed",
    "service:prosthodontics": "1776406987595-ba14f3510c07",
    "service:dental-implants": "1593022356769-11f762e25ed9",
    "service:general-dentistry": "1606811971618-4486d14f3f99",
    "service:orthodontics": "1720685193964-4529228a33c1",
    "service:pediatric-dentistry": "1758205307836-0829c799890b",
    # branches (by slug)
    "branch:malolos": "1629909613654-28e377c37b09",
    "branch:guiguinto": "1598256989800-fe5f95da9787",
    "branch:bocaue": "1704455306251-b4634215d98f",
    "branch:sjdm": "1642845257969-09077e914081",
}

# Portfolio samples shown only until the clinic adds its own cases.
SAMPLES = [
    ("cosmetic", "Smile makeover", "1677026010083-78ec7f1b84ed"),
    ("cosmetic", "Veneers", "1654373535457-383a0a4d00f9"),
    ("implants", "Dental implants", "1593022356769-11f762e25ed9"),
    ("orthodontics", "Braces", "1720685193964-4529228a33c1"),
    ("orthodontics", "Clear aligners", "1609840114035-3c981b782dfe"),
    ("prosthodontics", "Crowns & bridges", "1771442873035-474765b40ac6"),
]


def enabled() -> bool:
    return os.environ.get("STOCK_PHOTOS", "on").lower() != "off"


def url(key: str, w: int = 1200) -> str | None:
    pid = PHOTOS.get(key)
    return _BASE.format(id=pid, w=w) if pid and enabled() else None


def samples(w: int = 900) -> list[dict]:
    if not enabled():
        return []
    return [{"category": c, "title": t, "url": _BASE.format(id=pid, w=w), "full": _BASE.format(id=pid, w=1600)} for c, t, pid in SAMPLES]

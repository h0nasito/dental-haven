"""Editable website texts, grouped by the section of the page they appear in.

Each field has a key, a label for the editor, the default text (what the site showed before anyone edited it), and a kind:
- "line": one line (headings, labels, buttons)
- "text": a few sentences
- "show": a show/hide switch for the section ("1" shown, "0" hidden)

Keys starting with "@" are stored in the older site_content table ("@home_hero.title" = the title of "home_hero"), so the
Website content page and this editor change the same text.

In headings, *words between asterisks* are shown in the gold italic accent.
"""
from __future__ import annotations

import re

from markupsafe import Markup, escape

LAB_NAME = "Digital Solutions Dental Laboratory"

SECTIONS = [
    {"id": "hero", "label": "Top of the page", "anchor": "top", "photos": ["hero"],
     "note": "The headline area with the big background photo.",
     "fields": [
         ("hero.kicker", "Small label above the headline", "Aesthetic & general dentistry", "line"),
         ("@home_hero.title", "Headline", "Happiest your teeth will ever be", "line"),
         ("@home_hero.body", "Intro text", "", "text"),
         ("hero.btn_book", "Main button", "Book your visit", "line"),
         ("hero.btn_second", "Second button", "See before & after", "line"),
         ("hero.fact1_big", "Fact 1: big text", "4", "line"),
         ("hero.fact1_small", "Fact 1: small text", "branches to serve you", "line"),
         ("hero.fact2_big", "Fact 2: big text (empty = number of services)", "", "line"),
         ("hero.fact2_small", "Fact 2: small text", "areas of care, one clinic", "line"),
         ("hero.fact3_big", "Fact 3: big text", "Gentle", "line"),
         ("hero.fact3_small", "Fact 3: small text", "care for kids & special needs", "line"),
         ("hero.fact4_big", "Fact 4: big text", "3D", "line"),
         ("hero.fact4_small", "Fact 4: small text", "CBCT & panoramic X-rays in-house", "line"),
     ]},
    {"id": "services", "label": "Main services", "anchor": "services", "photos": [],
     "note": "Service names, descriptions and photos are edited in Administration → Services.",
     "fields": [
         ("services.eyebrow", "Small label", "Main services", "line"),
         ("services.title", "Heading", "Everything your smile needs, *under one roof*", "line"),
         ("services.intro", "Intro text", "From a routine cleaning to a complete smile makeover, every treatment is planned around you and your goals.", "text"),
         ("services.card_btn", "Button on each service", "Book now", "line"),
         ("services.cta_btn", "Button below the services", "Book a consultation", "line"),
         ("services.cta_note", "Note next to the button", "Not sure where to start? We'll check your teeth and explain your options and costs before any treatment.", "text"),
     ]},
    {"id": "specialty", "label": "Smile transformations", "anchor": "specialty", "photos": ["specialty"],
     "note": "Shows the featured before & after case. Until there is one, it shows the photo below.",
     "fields": [
         ("specialty.show", "Show this section", "1", "show"),
         ("specialty.eyebrow", "Small label", "Smile transformations", "line"),
         ("specialty.title", "Heading", "Care for *every smile*", "line"),
         ("specialty.text", "Text", "From your child's first check-up to fillings, braces, crowns, dentures and implants, our dentists care for every smile in the family. Restorations are crafted in our own digital lab for a precise, natural-looking fit.", "text"),
         ("specialty.btn_book", "Main button", "Book a consultation", "line"),
         ("specialty.btn_work", "Second button", "See all our work", "line"),
     ]},
    {"id": "work", "label": "Our work (gallery)", "anchor": "work", "photos": [],
     "note": "The photos come from the Gallery (Website content → Gallery).",
     "fields": [
         ("work.show", "Show this section", "1", "show"),
         ("work.eyebrow", "Small label", "Our work", "line"),
         ("work.title", "Heading (when there are gallery photos)", "Real smiles. *Real results.*", "line"),
         ("work.intro", "Intro (when there are gallery photos)", "Every smile here was crafted by our dentists for a Dental Haven patient: makeovers, restorations, implants and more.", "text"),
         ("work.title_empty", "Heading (before gallery photos are added)", "The smiles *we create*", "line"),
         ("work.intro_empty", "Intro (before gallery photos are added)", "Makeovers, veneers, implants, braces and restorations, planned by our dentists and crafted in our own lab.", "text"),
         ("work.all_label", "Filter button for everything", "All work", "line"),
         ("work.link", "Link to the full gallery", "View the full gallery →", "line"),
     ]},
    {"id": "guides", "label": "Patient guides", "anchor": "guides", "photos": [],
     "note": "Shown only when at least one guide is published. Guides are edited in Website content → Patient guides.",
     "fields": [
         ("guides.show", "Show this section", "1", "show"),
         ("guides.eyebrow", "Small label", "Patient guides", "line"),
         ("guides.title", "Heading", "Know before *you go*", "line"),
         ("guides.intro", "Intro text", "Short, easy-to-read guides to help you understand your treatment and feel at ease before your visit.", "text"),
         ("guides.link", "Link to all guides", "See all patient guides →", "line"),
     ]},
    {"id": "why", "label": "Why Dental Haven (4 highlights)", "anchor": "clinic", "photos": [],
     "fields": [
         ("why.show", "Show this section", "1", "show"),
         ("why.1_title", "Highlight 1: title", "Everything in one place", "line"),
         ("why.1_text", "Highlight 1: text", "From cleanings to full-mouth rehabilitation", "line"),
         ("why.2_title", "Highlight 2: title", "Gentle with kids & special needs", "line"),
         ("why.2_text", "Highlight 2: text", "Including conscious sedation", "line"),
         ("why.3_title", "Highlight 3: title", "See clearly, treat precisely", "line"),
         ("why.3_text", "Highlight 3: text", "In-house 3D CBCT & panoramic X-rays", "line"),
         ("why.4_title", "Highlight 4: title", "Your new smile, sooner", "line"),
         ("why.4_text", "Highlight 4: text", "Made in our own digital lab", "line"),
     ]},
    {"id": "about", "label": "About us", "anchor": "about", "photos": ["about"],
     "note": "Dentists, staff and activities are added in Administration → About us. The section stays hidden until there is something to show.",
     "fields": [
         ("about.show", "Show this section", "1", "show"),
         ("about.eyebrow", "Small label", "About us", "line"),
         ("about.title", "Heading", "The people behind *your smile*", "line"),
         ("about.story", "Our story (a few paragraphs; leave a blank line between paragraphs)", "", "text"),
         ("about.mission_title", "Mission: heading", "Our mission", "line"),
         ("about.mission", "Mission (empty = hidden)", "", "text"),
         ("about.vision_title", "Vision: heading", "Our vision", "line"),
         ("about.vision", "Vision (empty = hidden)", "", "text"),
         ("about.values_title", "Values: heading", "What we value", "line"),
         ("about.values", "Values, one per line (empty = hidden)", "", "text"),
         ("about.dentists_title", "Dentists: heading", "Meet our dentists", "line"),
         ("about.staff_title", "Clinic staff: heading", "Our clinic team", "line"),
         ("about.lab_title", "Lab team: heading", "Our laboratory team", "line"),
         ("about.activities_title", "Activities: heading", "Activities & community", "line"),
         ("about.link", "Link to the full About us page", "More about us", "line"),
     ]},
    {"id": "reviews", "label": "Patient reviews", "anchor": "reviews", "photos": [],
     "note": "Quotes come from Website content → Patient feedback (only real, consented reviews). The Google rating comes from Administration → Branches & chairs → each branch → Google reviews.",
     "fields": [
         ("reviews.show", "Show this section", "1", "show"),
         ("reviews.eyebrow", "Small label", "Patient reviews", "line"),
         ("reviews.title", "Heading", "Hear it from our patients", "line"),
         ("reviews.intro_empty", "Text when there are no reviews yet", "Read what patients say about each branch on our Facebook pages.", "text"),
         ("reviews.google_label", "Google rating: label", "Rated on Google", "line"),
         ("reviews.google_btn", "Google rating: button on each branch", "Read reviews", "line"),
         ("reviews.google_write", "Google rating: invitation under the branches", "Visited us? We'd love to hear from you on Google.", "line"),
         ("reviews.fb_label", "Label before the Facebook buttons", "Facebook reviews", "line"),
         ("reviews.fb_label_more", "Same label when reviews are shown", "More reviews on Facebook", "line"),
     ]},
    {"id": "branches", "label": "Branches", "anchor": "branches", "photos": [],
     "note": "Branch names, addresses, phones, hours and photos are edited in Administration → Branches & chairs.",
     "fields": [
         ("branches.eyebrow", "Small label", "Visit us", "line"),
         ("branches.title", "Heading", "Four branches to serve you", "line"),
         ("branches.intro", "Intro text", "Visit the branch that's most convenient for you. Book online in minutes or give us a call.", "text"),
         ("branches.btn", "Button (the branch name is added after it)", "Book at", "line"),
     ]},
    {"id": "lab", "label": "Digital lab", "anchor": "lab", "photos": ["lab", "tech_xray", "tech_scanner", "tech_milling"],
     "fields": [
         ("lab.show", "Show this section", "1", "show"),
         ("@lab.title", "Laboratory name", LAB_NAME, "line"),
         ("lab.eyebrow", "Small label", "Behind every smile", "line"),
         ("lab.title", "Heading", "Your new smile, made in our own lab", "line"),
         ("lab.lead", "Text", "Experience fast turnaround times for custom dental restorations, including crowns, bridges, dentures and aligners, crafted efficiently in-house at " + LAB_NAME + " using advanced CAD/CAM technology.", "text"),
         ("lab.cap_xray", "Caption: X-ray photo", "X-rays: panoramic, cephalometric & CBCT", "line"),
         ("lab.cap_scanner", "Caption: scanner photo", "Intraoral scanning", "line"),
         ("lab.cap_milling", "Caption: milling photo", "Milling & 3D printing", "line"),
         ("lab.tech1", "Technology 1", "Intraoral scanners", "line"),
         ("lab.tech2", "Technology 2", "exocad design", "line"),
         ("lab.tech3", "Technology 3", "3D printers", "line"),
         ("lab.tech4", "Technology 4", "CAD/CAM milling", "line"),
         ("lab.tech5", "Technology 5", "Panoramic, cephalometric & CBCT X-rays", "line"),
     ]},
    {"id": "careers", "label": "Careers", "anchor": "careers", "photos": [],
     "note": "Shown only when the careers email is filled in.",
     "fields": [
         ("careers.show", "Show this section", "1", "show"),
         ("@careers_email.body", "Email for applications", "", "line"),
         ("@careers.title", "Heading", "Grow your career with us", "line"),
         ("@careers.body", "Text (first paragraph = intro; second = application note; lines starting with \"- \" = reasons to work here, \"Title: text\")", "", "text"),
         ("careers.card_title", "Application box: title", "Send your application", "line"),
         ("careers.card_text", "Application box: text (if the text above has no second paragraph)", "Email your CV, the position you're applying for, and your preferred branch.", "text"),
         ("careers.btn", "Button", "Email your CV", "line"),
         ("careers.perks_title", "Heading above the reasons", "Why work at Dental Haven", "line"),
     ]},
    {"id": "final", "label": "Bottom of the page (contact)", "anchor": "contact", "photos": [],
     "fields": [
         ("final.title", "Heading", "Your happiest smile *starts here*", "line"),
         ("final.text", "Text", "Pick a branch and a time that suits you. Our team will call or message you to confirm your visit.", "text"),
         ("final.btn_book", "Main button", "Book your visit", "line"),
         ("final.btn_ask", "Second button", "Ask us anything", "line"),
     ]},
    {"id": "header", "label": "Menu at the top (every page)", "anchor": "top", "photos": [],
     "fields": [
         ("nav.specialty", "Menu: smile transformations", "Smile transformations", "line"),
         ("nav.work", "Menu: our work", "Our work", "line"),
         ("nav.services", "Menu: services", "Services", "line"),
         ("nav.about", "Menu: about us", "About us", "line"),
         ("nav.guides", "Menu: guides", "Guides", "line"),
         ("nav.branches", "Menu: branches", "Branches", "line"),
         ("nav.contact", "Menu: contact", "Contact", "line"),
         ("nav.book", "Menu button", "Book now", "line"),
     ]},
    {"id": "footer", "label": "Footer (every page)", "anchor": "", "photos": [],
     "fields": [
         ("footer.tagline", "Tagline", "Happiest your teeth will ever be.", "line"),
         ("footer.about", "About text", "Preventive & diagnostic, restorative, prosthodontics & tooth replacement, orthodontics & TMJ, oral surgery, cosmetic, gum care, and pediatric & special care dentistry, with our in-house Digital Solutions Dental Laboratory.", "text"),
         ("footer.fine", "Small print", "© Dental Haven. Website content is being finalised with the clinic.", "line"),
     ]},
]

FIELDS = {k: (label, default, kind) for s in SECTIONS for (k, label, default, kind) in s["fields"]}
SECTION_BY_ID = {s["id"]: s for s in SECTIONS}


def load(conn) -> dict:
    """All saved texts (site_text plus the site_content texts the sections use)."""
    saved = {r["key"]: r["value"] for r in conn.all("SELECT key, value FROM site_text")}
    for r in conn.all("SELECT key, title, body FROM site_content"):
        saved[f"@{r['key']}.title"] = r["title"] or ""
        saved[f"@{r['key']}.body"] = r["body"] or ""
    return saved


def value(saved: dict, key: str) -> str:
    """The text to show: what the clinic saved, or the default when nothing (or an empty text) is saved."""
    v = saved.get(key)
    if v is None or v == "":
        return FIELDS[key][1] if key in FIELDS else ""
    return v


def shown(saved: dict, section_id: str) -> bool:
    key = f"{section_id}.show"
    return key not in FIELDS or value(saved, key) != "0"


def accent(text: str) -> Markup:
    """Escape, then turn *words* into the gold italic accent used in headings."""
    return Markup(re.sub(r"\*([^*]+)\*", r"<em>\1</em>", str(escape(text or ""))))


def save(conn, section_id: str, form, user_id: int, now: str) -> list[str]:
    """Save one section's texts. A text equal to the default (or emptied) goes back to the default.
    Returns the keys that changed."""
    from .util import clean
    changed = []
    saved = load(conn)
    for key, _label, default, kind in SECTION_BY_ID[section_id]["fields"]:
        if kind == "show":
            new = "1" if form.get(key) == "1" else "0"
        else:
            new = clean(form.get(key), 4000 if kind == "text" else 300)
        old = value(saved, key)
        if new == old:
            continue
        changed.append(key)
        if key.startswith("@"):
            ckey, _, part = key[1:].rpartition(".")
            row = conn.one("SELECT key FROM site_content WHERE key = ?", (ckey,))
            if row:
                conn.execute(f"UPDATE site_content SET {part} = ?, updated_at = ?, updated_by = ? WHERE key = ?", (new, now, user_id, ckey))
            else:
                conn.execute(f"INSERT INTO site_content (key, {part}, updated_at, updated_by) VALUES (?, ?, ?, ?)", (ckey, new, now, user_id))
        elif new == default or (new == "" and kind != "show"):
            conn.execute("DELETE FROM site_text WHERE key = ?", (key,))
        elif conn.one("SELECT key FROM site_text WHERE key = ?", (key,)):
            conn.execute("UPDATE site_text SET value = ?, updated_at = ?, updated_by = ? WHERE key = ?", (new, now, user_id, key))
        else:
            conn.execute("INSERT INTO site_text (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?)", (key, new, now, user_id))
    return changed

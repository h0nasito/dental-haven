"""Seed data.

seed_base: configuration every installation needs (branches, services, placeholder website
copy, message templates, reminder rules, role defaults). All clinic facts are placeholders
marked "[to be confirmed]"; nothing is copied from Facebook.

seed_demo: SYNTHETIC demo data only (fictional people, fake phone numbers, example.test
emails). Never load it into a production database.
"""
from __future__ import annotations

import json
import random
import secrets
from datetime import date, datetime, timedelta

from .auth import hash_password
from .billing import compute_totals, line_amount, next_invoice_number
from .messaging import schedule_appointment_reminders
from .payroll import build_lines, evaluate_record
from .permissions import ROLE_DEFAULTS
from .util import fmt_dt, now, now_str, today

BRANCHES = [
    ("malolos", "Malolos"),
    ("guiguinto", "Guiguinto"),
    ("bocaue", "Bocaue"),
    ("sjdm", "San Jose del Monte (SJDM)"),
]

# Confirmed by the clinic (Sep 25, 2026). Hours are still to be confirmed.
# Dental chairs per branch (one dentist per chair, so this many patients can be seen at once).
BRANCH_CHAIRS = {"malolos": 5, "guiguinto": 3, "bocaue": 2, "sjdm": 2}

# Confirmed by the clinic (Sept 2026): all branches Monday–Saturday 9:00 AM–6:00 PM, closed Sundays.
CONFIRMED_HOURS = "Monday – Saturday: 9:00 AM – 6:00 PM\nSunday: Closed"

BRANCH_DETAILS = {
    "malolos": {
        "hours_text": CONFIRMED_HOURS,
        "address": "76 Paseo del Congreso, Malolos City, Bulacan (former Matt Balloons)",
        "phone": "+63 927 277 7833 / +63 942 381 1106",
        "facebook_url": "https://www.facebook.com/dentalhavenmalolos",
        "waze_url": "https://waze.com/ul?q=Dental%20Haven%20Malolos",
        "map_url": "https://www.google.com/maps/search/?api=1&query=Dental+Haven+76+Paseo+del+Congreso+Malolos+Bulacan",
    },
    "guiguinto": {
        "hours_text": CONFIRMED_HOURS,
        "address": "0113 CMISS Bldg., Cagayan Valley Road, Sta. Rita, Guiguinto, Bulacan (below Guiguinto Water District)",
        "phone": "+63 981 463 3664 / +63 906 835 5868",
        "facebook_url": "https://www.facebook.com/dentalhavenguiguinto",
        "waze_url": "https://waze.com/ul?q=Dental%20Haven%20Guiguinto",
        "map_url": "https://www.google.com/maps/search/?api=1&query=Dental+Haven+Cagayan+Valley+Road+Sta+Rita+Guiguinto+Bulacan",
    },
    "bocaue": {
        "hours_text": CONFIRMED_HOURS,
        "address": "758 McArthur Highway, Bunlo, Bocaue, Bulacan (in front of JIL Christian School)",
        "phone": "+63 966 558 5997 / +63 969 637 8075",
        "facebook_url": "https://www.facebook.com/dentalhavenbocaue",
        "waze_url": "https://waze.com/ul?q=Dental%20Haven%20Bocaue",
        "map_url": "https://www.google.com/maps/search/?api=1&query=Dental+Haven+758+McArthur+Highway+Bunlo+Bocaue+Bulacan",
    },
    "sjdm": {
        "hours_text": CONFIRMED_HOURS,
        "address": "368 Carriedo, Muzon Proper, San Jose del Monte, Bulacan (near Ace Hospital and McDonald's Muzon)",
        "phone": "+63 955 653 9702 / +63 962 213 1315",
        "facebook_url": "https://www.facebook.com/dentalhavensjdm",
        "waze_url": "https://waze.com/ul?q=Dental%20Haven%20SJDM",
        "map_url": "https://www.google.com/maps/search/?api=1&query=Dental+Haven+368+Carriedo+Muzon+San+Jose+del+Monte+Bulacan",
    },
}

EXPECT = ("## What to expect\n\n- A conversation about your concerns and health history\n"
          "- An examination, with images or scans when needed\n- Your options and costs explained before any treatment")

# (slug, name, category, default minutes, one-line summary, page body). Service list from Dental Haven (Sep 26, 2026, v2).
SERVICES = [
    ("general-dentistry", "Preventive & Diagnostic Services", "Preventive & Diagnostic", 30,
     "Check-ups & cleanings, dental X-rays & imaging, fluoride treatments, dental sealants, and oral cancer screenings.",
     "Stay ahead of problems with regular care and clear, detailed diagnostics.\n\n"
     "- Routine dental check-ups & cleanings: regular examinations and professional scaling and polishing to remove plaque and tartar.\n"
     "- Dental X-rays & imaging: panoramic (pano), cephalometric, and cone beam computed tomography (CBCT) for detailed 3D views of the jaw and teeth.\n"
     "- Fluoride treatments: high-concentration fluoride to strengthen tooth enamel and prevent decay.\n"
     "- Dental sealants: protective coatings on the chewing surfaces of the back teeth (molars) to prevent cavities.\n"
     "- Oral cancer screenings: an examination of the soft tissues of the mouth to detect early signs of abnormalities or disease.\n\n" + EXPECT),
    ("restorative-dentistry", "Restorative Services", "Restorative", 60,
     "Dental fillings, crowns, bridges, inlays & onlays, and root canal therapy.",
     "Repair decayed or damaged teeth and bring back their strength, shape and function.\n\n"
     "- Dental fillings: restoring decayed or damaged teeth with tooth-colored composite or amalgam.\n"
     "- Dental crowns (caps): custom-fitted covers that restore the shape, strength and appearance of badly decayed or broken teeth.\n"
     "- Dental bridges: fixed replacements for one or more missing teeth, anchored to the natural teeth beside the gap.\n"
     "- Inlays and onlays: lab-made fillings that repair larger areas of decay or damage on the chewing surfaces.\n"
     "- Root canal therapy (endodontics): removing infected pulp from inside a tooth to relieve pain and save the natural tooth.\n\n"
     "Crowns, bridges, inlays and onlays are crafted in our in-house digital dental laboratory.\n\n" + EXPECT),
    ("prosthodontics", "Prosthodontics & Tooth Replacement", "Prosthodontics & Tooth Replacement", 60,
     "Complete & partial dentures, dental implants, and veneers.",
     "Replace missing teeth and rebuild your smile with restorations made to fit you.\n\n"
     "- Complete & partial dentures: removable appliances that replace missing teeth and the surrounding gum tissue.\n"
     "- Dental implants: permanent titanium posts placed in the jawbone to support crowns, bridges or dentures.\n"
     "- Veneers: thin shells of porcelain or composite resin bonded to the front of the teeth to improve their appearance.\n\n"
     "Dentures, implant crowns and veneers are crafted in our in-house digital dental laboratory.\n\n" + EXPECT),
    ("orthodontics", "Orthodontics & TMJ", "Orthodontics & TMJ", 45,
     "Traditional braces, clear aligners, retainers, and management of TMJ disorders.",
     "Straighter teeth, a healthier bite, and relief for jaw joint problems.\n\n"
     "- Traditional braces: metal or ceramic brackets and wires that correct misaligned teeth and bite problems.\n"
     "- Clear aligners: removable, custom-made clear trays that gradually straighten the teeth.\n"
     "- Retainers: custom appliances worn after orthodontic treatment to keep the teeth in their new positions.\n"
     "- Management of TMJ disorders: care for jaw joint pain, clicking and limited opening.\n\n" + EXPECT),
    ("oral-surgery", "Oral Surgery", "Oral Surgery", 60,
     "Tooth extractions, wisdom tooth removal, and bone grafting.",
     "Safe, carefully planned surgical care, with 3D imaging when needed.\n\n"
     "- Tooth extractions: safe removal of teeth because of severe decay, trauma, crowding, or in preparation for braces.\n"
     "- Wisdom tooth removal (third molar surgery): removal of impacted or problematic wisdom teeth.\n"
     "- Bone grafting: rebuilding or regenerating bone in the jaw before implant placement.\n\n"
     "Planning can use in-house panoramic and CBCT imaging.\n\n" + EXPECT),
    ("aesthetic-dentistry", "Cosmetic Dentistry", "Cosmetic Dentistry", 60,
     "Teeth whitening, dental bonding, and smile makeovers.",
     "Brighten, repair and refine your smile.\n\n"
     "- Teeth whitening (bleaching): professional in-office or take-home treatments to brighten stained or discolored teeth.\n"
     "- Dental bonding: tooth-colored resin to repair chips, cracks or gaps.\n"
     "- Smile makeovers: a complete treatment plan combining several cosmetic procedures to enhance your whole smile.\n\n" + EXPECT),
    ("periodontal-care", "Periodontal (Gum) Care", "Periodontal (Gum) Care", 60,
     "Scaling and root planing, and gum grafting.",
     "Healthy gums are the foundation of a healthy smile.\n\n"
     "- Scaling and root planing: a deep cleaning below the gumline to treat gum disease (periodontitis) and remove bacterial toxins.\n"
     "- Gum grafting: procedures to treat receding gums and protect exposed tooth roots.\n\n" + EXPECT),
    ("pediatric-dentistry", "Pediatrics & Special Care Dentistry", "Pediatrics & Special Care", 45,
     "Preventive and corrective dentistry, crowns for kids, and conscious sedation.",
     "Gentle, child-friendly care, and extra support for patients with special needs.\n\n- Preventive and corrective dentistry\n"
     "- Crowns for kids\n- Conscious sedation\n\n" + EXPECT),
]
# Services renamed in the v2 list (old slug → new slug); the existing record, its bookings and guides are kept.
SERVICE_RENAMES = {"dental-implants": "oral-surgery"}
SERVICES_VERSION = 2   # bump when the clinic sends a new official service list

# Earlier placeholder wording, replaced automatically if nobody has edited it.
OLD_PLACEHOLDER = "[Service description to be confirmed"

CONTENT = {
    "home_hero": ("Happiest your teeth will ever be",
                  "Complete dental care for the whole family, with a specialty in aesthetic dentistry: smile makeovers, "
                  "veneers, crowns and implants crafted for beautiful, natural-looking results."),
    "home_about": ("About Dental Haven",
                   "[About-us copy to be provided by Dental Haven.]\n\nDental Haven serves patients at four branches: "
                   "Malolos, Guiguinto, Bocaue and San Jose del Monte."),
    "lab": ("Digital Solutions Dental Laboratory",
            "Our in-house digital lab allows for fast, high-precision fabrication of custom restorations (like crowns, bridges, "
            "and dentures) and 3D-printed appliances.\n\nWe're equipped with intraoral scanners, exocad design systems, 3D printers, "
            "milling machines, and in-house diagnostic imaging (including CBCT and Panoramic X-rays) for accurate treatments and "
            "faster turnaround times."),
    "contact": ("Contact us", "Call, text or message your nearest branch on Facebook. We're happy to help."),
    "booking_note": ("", "Choose your branch, service and a preferred time. This is a request, not a confirmed booking — our team "
                         "will contact you to confirm."),
    "consent_booking": ("", "I agree that Dental Haven may collect and use the information I provide to respond to my request and "
                            "arrange my appointment, as described in the privacy notice."),
    "consent_contact": ("", "I agree to receive appointment reminders and follow-up messages by SMS or email. I can opt out at any time."),
    "privacy_notice": ("Privacy notice (draft for Dental Haven's review)",
        "DRAFT — this notice must be reviewed and completed by Dental Haven and its Data Protection Officer before publication. "
        "It is not legal advice.\n\n"
        "## Who we are\nDental Haven ([registered business name to be confirmed]) operates dental clinics in Malolos, Guiguinto, "
        "Bocaue and San Jose del Monte, Bulacan, and an in-house digital dental laboratory.\n\n"
        "## What we collect\n- Contact details you give us (name, mobile number, email)\n- Your appointment request or inquiry\n"
        "- For patients: health and dental history, treatment records, images and billing records\n\n"
        "## Why we use it\n- To respond to inquiries and arrange appointments\n- To provide and document your dental care\n"
        "- To send appointment reminders and follow-ups if you agree\n- To bill for services and meet legal and regulatory obligations\n\n"
        "## Sharing\nWe share information only with people who need it to provide your care (for example our dentists and laboratory), "
        "with service providers acting for us under confidentiality obligations, or where the law requires. [List of processors to be confirmed.]\n\n"
        "## How long we keep it\n[Retention periods to be confirmed by Dental Haven.]\n\n"
        "## Your rights\nUnder the Data Privacy Act of 2012 (Republic Act No. 10173) you may ask to access or correct your "
        "information, object to certain processing, and withdraw consent to optional messages. You may also file a complaint "
        "with the National Privacy Commission.\n\n"
        "## Contact our Data Protection Officer\n[DPO name, email and address to be confirmed.]"),
}

TEMPLATES = [
    ("lead_general", "General inquiry reply", "lead_reply",
     "Hi {{first_name}}! Thank you for messaging Dental Haven. We'd be happy to help. May we know which branch is most convenient for you "
     "(Malolos, Guiguinto, Bocaue or San Jose del Monte) and your preferred day and time? You can also request an appointment on our website."),
    ("lead_price", "Price inquiry reply (no prices)", "lead_reply",
     "Hi {{first_name}}! Thanks for asking about {{service}}. The cost depends on your dentist's assessment, so we recommend a consultation "
     "first. Your dentist will explain your options and the cost before any treatment. Would you like us to book a consultation at {{branch}}?"),
    ("lead_hours", "Branch location & hours", "lead_reply",
     "Hi {{first_name}}! Our {{branch}} branch can be reached at {{branch_phone}}. We'll send you the address and clinic hours. "
     "Would you like to schedule a visit?"),
    ("ack_request", "Booking request received", "booking_ack",
     "Hi {{first_name}}, we received your appointment request at Dental Haven {{branch}}. It is not yet confirmed — we will contact you shortly "
     "to confirm your schedule."),
    ("ack_confirmed", "Appointment confirmed", "booking_ack",
     "Hi {{first_name}}, your {{service}} appointment at Dental Haven {{branch}} is confirmed for {{date}} at {{time}}. "
     "To reschedule, please call {{branch_phone}}."),
    ("rem_day_before", "Reminder — day before", "appointment_reminder",
     "Hi {{first_name}}, this is Dental Haven {{branch}} reminding you of your appointment on {{date}} at {{time}}. "
     "To reschedule, call {{branch_phone}}. Reply STOP to opt out of reminders."),
    ("rem_same_day", "Reminder — same day", "appointment_reminder",
     "Hi {{first_name}}, see you today at {{time}} at Dental Haven {{branch}}. Call {{branch_phone}} if you're running late."),
    ("fu_post_treatment", "Post-treatment check-in", "follow_up",
     "Hi {{first_name}}, this is Dental Haven {{branch}} checking in after your recent visit. How are you feeling? If you have any "
     "concerns, please call us at {{branch_phone}}."),
    ("fu_recall", "Check-up recall", "follow_up",
     "Hi {{first_name}}, it's time for your regular dental check-up at Dental Haven {{branch}}. Would you like us to book a schedule for you?"),
    ("fu_missed", "Missed appointment", "follow_up",
     "Hi {{first_name}}, we missed you at your Dental Haven appointment. We hope everything is okay. Would you like to choose a new schedule?"),
]


# Wording replaced automatically when staff haven't edited it (the clinic chose the original hero wording).
OLD_CONTENT = {"home_hero": "Complete dental care for the whole family, all in one clinic: check-ups and cleanings, fillings, "
                            "care for kids, braces, veneers and crowns, dentures, and implants."}


def _upsert_content(conn, key, title, body):
    row = conn.one("SELECT * FROM site_content WHERE key = ?", (key,))
    if row and row["body"] == OLD_CONTENT.get(key) and row["body"] != body:
        conn.execute("UPDATE site_content SET body = ?, updated_at = ? WHERE key = ?", (body, now_str(), key))
        return
    if not row:
        conn.execute("INSERT INTO site_content (key, title, body, updated_at) VALUES (?, ?, ?, ?)", (key, title, body, now_str()))
    elif row["updated_by"] is None and "[" in (row["body"] or "") and "[" not in body:
        # Never edited by staff and still showing placeholder text: use the confirmed wording.
        conn.execute("UPDATE site_content SET title = ?, body = ?, updated_at = ? WHERE key = ?", (title, body, now_str(), key))


def _top_up_chairs(conn, branch_id, slug):
    """Add chairs until the branch has its set number. Never removes or re-enables chairs staff switched off."""
    have = conn.one("SELECT COUNT(*) AS n FROM resources WHERE branch_id = ? AND kind = 'chair'", (branch_id,))["n"]
    for n in range(have + 1, BRANCH_CHAIRS.get(slug, 2) + 1):
        conn.insert("resources", {"branch_id": branch_id, "name": f"Chair {n}", "kind": "chair", "active": 1})


def seed_base(conn):
    with conn.transaction():
        for i, (slug, name) in enumerate(BRANCHES):
            existing = conn.one("SELECT * FROM branches WHERE slug = ?", (slug,))
            if existing:
                # Fill in confirmed details only where the placeholder was never edited.
                det = BRANCH_DETAILS.get(slug, {})
                upd = {k: v for k, v in det.items() if not existing.get(k) or str(existing.get(k)).startswith("[")}
                if upd:
                    conn.update("branches", existing["id"], upd)
                _top_up_chairs(conn, existing["id"], slug)
                continue
            bid = conn.insert("branches", {
                "slug": slug, "name": name, "address": f"[{name} address to be confirmed]",
                "phone": "[Contact number to be confirmed]", "email": "", "map_url": "",
                "hours_text": "[Clinic hours to be confirmed]",
                **BRANCH_DETAILS.get(slug, {}),
                "intro": f"Welcome to Dental Haven {name}. [Branch description to be confirmed.]",
                "active": 1, "sort_order": i, "created_at": now_str()})
            for wd in range(7):
                conn.execute("INSERT INTO branch_hours (branch_id, weekday, open_time, close_time, closed) VALUES (?, ?, '09:00', '18:00', ?)",
                             (bid, wd, 1 if wd == 6 else 0))
            conn.execute("INSERT INTO invoice_sequences (branch_id, prefix, next_no) VALUES (?, ?, 1)", (bid, slug[:3].upper()))
            _top_up_chairs(conn, bid, slug)
        for old, newslug in SERVICE_RENAMES.items():
            if conn.one("SELECT id FROM services WHERE slug = ?", (old,)) and not conn.one("SELECT id FROM services WHERE slug = ?", (newslug,)):
                conn.execute("UPDATE services SET slug = ? WHERE slug = ?", (newslug, old))
        from . import settings as _settings
        apply_list = int(_settings.get("seed.services_version", conn) or 1) < SERVICES_VERSION
        for i, (slug, name, cat, mins, summary, body) in enumerate(SERVICES):
            existing = conn.one("SELECT * FROM services WHERE slug = ?", (slug,))
            if existing and apply_list:
                # The clinic sent an official service list: apply it once. Later edits in the admin are kept.
                conn.update("services", existing["id"], {"name": name, "category": cat, "summary": summary, "body": body,
                                                         "sort_order": i, "active": 1})
                continue
            if existing and OLD_PLACEHOLDER in (existing["body"] or ""):
                conn.update("services", existing["id"], {"name": name, "category": cat, "summary": summary, "body": body,
                                                         "sort_order": i})
            if not existing:
                conn.insert("services", {"slug": slug, "name": name, "category": cat, "summary": summary, "body": body,
                                         "default_duration_min": mins, "default_price_cents": None, "bookable_online": 1,
                                         "active": 1, "sort_order": i})
        if apply_list:
            _settings.put("seed.services_version", SERVICES_VERSION, None, conn)
            from .prices_content import SAMPLE_PRICES
            from .guides_content import GUIDES
            sid = {r["slug"]: r["id"] for r in conn.all("SELECT id, slug FROM services")}
            for pname, sslug, *_ in SAMPLE_PRICES:  # sample prices only; real prices are never touched
                if sslug in sid:
                    conn.execute("UPDATE price_items SET service_id = ? WHERE name = ? AND sample = 1", (sid[sslug], pname))
            for gd in GUIDES:  # guides nobody has edited
                if gd["service"] in sid:
                    conn.execute("UPDATE guides SET service_id = ? WHERE slug = ? AND updated_by IS NULL", (sid[gd["service"]], gd["slug"]))
        for key, (title, body) in CONTENT.items():
            _upsert_content(conn, key, title, body)
        for key, name, purpose, body in TEMPLATES:
            if not conn.one("SELECT id FROM message_templates WHERE key = ?", (key,)):
                conn.insert("message_templates", {"key": key, "name": name, "purpose": purpose, "channel": "any", "body": body,
                                                  "active": 1, "updated_at": now_str()})
        if not conn.scalar("SELECT COUNT(*) FROM reminder_rules"):
            t1 = conn.scalar("SELECT id FROM message_templates WHERE key = 'rem_day_before'")
            t2 = conn.scalar("SELECT id FROM message_templates WHERE key = 'rem_same_day'")
            conn.insert("reminder_rules", {"name": "Day before", "purpose": "appointment", "offset_minutes": -24 * 60,
                                           "template_id": t1, "channel": "sms", "active": 1})
            conn.insert("reminder_rules", {"name": "Same day (3 hours before)", "purpose": "appointment", "offset_minutes": -3 * 60,
                                           "template_id": t2, "channel": "sms", "active": 0})
        if not conn.scalar("SELECT COUNT(*) FROM price_items"):
            # Placeholder prices for testing, marked sample=1. Never shown to the public until the clinic
            # enters its real prices and turns on "Show prices to patients".
            from .prices_content import SAMPLE_PRICES
            for i, (pname, sslug, pfrom, pto, unit, kw) in enumerate(SAMPLE_PRICES):
                svc = conn.one("SELECT id FROM services WHERE slug = ?", (sslug,))
                conn.insert("price_items", {"name": pname, "service_id": svc["id"] if svc else None, "price_from_cents": pfrom * 100,
                                            "price_to_cents": pto * 100 if pto else None, "unit": unit, "keywords": kw,
                                            "sort_order": i, "published": 1, "sample": 1, "updated_at": now_str()})
        from .guides_content import GUIDES
        for i, gd in enumerate(GUIDES):
            if not conn.one("SELECT id FROM guides WHERE slug = ?", (gd["slug"],)):  # added once; staff edits are kept
                svc = conn.one("SELECT id FROM services WHERE slug = ?", (gd["service"],))
                conn.insert("guides", {"slug": gd["slug"], "service_id": svc["id"] if svc else None, "title": gd["title"],
                                       "summary": gd["summary"], "body": gd["body"], "sort_order": i, "published": 1,
                                       "created_at": now_str(), "updated_at": now_str()})
        if not conn.scalar("SELECT COUNT(*) FROM laboratories"):
            conn.insert("laboratories", {"name": "DSDL", "address": "Liang, Malolos, Bulacan", "phone": "", "active": 1})
        # Permissions added after a database was created are granted once to the roles that have them by default;
        # afterwards the super admin's choices in Role access are kept.
        from . import settings as _settings2
        granted = set(_settings2.get("seed.perms_granted", conn) or [])
        new_perms = {"quotes.view", "quotes.manage"} - granted
        if new_perms and conn.scalar("SELECT COUNT(*) FROM role_permissions"):
            for role, perms in ROLE_DEFAULTS.items():
                for perm in new_perms & set(perms):
                    if not conn.one("SELECT 1 AS x FROM role_permissions WHERE role = ? AND permission = ?", (role, perm)):
                        conn.execute("INSERT INTO role_permissions (role, permission) VALUES (?, ?)", (role, perm))
        if new_perms:
            _settings2.put("seed.perms_granted", sorted(granted | new_perms), None, conn)
        if not conn.scalar("SELECT COUNT(*) FROM role_permissions"):
            for role, perms in ROLE_DEFAULTS.items():
                for p in perms:
                    conn.execute("INSERT INTO role_permissions (role, permission) VALUES (?, ?)", (role, p))


# ---------------------------------------------------------------------------
# Synthetic demo data
# ---------------------------------------------------------------------------

FIRST = ["Andrea", "Bea", "Carlo", "Dianne", "Enzo", "Fatima", "Gabriel", "Hannah", "Ivan", "Jasmine", "Kevin", "Liza", "Marco",
         "Nina", "Oscar", "Patricia", "Quincy", "Rhea", "Samuel", "Tricia", "Ulysses", "Vina", "Warren", "Ysabel", "Zoe", "Joaquin",
         "Maricel", "Rafael", "Camille", "Paolo"]
LAST = ["Aquino", "Bautista", "Cruz", "Dela Rosa", "Espiritu", "Fernandez", "Garcia", "Hernandez", "Ilagan", "Jimenez", "Lopez",
        "Mendoza", "Navarro", "Ocampo", "Pascual", "Quiambao", "Ramos", "Santos", "Torres", "Valdez", "Villanueva", "Yap"]
ALLERGIES = ["", "", "", "", "Penicillin", "Latex", "Ibuprofen", ""]
CONDITIONS = ["", "", "", "Hypertension (controlled)", "Type 2 diabetes", "Asthma", ""]


def seed_demo(conn, password: str | None = None) -> str:
    seed_base(conn)
    if conn.one("SELECT id FROM users WHERE email = 'admin@demo.dentalhaven.test'"):
        return password or "(unchanged — demo data already loaded)"
    rnd = random.Random(20260924)
    password = password or ("Demo-" + secrets.token_urlsafe(6).replace("-", "x").replace("_", "y") + "9")
    pw_hash = hash_password(password)
    branches = conn.all("SELECT * FROM branches ORDER BY sort_order")
    services = {s["slug"]: s for s in conn.all("SELECT * FROM services")}
    bid = {b["slug"]: b["id"] for b in branches}
    ts = now_str()

    def user(email, name, role, branch_slugs, position):
        uid = conn.insert("users", {"email": email, "name": name, "password_hash": pw_hash, "role": role, "active": 1,
                                    "must_change_password": 0, "created_at": ts})
        for s in branch_slugs:
            conn.execute("INSERT INTO user_branches (user_id, branch_id) VALUES (?, ?)", (uid, bid[s]))
        conn.insert("employees", {"user_id": uid, "full_name": name, "position": position,
                                  "employment_type": "associate" if role == "dentist" else "regular",
                                  "primary_branch_id": bid[branch_slugs[0]] if branch_slugs else None, "active": 1, "created_at": ts})
        return uid

    with conn.transaction():
        admin = user("admin@demo.dentalhaven.test", "Demo Super Admin", "super_admin", [], "Clinic manager")
        dentists = {
            "malolos": user("dentist.malolos@demo.dentalhaven.test", "Dr. Lea Ramos (demo)", "dentist", ["malolos", "guiguinto"], "Associate dentist"),
            "guiguinto": user("dentist.guiguinto@demo.dentalhaven.test", "Dr. Paolo Cruz (demo)", "dentist", ["guiguinto"], "Associate dentist — prosthodontics"),
            "bocaue": user("dentist.bocaue@demo.dentalhaven.test", "Dr. Mia Santos (demo)", "dentist", ["bocaue", "malolos"], "Associate dentist — implants"),
            "sjdm": user("dentist.sjdm@demo.dentalhaven.test", "Dr. Nico Valdez (demo)", "dentist", ["sjdm"], "Associate dentist — aesthetics"),
        }
        for slug, name in BRANCHES:
            user(f"reception.{slug}@demo.dentalhaven.test", f"{name.split(' (')[0]} Receptionist (demo)", "receptionist", [slug], "Receptionist")
        user("staff.malolos@demo.dentalhaven.test", "Malolos Staff (demo)", "staff", ["malolos", "guiguinto"], "Branch coordinator")
        user("staff.bocaue@demo.dentalhaven.test", "Bocaue Staff (demo)", "staff", ["bocaue", "sjdm"], "Branch coordinator")
        for slug, name in BRANCHES:
            conn.insert("employees", {"full_name": f"{name.split(' (')[0]} Dental Assistant (demo)", "position": "Dental assistant",
                                      "employment_type": "regular", "primary_branch_id": bid[slug], "active": 1, "created_at": ts})

        # dentist schedules
        sched = {"malolos": [("malolos", range(0, 4)), ("guiguinto", [4, 5])], "guiguinto": [("guiguinto", range(0, 5))],
                 "bocaue": [("bocaue", range(0, 4)), ("malolos", [4, 5])], "sjdm": [("sjdm", range(0, 6))]}
        for d, blocks in sched.items():
            for b, days in blocks:
                for wd in days:
                    conn.insert("dentist_schedules", {"dentist_id": dentists[d], "branch_id": bid[b], "weekday": wd,
                                                      "start_time": "09:00", "end_time": "17:00"})

        # patients
        patients = []
        for i in range(60):
            fn, ln = rnd.choice(FIRST), rnd.choice(LAST)
            home = rnd.choice(branches)
            sms = rnd.random() < 0.8
            pid = conn.insert("patients", {
                "chart_no": f"DH-{i + 1:06d}", "first_name": fn, "last_name": ln,
                "birth_date": date(rnd.randint(1955, 2015), rnd.randint(1, 12), rnd.randint(1, 28)).isoformat(),
                "sex": rnd.choice(["female", "male"]), "phone": f"0900 000 {i + 1:04d}", "email": f"demo.patient{i + 1}@example.test",
                "address": "Demo address (synthetic)", "preferred_branch_id": home["id"], "consent_privacy": 1, "consent_privacy_at": ts,
                "contact_sms": 1 if sms else 0, "contact_email": 1 if rnd.random() < 0.4 else 0, "opt_out_all": 1 if i % 17 == 0 else 0,
                "preferred_channel": "sms" if sms else "call", "source": "demo", "is_demo": 1, "created_at": ts, "updated_at": ts})
            allergy = rnd.choice(ALLERGIES)
            cond = rnd.choice(CONDITIONS)
            conn.execute("INSERT INTO patient_history (patient_id, medical_conditions, allergies, medications, dental_history, updated_at, updated_by) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", (pid, cond, allergy, "Metformin (demo)" if "diabetes" in cond else "",
                                                          "Synthetic demo history.", ts, admin))
            if allergy:
                conn.execute("UPDATE patients SET alert_flag = ? WHERE id = ?", (f"{allergy} allergy", pid))
            patients.append({"id": pid, "branch": home["slug"], "first": fn})

        # appointments: past 45 days + next 12 days, per dentist per scheduled day
        start_day = today() - timedelta(days=45)
        slot_times = ["09:00", "10:00", "11:00", "13:30", "14:30", "15:30"]
        svc_list = list(services.values())
        appt_ids = []
        resources = {b["id"]: [r["id"] for r in conn.all("SELECT id FROM resources WHERE branch_id = ?", (b["id"],))] for b in branches}
        busy = set()
        for offset in range(58):
            day = start_day + timedelta(days=offset)
            for dkey, blocks in sched.items():
                for bslug, days in blocks:
                    if day.weekday() not in days:
                        continue
                    for t in slot_times:
                        if rnd.random() > (0.55 if day < today() else 0.35):
                            continue
                        svc = rnd.choice(svc_list)
                        mins = min(svc["default_duration_min"], 60)
                        s = datetime.combine(day, datetime.strptime(t, "%H:%M").time())
                        e = s + timedelta(minutes=mins)
                        b_id = bid[bslug]
                        res = next((r for r in resources[b_id] if (r, day, t) not in busy), None)
                        if res is None:
                            continue
                        busy.add((res, day, t))
                        cands = [p for p in patients if p["branch"] == bslug] or patients
                        p = rnd.choice(cands)
                        if s < now():
                            status = rnd.choices(["completed", "no_show", "cancelled"], [0.85, 0.07, 0.08])[0]
                        else:
                            status = rnd.choices(["confirmed", "requested"], [0.85, 0.15])[0]
                        aid = conn.insert("appointments", {
                            "patient_id": p["id"], "branch_id": b_id, "service_id": svc["id"], "dentist_id": dentists[dkey],
                            "resource_id": res, "start_at": fmt_dt(s), "end_at": fmt_dt(e), "status": status,
                            "source": rnd.choice(["staff", "phone", "facebook", "walk_in", "website"]),
                            "cancel_reason": "Patient rescheduled (demo)" if status == "cancelled" else "",
                            "created_by": admin, "created_at": fmt_dt(s - timedelta(days=5)),
                            "completed_at": fmt_dt(e) if status == "completed" else None})
                        conn.execute("INSERT OR IGNORE INTO patient_assignments (patient_id, dentist_id, created_at) VALUES (?, ?, ?)"
                                     if not conn.database.is_postgres else
                                     "INSERT INTO patient_assignments (patient_id, dentist_id, created_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                                     (p["id"], dentists[dkey], ts))
                        appt_ids.append((aid, status, p, svc, b_id, dentists[dkey], s))

        # clinical notes, procedures, invoices for completed visits
        demo_prices = {"general-dentistry": 80000, "prosthodontics": 1200000, "oral-surgery": 350000, "restorative-dentistry": 500000, "periodontal-care": 400000, "aesthetic-dentistry": 900000, "orthodontics": 4500000,
                       "pediatric-dentistry": 150000}
        methods = ["cash", "gcash", "maya", "card", "bank_transfer"]
        for aid, status, p, svc, b_id, did, s in appt_ids:
            if status != "completed":
                continue
            conn.insert("clinical_notes", {"patient_id": p["id"], "appointment_id": aid, "author_id": did,
                                           "body": f"Demo note: {svc['name']} visit. Findings and treatment recorded (synthetic).",
                                           "created_at": fmt_dt(s + timedelta(minutes=45))})
            conn.insert("procedures", {"patient_id": p["id"], "appointment_id": aid, "service_id": svc["id"], "branch_id": b_id,
                                       "tooth": rnd.choice(["", "11", "16", "26", "36", "46"]), "description": f"{svc['name']} (demo procedure)",
                                       "status": "completed", "performed_by": did, "performed_at": s.date().isoformat(), "created_at": fmt_dt(s)})
            price = demo_prices[svc["slug"]]
            items = [{"amount_cents": price}]
            totals = compute_totals(items, 0, conn)
            number = next_invoice_number(conn, b_id)
            inv = conn.insert("invoices", {"number": number, "branch_id": b_id, "patient_id": p["id"], "appointment_id": aid, "status": "issued",
                                           "issued_at": s.date().isoformat(), **totals, "notes": "Demo amounts — not clinic prices",
                                           "created_by": admin, "created_at": fmt_dt(s)})
            conn.insert("invoice_items", {"invoice_id": inv, "service_id": svc["id"], "description": f"{svc['name']} (demo amount)", "qty": 1,
                                          "unit_price_cents": price, "discount_cents": 0, "amount_cents": line_amount(1, price, 0)})
            r = rnd.random()
            if r < 0.7:
                paid = price
            elif r < 0.9:
                paid = price // 2
            else:
                paid = 0
            if paid:
                conn.insert("payments", {"invoice_id": inv, "branch_id": b_id, "kind": "payment", "amount_cents": paid,
                                         "method": rnd.choice(methods), "reference": "", "received_at": (s.date() + timedelta(days=rnd.choice([0, 0, 1, 3]))).isoformat()
                                         if s.date() + timedelta(days=3) <= today() else s.date().isoformat(),
                                         "received_by": admin, "status": "valid", "created_at": fmt_dt(s)})

        # treatment plans for some patients
        for p in rnd.sample(patients, 15):
            did = conn.scalar("SELECT dentist_id FROM patient_assignments WHERE patient_id = ? LIMIT 1", (p["id"],))
            if not did:
                continue
            plan = conn.insert("treatment_plans", {"patient_id": p["id"], "dentist_id": did, "title": "Demo treatment plan",
                                                   "status": rnd.choice(["presented", "accepted", "in_progress"]), "notes": "Synthetic plan.",
                                                   "created_at": ts, "updated_at": ts})
            for seq, (desc, svc) in enumerate([("Crown preparation (demo)", "prosthodontics"), ("Implant consultation (demo)", "prosthodontics")], 1):
                conn.insert("treatment_plan_items", {"plan_id": plan, "service_id": services[svc]["id"], "tooth": rnd.choice(["36", "46", "14"]),
                                                     "description": desc, "estimate_cents": None, "status": "pending", "seq": seq})

        # follow-ups
        for aid, status, p, svc, b_id, did, s in appt_ids:
            if status == "no_show":
                conn.insert("follow_ups", {"branch_id": b_id, "patient_id": p["id"], "appointment_id": aid, "kind": "no_show",
                                           "title": "Missed appointment — call to rebook", "due_at": fmt_dt(s + timedelta(hours=3)),
                                           "status": "open" if s > now() - timedelta(days=10) else "done",
                                           "outcome": "" if s > now() - timedelta(days=10) else "Called; rebooked (demo)", "created_at": fmt_dt(s)})
            elif status == "completed" and svc["slug"] in ("restorative-dentistry", "prosthodontics") and rnd.random() < 0.6:
                due = s + timedelta(days=7)
                conn.insert("follow_ups", {"branch_id": b_id, "patient_id": p["id"], "appointment_id": aid, "kind": "post_treatment",
                                           "title": f"Post-treatment check: {svc['name']}", "due_at": fmt_dt(due.replace(hour=10, minute=0)),
                                           "status": "open" if due > now() - timedelta(days=4) else "done",
                                           "outcome": "" if due > now() - timedelta(days=4) else "Patient doing well (demo)", "created_at": fmt_dt(s)})

        # booking requests (pending)
        for i in range(6):
            b = rnd.choice(branches)
            day = today() + timedelta(days=rnd.randint(1, 10))
            if day.weekday() == 6:
                day += timedelta(days=1)
            conn.insert("booking_requests", {"ref_code": f"DH-DEMO{i + 1:02d}", "full_name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
                                             "phone": f"0900 111 {i + 1:04d}", "email": "", "branch_id": b["id"],
                                             "service_id": rnd.choice(svc_list)["id"], "preferred_start": f"{day.isoformat()} {rnd.choice(['10:00', '14:00', '15:30'])}",
                                             "message": "Demo request (synthetic).", "consent_privacy": 1, "consent_contact": 1,
                                             "status": "pending", "created_at": fmt_dt(now() - timedelta(hours=rnd.randint(1, 40)))})

        # leads
        lead_statuses = ["new", "new", "new", "contacted", "contacted", "qualified", "booked", "converted", "lost"]
        receptionists = [r["id"] for r in conn.all("SELECT id FROM users WHERE role = 'receptionist'")]
        for i in range(28):
            b = rnd.choice(branches)
            st = rnd.choice(lead_statuses)
            created = now() - timedelta(days=rnd.randint(0, 40), hours=rnd.randint(0, 8))
            lid = conn.insert("leads", {"full_name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", "phone": f"0900 222 {i + 1:04d}",
                                        "email": "", "source": rnd.choice(["facebook", "messenger", "messenger", "website", "phone", "walk_in", "referral"]),
                                        "branch_id": b["id"], "service_id": rnd.choice(svc_list)["id"],
                                        "message": rnd.choice(["How much is an implant?", "Available po ba bukas?", "Do you do dentures?",
                                                               "Magkano po cleaning?", "Is the SJDM branch open Sunday?"]) + " (demo)",
                                        "owner_id": rnd.choice(receptionists) if st != "new" else None, "status": st,
                                        "next_follow_up_at": fmt_dt(now() + timedelta(days=rnd.randint(-3, 5))) if st in ("contacted", "qualified") else None,
                                        "consent_contact": 1, "created_at": fmt_dt(created), "updated_at": fmt_dt(created)})
            conn.execute("INSERT INTO lead_activities (lead_id, kind, body, created_at) VALUES (?, 'created', 'Demo lead', ?)", (lid, fmt_dt(created)))

        # attendance: last 30 days
        emps = conn.all("SELECT e.*, u.role FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.primary_branch_id IS NOT NULL")
        for e in emps:
            for back in range(30, 0, -1):
                d = today() - timedelta(days=back)
                if d.weekday() == 6 or rnd.random() < 0.08:
                    continue
                tin = rnd.choice(["08:45", "08:50", "08:55", "08:58", "09:00", "08:52", "08:57", "08:40", "08:59", "09:12"]) if rnd.random() > 0.03 else None
                tout = rnd.choice(["18:00", "18:05", "18:10", "18:02", "18:15", "18:00", "17:40"]) if rnd.random() > 0.04 else None
                rec = {"employee_id": e["id"], "branch_id": e["primary_branch_id"], "work_date": d.isoformat(), "time_in": tin, "time_out": tout, "status": "ok"}
                status, note = evaluate_record(conn, rec)
                conn.insert("time_records", {**rec, "status": status, "exception_note": note, "source": "import", "created_at": ts})
            # synthetic compensation (clearly labelled)
            conn.insert("compensation", {"employee_id": e["id"], "basis": "percentage" if e["role"] == "dentist" else "daily",
                                         "rate_cents": None if e["role"] == "dentist" else 70000,
                                         "percentage_bp": 4000 if e["role"] == "dentist" else None,
                                         "notes": "DEMO VALUE — not a real rate", "effective_from": (today() - timedelta(days=90)).isoformat(),
                                         "created_by": admin, "created_at": ts})

        # draft payroll period
        end = today() - timedelta(days=1)
        start = end - timedelta(days=14)
        pid = conn.insert("payroll_periods", {"name": f"Demo cut-off {start.isoformat()} to {end.isoformat()}", "start_date": start.isoformat(),
                                              "end_date": end.isoformat(), "branch_id": None, "status": "draft", "rules_confirmed": 0,
                                              "created_by": admin, "created_at": ts})
        period = conn.one("SELECT * FROM payroll_periods WHERE id = ?", (pid,))
        for line in build_lines(conn, period):
            conn.insert("payroll_lines", {"period_id": pid, **line})

        # a report card waiting for review
        p = patients[0]
        did = conn.scalar("SELECT dentist_id FROM patient_assignments WHERE patient_id = ? LIMIT 1", (p["id"],))
        if did:
            from .views.reportcards import build_snapshot, draft_summary
            snap = build_snapshot(conn, p["id"], (today() - timedelta(days=90)).isoformat(), today().isoformat())
            summary, recs = draft_summary(snap)
            conn.insert("report_cards", {"patient_id": p["id"], "branch_id": conn.scalar("SELECT preferred_branch_id FROM patients WHERE id = ?", (p["id"],)),
                                         "period_from": (today() - timedelta(days=90)).isoformat(), "period_to": today().isoformat(),
                                         "reviewer_id": did, "status": "pending_review", "summary": summary, "recommendations": recs,
                                         "snapshot": json.dumps(snap, default=str), "generated_by": admin, "generated_at": ts})

    # sample chart entries, prescription, certificate, expenses, lab cases and a deposit (all synthetic)
    with conn.transaction():
        p0 = patients[0]["id"]
        d0 = conn.scalar("SELECT dentist_id FROM patient_assignments WHERE patient_id = ? LIMIT 1", (p0,)) or admin
        for tooth, cond, surf in (("16", "restoration", "O"), ("26", "caries", "MO"), ("36", "rct", ""), ("36", "crown", ""),
                                  ("46", "missing", ""), ("11", "sound", ""), ("47", "extraction_needed", "")):
            conn.insert("chart_entries", {"patient_id": p0, "tooth": tooth, "surfaces": surf, "condition": cond, "note": "Demo entry",
                                          "recorded_by": d0, "recorded_on": (today() - timedelta(days=20)).isoformat(), "created_at": ts})
        rx = conn.insert("prescriptions", {"patient_id": p0, "branch_id": conn.scalar("SELECT preferred_branch_id FROM patients WHERE id = ?", (p0,)),
                                           "prescriber_id": d0, "prescribed_on": today().isoformat(), "notes": "", "created_by": d0, "created_at": ts})
        conn.insert("prescription_items", {"prescription_id": rx, "medicine": "Amoxicillin 500 mg capsule (demo)", "dosage": "500 mg",
                                           "quantity": "#21", "instructions": "1 capsule every 8 hours for 7 days", "seq": 0})
        conn.insert("prescription_items", {"prescription_id": rx, "medicine": "Mefenamic acid 500 mg (demo)", "dosage": "500 mg",
                                           "quantity": "#10", "instructions": "1 capsule every 8 hours as needed for pain", "seq": 1})
        cats = ["Dental supplies", "Laboratory fees", "Utilities (power, water, internet)", "Rent", "Office supplies"]
        for i in range(24):
            b = rnd.choice(branches)
            conn.insert("expenses", {"branch_id": b["id"], "expense_date": (today() - timedelta(days=rnd.randint(0, 40))).isoformat(),
                                     "category": rnd.choice(cats), "description": "Demo expense", "payee": "Demo supplier",
                                     "amount_cents": rnd.choice([85000, 150000, 420000, 1200000, 2500000]), "method": "cash",
                                     "status": "posted" if i % 5 else "draft", "created_by": admin, "created_at": ts,
                                     "posted_by": admin if i % 5 else None, "posted_at": ts if i % 5 else None})
        lab = conn.scalar("SELECT id FROM laboratories WHERE name = 'DSDL'")
        for i, (ctype, st) in enumerate((("Crown (zirconia / all-ceramic)", "in_progress"), ("Complete denture", "sent"),
                                         ("Bridge", "ready"), ("Partial denture (flexible)", "delivered"))):
            pp = patients[i + 1]
            ddent = conn.scalar("SELECT dentist_id FROM patient_assignments WHERE patient_id = ? LIMIT 1", (pp["id"],)) or None
            cid = conn.insert("lab_cases", {"lab_id": lab, "branch_id": bid[pp["branch"]], "patient_id": pp["id"], "dentist_id": ddent,
                                            "case_type": ctype, "teeth": rnd.choice(["36", "11, 21", "Upper arch"]), "shade": "A2",
                                            "status": st, "sent_on": (today() - timedelta(days=6 - i)).isoformat(),
                                            "due_on": (today() + timedelta(days=i - 1)).isoformat(), "instructions": "Demo case",
                                            "created_by": admin, "created_at": ts, "updated_at": ts})
            conn.insert("lab_case_events", {"case_id": cid, "user_id": admin, "status": st, "note": "Demo", "created_at": ts})
        conn.insert("patient_credits", {"patient_id": p0, "branch_id": conn.scalar("SELECT preferred_branch_id FROM patients WHERE id = ?", (p0,)),
                                        "kind": "deposit", "amount_cents": 500000, "method": "gcash", "entry_date": today().isoformat(),
                                        "notes": "Demo advance payment for braces", "created_by": admin, "created_at": ts})
        for pp in patients[5:8]:  # a few birthdays this week
            bd = conn.scalar("SELECT birth_date FROM patients WHERE id = ?", (pp["id"],))
            nd = (today() + timedelta(days=rnd.randint(0, 6)))
            conn.execute("UPDATE patients SET birth_date = ? WHERE id = ?", (f"{bd[:4]}-{nd.strftime('%m-%d')}", pp["id"]))

    # reminders for upcoming confirmed appointments
    with conn.transaction():
        for aid, status, *_ in appt_ids:
            if status == "confirmed":
                schedule_appointment_reminders(conn, aid)
    return password

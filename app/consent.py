"""Patient consent forms: starting drafts and filling in the patient's details.

The drafts below are plain starting points only. They are NOT approved clinic or legal wording: an admin edits each form under
Administration → Consent forms, and a dentist approves it before patients can sign it. Editing a form clears its approval.
Blanks the staff fill in when the patient signs: {procedure} and {teeth}. Filled in automatically: {patient}, {age}, {date},
{branch}, {dentist}, {address}.
The orthodontic form uses the clinic's own wording (consent_ortho.py).
"""
from __future__ import annotations

from .consent_clinic import FORMS as CLINIC_FORMS
from .consent_ortho import BODY as ORTHO_BODY, TITLE as ORTHO_TITLE

# How my first braces draft began (replaced by the clinic's own wording, Nov 2026).
OLD_ORTHO_START = "I, {patient}, {age}, consent to orthodontic treatment (braces)"

# Filled in from the patient's record and the signing screen's dentist.
AUTO = ("patient", "age", "address", "date", "branch", "dentist")
# Typed by the staff on the signing screen (only the ones a form uses are asked): name → label.
STAFF_FIELDS = {"procedure": "Treatment / procedure", "teeth": "Tooth / teeth", "site": "Surgical site", "material": "Restorative material",
                "anesthesia": "Anesthesia chosen", "other_risks": "Other risks", "fee": "Remake / re-fabrication fee (₱)",
                "lab": "Dental laboratory"}
PLACEHOLDERS = AUTO + tuple(STAFF_FIELDS)

_COMMON_END = (
    "\n\nI was given the chance to ask questions, and my questions were answered to my satisfaction. I understand that no result "
    "can be guaranteed. I understand that I may refuse or stop this treatment, and that the dentist will explain what may happen "
    "if I do.\n\n"
    "I confirm that I gave the dentist true and complete information about my medical history, medicines and allergies, and that "
    "I will tell the clinic of any change.\n\n"
    "I have read this form, or it was read and explained to me, and I understand it. I give my consent to the treatment described above."
)

DRAFTS = [
    ("general", "Consent for dental examination and treatment",
     "I, {patient}, {age}, consent to dental examination and treatment by {dentist} and the staff of Dental Haven {branch}.\n\n"
     "Treatment to be done: {procedure}\nTooth / teeth: {teeth}\n\n"
     "The dentist explained to me in words I understand:\n"
     "• what the treatment is and why it is recommended;\n"
     "• other options, including not treating;\n"
     "• the usual risks, such as soreness, swelling, sensitivity, bleeding, or a reaction to the anesthesia or medicines;\n"
     "• the expected cost, and that it may change if the treatment plan changes.\n\n"
     "I understand that X-rays, photos and impressions may be taken as part of my treatment and kept in my clinic record."
     + _COMMON_END),
    ("ortho", ORTHO_TITLE, ORTHO_BODY),
] + [(code, title, body) for code, title, body, _old in CLINIC_FORMS]


def staff_fields(body: str) -> list[tuple[str, str]]:
    """The blanks of a form the staff fill in on the signing screen, in the order they appear."""
    found = [(body.index("{" + k + "}"), k) for k in STAFF_FIELDS if "{" + k + "}" in body]
    return [(k, STAFF_FIELDS[k]) for _i, k in sorted(found)]


def fill(body: str, values: dict) -> str:
    """Put the patient's details into the form text. Unknown {words} are left as they are."""
    out = body
    for k in PLACEHOLDERS:
        out = out.replace("{" + k + "}", values.get(k) or "—")
    return out


def seed_drafts(conn, now: str) -> None:
    """Add the starting drafts once (not approved, so they can't be used until a dentist approves them). The braces form
    is switched to the clinic's own wording if it is still the untouched first draft."""
    if conn.scalar("SELECT COUNT(*) FROM consent_templates"):
        # The braces form still holding my first draft (edited or not, approved or not) gets the clinic's own wording, as long
        # as no patient has signed it yet. Its approval is cleared: a dentist approves the clinic's wording again.
        t = conn.one("SELECT * FROM consent_templates WHERE code = 'ortho'")
        if t and t["body"] != ORTHO_BODY and t["body"].startswith(OLD_ORTHO_START) \
                and not conn.scalar("SELECT COUNT(*) FROM patient_consents WHERE template_id = ?", (t["id"],)):
            conn.execute("UPDATE consent_templates SET title = ?, body = ?, approved_by = NULL, approved_at = NULL, updated_at = ? "
                         "WHERE id = ?", (ORTHO_TITLE, ORTHO_BODY, now, t["id"]))
        # The clinic's own forms (Nov 2026): replace my first drafts, add the new ones. A draft a patient already signed is
        # hidden (its signed copies stay as signed) and the clinic's form is added next to it.
        top = conn.scalar("SELECT MAX(sort_order) FROM consent_templates") or 0
        for code, title, body, old_start in CLINIC_FORMS:
            t = conn.one("SELECT * FROM consent_templates WHERE code = ?", (code,))
            if t is None:
                top += 1
                conn.insert("consent_templates", {"code": code, "title": title, "body": body, "sort_order": top, "active": 1, "created_at": now})
            elif old_start and t["body"].startswith(old_start):
                if conn.scalar("SELECT COUNT(*) FROM patient_consents WHERE template_id = ?", (t["id"],)):
                    conn.execute("UPDATE consent_templates SET active = 0, code = ? WHERE id = ?", (f"{code}-old-{t['id']}", t["id"]))
                    conn.insert("consent_templates", {"code": code, "title": title, "body": body, "sort_order": t["sort_order"],
                                                      "active": 1, "created_at": now})
                else:
                    conn.execute("UPDATE consent_templates SET title = ?, body = ?, approved_by = NULL, approved_at = NULL, updated_at = ? "
                                 "WHERE id = ?", (title, body, now, t["id"]))
        return
    for i, (code, title, body) in enumerate(DRAFTS):
        conn.insert("consent_templates", {"code": code, "title": title, "body": body, "sort_order": i, "active": 1, "created_at": now})

"""Patient consent forms: starting drafts and filling in the patient's details.

The drafts below are plain starting points only. They are NOT approved clinic or legal wording: an admin edits each form under
Administration → Consent forms, and a dentist approves it before patients can sign it. Editing a form clears its approval.
Blanks the staff fill in when the patient signs: {procedure} and {teeth}. Filled in automatically: {patient}, {age}, {date},
{branch}, {dentist}, {address}.
The orthodontic form uses the clinic's own wording (consent_ortho.py).
"""
from __future__ import annotations

from .consent_ortho import BODY as ORTHO_BODY, TITLE as ORTHO_TITLE

PLACEHOLDERS = ("patient", "age", "address", "date", "branch", "dentist", "procedure", "teeth")

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
    ("extraction", "Consent for tooth extraction / oral surgery",
     "I, {patient}, {age}, consent to the following procedure by {dentist} at Dental Haven {branch}:\n\n"
     "Procedure: {procedure}\nTooth / teeth: {teeth}\n\n"
     "The dentist explained to me the reason for the procedure, the other options (including not treating), and the possible risks "
     "and complications, which may include:\n"
     "• pain, swelling, bruising and limited mouth opening for some days;\n"
     "• bleeding, and infection or dry socket that may need more treatment;\n"
     "• injury to nearby teeth, fillings or crowns;\n"
     "• numbness or tingling of the lip, chin, tongue or gums, which is usually temporary but may rarely last longer;\n"
     "• for upper back teeth, an opening into the sinus that may need more treatment;\n"
     "• a broken root tip that may be left in place or need further surgery.\n\n"
     "I agree to follow the after-care instructions given to me and to return to the clinic or seek care if I have heavy bleeding, "
     "fever or swelling that gets worse."
     + _COMMON_END),
    ("ortho", ORTHO_TITLE, ORTHO_BODY),
    ("rct_prosth", "Consent for root canal, crown, bridge or denture",
     "I, {patient}, {age}, consent to the following treatment by {dentist} at Dental Haven {branch}:\n\n"
     "Treatment: {procedure}\nTooth / teeth: {teeth}\n\n"
     "Root canal treatment: the dentist explained that it aims to save the tooth, that it may need several visits, and that "
     "possible risks include pain or swelling, a broken instrument inside the canal, a crack or fracture of the tooth, and failure "
     "that may need re-treatment or removal of the tooth. A treated tooth may need a crown or other restoration to protect it.\n\n"
     "Crowns, bridges and dentures: the dentist explained that teeth may be shaped and impressions or scans taken, that the work is "
     "made by a dental laboratory, that a try-in or adjustments may be needed, that the color and shape are chosen together with "
     "me, and that a new denture can take time to get used to (speaking, eating, sore spots). The work may need repair or "
     "replacement over time. Once the laboratory has started the work, the laboratory fee may not be refundable."
     + _COMMON_END),
]


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
        t = conn.one("SELECT * FROM consent_templates WHERE code = 'ortho'")
        if t and t["updated_at"] is None and t["approved_at"] is None and t["body"] != ORTHO_BODY \
                and not conn.scalar("SELECT COUNT(*) FROM patient_consents WHERE template_id = ?", (t["id"],)):
            conn.execute("UPDATE consent_templates SET title = ?, body = ? WHERE id = ?", (ORTHO_TITLE, ORTHO_BODY, t["id"]))
        return
    for i, (code, title, body) in enumerate(DRAFTS):
        conn.insert("consent_templates", {"code": code, "title": title, "body": body, "sort_order": i, "active": 1, "created_at": now})

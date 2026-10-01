"""Starting evaluation forms. The clinic's Assistant Checklist (Yes/No), typed from the paper form.

Questions are stored on the form in the database, so the admin can edit them later. In the text format,
a line starting with '##' is a section heading and every other line is a question.
"""
from __future__ import annotations

ASSISTANT_CHECKLIST_TITLE = "Assistant Checklist"
ASSISTANT_CHECKLIST_DESCRIPTION = "Yes/No evaluation of a dental assistant's appearance, daily opening tasks, work during operations and closing routine."

ASSISTANT_CHECKLIST = """## A. Assistant personality
Naka-full uniform ba? (daily uniform, cream crocs, black socks, navy blue ribbon, nameplate)
Naka-make up ba?
Malinis ba ang kuko, hindi mahaba?
Palagi bang naka-smile si assistant?
Naka-pusod ba palagi si assistant? (naka-ribbon)
Kaaya-aya ba ang amoy?
## B. Assistant daily operation to-do list (morning)
Nakapagwalis ba sa cubicle 1, 2, 3, 4 at hallway, X-ray room?
Nakapag-mop ng buong lobby, operating area, X-ray room?
Napunasan ba ang mga salamin, buong dental chair?
Nakapag-refill ba ng mga nakalagay sa dental chair, kumpleto ba?
Nakapag-refill ba ng pang-disinfectant?
Nakapag-refill ba ng hand soap, alcohol sa lavatory?
Napalitan ba ang punasan ng kamay? (bimpo)
Napunasan ba ang pader ng operation area?
Nakapaglinis ba ng CR?
Nakapag-refill ba ng alcohol, tissue, air freshener sa CR?
Napunasan ba ang salamin, blinds, ilaw, pader sa CR?
Pinapatuyo ba ang CR, na-mop ba?
Napapagana ba ang up/down ng dental chair?
Nate-testing ba ang dental chair kung may hangin at tubig?
Na-oil ba ang high speed, nate-testing ba ng 3 seconds bago gamitin?
Na-check ba ang scaler, nalinis ba, gumagana?
Na-testing ba ang dental chair kung may hangin at tubig?
Na-check ba sa system ang mga patient na naka-appoint para sa gagawing procedure? (for preparing)
Kumpleto ba ang gamit na gagamitin sa procedure? (Look for the dental assistant manual to complete the equipment/tools: basic, oral prophylaxis, fixed bridge, sukat sa denture, braces install, crown, inlay, onlay, veneers, gingivectomy, whitening, bleaching, TMJ, implant)
Napainitan ba ang mga instrument ng 10 minutes?
Na-charge ba ang lahat ng mga tablet, laptop, oximeter, lightcure, periapical X-ray, pang-BP?
Na-open ba ang speaker para sa sound? (worship song)
Naka-open ba ang TV, naka-play ba ito na naaayon sa dental procedure?
May basic na ba na nakaayos, may nakalagay na ba sa dental chair?
## C. During operation
Naka-smile ba si assistant habang nagpapapasok ng patient?
May paggalang ba sa pagtawag ng patient (ma'am, sir, opo, po)?
Nasasabi ba ang spiel sa patient?
Bumabati ba ng "happiest day"?
Na-assist ba si patient mula pagpapapasok hanggang sa paghugas ng kamay at na-assign ba sa dental chair?
Napapa-gargle ba si patient ng 1 minute?
Na-prepare ba ang lahat ng procedure nang tama at kumpleto?
Binubuksan ba ang dental assistant manual pag mag-prepare ng gamit?
Naibibigay ang lahat ng kailangan ng dentista?
Kabisado ba kung saan nakalagay ang lahat ng mga gamit, mabilis ba?
Maagap ba sa pag-alis ng PPE sa patient?
Nai-input ba nang mabuti at kumpleto ang mga procedure sa system?
Detalyado ba sa paglalagay ng input sa system?
Nakakapag-suction ba nang tama at maayos sa patient?
Naka-set ba nang tama ang lightcure base sa procedure?
Nakapaglalagay ba ng bonding ayon sa dami?
Nakakapagpapasok ba agad ng patient once na bakante na ang dental chair?
Napapagamit ba ang stress ball at oximeter pag may binubunutan?
Nabibigyan ba ng icepack, frosty ang patient na nabunutan?
Naaalalayan ba si patient sa pagbibigay ng gamit?
Nalilinis ba agad ang dental chair once na wala na ang patient?
Maagap ba sa pag-prepare ng gamit kapag may biglaang procedure?
Nabibigyan ba ang batang patient ng coloring book, sticker book?
## D. Assistant closing routine
Napunasan ba at nalinis ang buong dental chair?
Nakapag-pasip-sip ba ng dental chair na may sabon at Zonrox?
Natanggal ba ang handpiece, 3-way?
Nalagyan ba ng oil ang handpiece bago itabi?
Niangat ba ang dental chair at napasingawan?
Nakapagwalis ba?
Nai-off ba ang mga TV, sounds?
Natanggal ba ang mga nakasaksak na TV, laptop, charger, speaker?
Nai-off ba ang aircon?
Natapon ba ang basura sa CR, operating area?
Nai-off ba ang compressor, napasingawan lahat?
Naiayos ba ang mga cast na nai-pour ngayong araw?
Napaalala ba sa dentist ang JO ngayon base sa case na ginawa ngayong araw? (fixed bridge, dentures, etc.)
Nakumpleto ba ang mga ipapadala na case? (JO, bite, picture)
Naibibigay ba sa receptionist ang case nang kumpleto?
Nasasabi ba sa receptionist kung rush ba ang case na ipapadala sa laboratory?
Naiwan ba nang maayos at malinis ang operation area?
"""


def parse_questions(text: str) -> list[dict]:
    """'## Heading' lines become sections; other non-empty lines become numbered questions."""
    items, n = [], 0
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("##"):
            items.append({"section": line.lstrip("#").strip()[:200]})
        else:
            n += 1
            items.append({"n": n, "q": line[:500]})
    return items


def to_text(items: list[dict]) -> str:
    return "\n".join(("## " + i["section"]) if "section" in i else i["q"] for i in items)

ASSISTANT_TARGET = "Dental Assistant"

RECEPTIONIST_CHECKLIST_TITLE = "Receptionist Checklist"
RECEPTIONIST_CHECKLIST_DESCRIPTION = "Yes/No evaluation of a receptionist: replying to inquiries, morning cleaning, assisting patients, closing and personality."
RECEPTIONIST_TARGET = "Receptionist"

RECEPTIONIST_CHECKLIST = """## A. Receptionist reply inquiries
Nakakapag-follow-up ba ng patients? (8:00 am, 8:45 am)
Nakakapag-reply ba ng 3–5 minutes?
Naaayon ba sa tanong ang sagot ni receptionist?
May paggalang ba ang pagsagot sa patient?
Malinaw bang naipapaliwanag ang bawat procedure sa patient?
Nakakapag-follow-up ba ng patients? (last week, last month, last 6 months)
Nare-reply-an ba ng tamang sagot ayon sa template? Look at the saved template. (question, answer, explanation, bridge, action)
Nai-input ba ang lahat ng information ni patient sa system nang tama?
Napapapirma ba si patient ng approval consent letter bago gawin ang procedure? (surgery, exo, etc.)
Aware ba si patient sa pagbabago ng schedule ni dentist, nasasabi kung bakit biglang wala si dentist?
Natatanong ba si patient kung may allergy sa gamot bago painumin ng gamot pang-surgery?
## B. Receptionist checklist: morning cleaning
Nakapagwalis ba, nakapag-mop ba?
Napunasan ba ang mga naka-display? (frame, toys, kids)
Nakakapag-refill ba ng biscuits, 3-in-1 coffee, sugar, creamer, candies?
Nalilinis ba ang sofa ng alcohol, napapagpag ba ang mga throw pillow?
Napunasan ba ang mga salamin?
Nafu-full charge ba ang mga massager, cellphone, laptop, speaker?
Nakakapagwalis ba sa harapan ng clinic?
Nakakapag-refill ba ng alcohol sa labas ng pinto?
Naka-open ba ang TV, naka-play ba nang mabuti ang video sa TV?
Naka-open ba ang sound? (worship song)
Napapanatili bang mabango sa reception?
## C. Assisting patients during operation
Napagbubuksan ba agad ang patient once nakapag-doorbell?
Pinatatanggal ba ang facemask, cap sa patient bago papasukin?
Naka-smile ba si receptionist kapag merong patient?
Bumabati ng "happiest day" sa patient?
Kumpleto ba ang PPE ng patient? (isolation gown, headcap)
Naalok ba si patient while waiting? (neck massager, coffee, biscuits, Zesto, candies)
Napapapasok ba agad ang patient sa operating area once na may bakanteng dental chair?
Naalok ba si patient ng WiFi?
Napapapirma ba si patient ng consent form/documents?
Nakukuhanan ba ng BP bago papasukin sa loob para bunutan?
Napapainom ba ang patient ng gamot bago i-surgery? (tranexamic, amoxicillin, celecoxib)
Nasasabi ba sa patient ang next schedule after magawan ng procedure? (ortho, fixed bridge, surgery)
Na-inform ba si patient sa schedule ni dentist na naghahandle sa kanya if may changes sa schedule?
Na-explain ba kay patient ang mga gamot, kung para saan ang pinaiinom na gamot at bakit pinaiinom?
Na-assist ba si patient sa pagbukas at pagsara ng pinto?
Kapag may naiwang gamit ang patient, naitatabi at naibabalik ba? (payong, tumbler, etc.)
## D. Receptionist closing
Na-follow-up ba ang lahat ng patient na naka-appoint para bukas?
Natawagan, na-text sa number, na-message sa Messenger si patient sa pag-follow-up?
Na-open ba ang signage ng 6 pm?
Nakapagwalis ba?
Napagpag ba ang mga throw pillow at naiayos?
Natanggal ba ang lahat ng saksakan? (laptop, thermos, charger, speaker, printer)
Nai-off ba ang lahat ng ilaw, chandelier, tagline, TV, sound?
Natapon ba ang basura?
Nakapag-out ba sa tamang oras?
Naiwan bang maayos, malinis ang lobby bago umuwi?
## E. Receptionist pleasing personality
Naka-full uniform? (uniform, ribbon, black flat shoes, nameplate)
Naka-make up ba?
Kaaya-aya ba ang amoy?
Malinis ba ang mga kuko sa kamay?
Laging nakangiti?
"""


ALIASES = {"dental assistant": {"assistant", "dental asst"}, "receptionist": {"dental receptionist"},
           "lab receptionist": {"dental laboratory receptionist", "laboratory receptionist"},
           "head receptionist": {"dental head receptionist"}, "dental staff consultant": {"staff consultant"},
           "dental technician (rpd)": {"rpd technician", "dental technician - rpd", "dental technician rpd"},
           "dental technician (fpd)": {"fpd technician", "dental technician - fpd", "dental technician fpd", "cad/cam technician",
                                       "cad cam technician"}}


def matches_target(position: str | None, targets: str) -> bool:
    """A staff member fits a form when their position is one of the form's target positions (comma-separated),
    ignoring upper/lower case; a few common spellings are accepted (e.g. 'Dental assistant'). No target = everyone."""
    wanted = [t.strip().lower() for t in (targets or "").split(",") if t.strip()]
    if not wanted:
        return True
    pos = " ".join((position or "").lower().split())
    return any(pos == w or pos in ALIASES.get(w, ()) for w in wanted)

HEAD_STAFF_TITLE = "Head Staff Evaluation"
HEAD_STAFF_DESCRIPTION = ("Yes/No evaluation of the Head Staff (lead assistant / head receptionist / practice manager), based on the clinic's "
                          "role clarity: daily operations, team leadership, inventory and equipment, compliance and safety, and patient experience.")
HEAD_STAFF_TARGET = "Head Staff"

HEAD_STAFF_CHECKLIST = """## A. Workflow & daily operations management
Is the day's schedule checked and organized before the first patient arrives?
Do patients move smoothly from the front desk to the dental chair and back, with little waiting?
Is dental chair downtime kept low (the next patient is ready when a chair is free)?
Are treatment rooms prepared, turned over and closed down properly between appointments?
Are same-day emergencies, cancellations and booking conflicts handled quickly, with a clear final decision?
Are schedule changes told right away to the dentist, the staff and the affected patients?
## B. Team leadership & staff supervision
Does the head staff train new assistants and front-desk staff on the system, clinical protocols and clinic workflow?
Are daily tasks (sterilization, inventory checks, patient follow-up calls) clearly assigned to each staff member?
Does the head staff check that the assigned tasks are actually done?
Does the head staff correct staff mistakes respectfully and on time?
Does the head staff give the dentist/owner accurate and fair feedback on staff performance?
Does the head staff set a good example (on time, in full uniform, follows clinic protocols)?
## C. Inventory & equipment control
Are clinical supplies, PPE and office materials checked regularly?
Are supplies reordered before they run out (no shortages during procedures)?
Is the inventory in the system kept up to date (stock counts and expiry dates)?
Is routine maintenance of major equipment (autoclave, X-ray, compressor, dental chairs) scheduled and done?
Are equipment problems reported and followed up until fixed?
Are orders with suppliers and the laboratory tracked, and are prices checked?
Do lab cases (crowns, bridges, dentures, appliances) come back on time, and are delays followed up?
## D. Compliance, safety & quality control
Are infection control and sterilization protocols followed by the whole team every day?
Are the sterilization/autoclave logs (including spore tests) complete and up to date?
Is medical waste segregated and disposed of properly, with records kept?
Are hazardous materials labeled, with safety information available to staff?
Are DOH and local health requirements followed (permits, posted notices, clinic standards)?
Are patient records and conversations kept private (Data Privacy Act), seen only by authorized staff?
## E. Patient experience & administrative support
Are patient complaints (billing, scheduling errors, service) handled calmly and resolved, or brought to the dentist when needed?
Are complaints and how they were resolved reported to the dentist/owner?
Does the head staff step in at the front desk when it is busy (complex check-ins, HMO verification)?
Can the head staff clearly explain treatment plans and payment options (installments, packages) to patients?
Do patients leave satisfied with the service?
"""

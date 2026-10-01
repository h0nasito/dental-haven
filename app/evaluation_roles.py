"""Performance evaluations built from Dental Haven's Role Clarity documents (one per position).

Each entry: title, target position (Employees → position), who answers it, description and the questions
('## ' lines are section headings). Answers are Yes / No (N/A allowed).
"""
from __future__ import annotations

# who answers: "dentists" (any account with "Answer staff evaluation forms"), "head_dentist" (an employee whose
# position is Head Dentist) or "management" (accounts that manage evaluations, e.g. the owner/super admin)
ANSWERED_BY = {"dentists": "Dentists", "head_dentist": "Head Dentist", "management": "Management (admin)"}

ROLE_FORMS = [
    {
        "title": "Dental Assistant Evaluation",
        "target": "Dental Assistant",
        "answered_by": "dentists",
        "description": "Performance evaluation based on the Role Clarity for Dental Assistant.",
        "questions": """## A. Chairside assistance
Are treatment rooms prepared before each patient?
Does the assistant hand instruments, suction and pass materials to the dentist efficiently during procedures?
Is the patient positioned properly and kept comfortable during treatment?
Are dental X-rays taken and prepared correctly when instructed and allowed?
## B. Instrument preparation & sterilization
Are instruments cleaned, disinfected and sterilized following clinic protocols, with no steps skipped?
Are instrument trays and dental materials set up correctly for each procedure?
Are infection control standards kept at all times?
## C. Equipment care & maintenance
Are handpieces and related equipment oiled and lubricated every day before the dentist uses them?
Are equipment issues or irregularities reported immediately?
Is all equipment kept clean, properly stored and ready for use?
## D. Patient care & communication
Are patients greeted and assisted before and after treatment?
Are post-treatment instructions given as directed by the dentist?
Are patient concerns handled politely and professionally?
## E. Clinic operations support
Are supplies, materials and equipment monitored and restocked, with low stock reported to the supervisor?
Are the treatment rooms, sterilization area and common areas kept clean?
Does the assistant help with documentation, treatment recording and updating patient files?
Are materials properly stored, labeled and organized in their designated areas?
Is the assigned pantry duty followed, with the pantry clean and supplies (water, cups, basic items) available?
Are materials used properly, without excessive or unnecessary use?
## F. Work behavior & conduct
Does the assistant follow clinic SOPs, rules and the Code of Conduct?
Does the assistant arrive on time and prepared for daily operations?
Is patient information kept confidential?
Does the assistant avoid doing any dental procedure without the dentist's instruction or supervision?
Does the assistant avoid diagnosing or giving medical advice to patients?
Does the assistant stay with the patient and never leave the treatment room unattended during a procedure?
Is the assistant professional and respectful toward patients and co-workers?
""",
    },
    {
        "title": "Dental Receptionist Evaluation",
        "target": "Receptionist",
        "answered_by": "dentists",
        "description": "Performance evaluation based on the Role Clarity for Dental Receptionist.",
        "questions": """## A. Front desk & patient coordination
Are patients, visitors and suppliers greeted courteously and professionally?
Are patient check-in and check-out handled properly?
Are calls answered and inquiries and appointment requests handled promptly?
Are appointments scheduled, confirmed, rescheduled and cancelled accurately?
Are patients informed of clinic policies, procedures and payment guidelines?
Are walk-in patients handled and coordinated with the dental staff?
## B. Patient records & documentation
Are patient records created and updated accurately?
Are patient information, consent forms and treatment records complete?
Are dental charts, forms and reports organized, legible, updated and securely stored?
Is patient data kept confidential at all times?
## C. Billing, payments & HMO coordination
Are treatment estimates, billing statements and receipts prepared correctly?
Are payments collected with a proper receipt issued for every payment?
Are daily sales reports coordinated with accounting and payments reconciled?
Are patients helped with HMO/insurance verification, claims and required documents?
Are services rendered and payments received recorded accurately?
## D. Communication & coordination
Are messages relayed accurately between patients, dentists and dental assistants?
Are patients informed of treatment schedules, delays or changes?
Is patient flow coordinated with the dental assistants and dentists?
Are patient concerns handled professionally and escalated when necessary?
## E. Administrative & clinic support
Are daily appointment lists and clinic reports prepared?
Are clinic supplies monitored and low stock reported to management?
Is the reception area clean, orderly and professional-looking?
## F. Work values & conduct
Is the receptionist punctual, without frequent excuses for lateness?
Are tasks finished within the given deadlines?
Is proper grooming kept (neat appearance, appropriate make-up)?
Is the approved spiel used consistently when talking to patients?
Are corrections accepted professionally and applied immediately?
Does the receptionist avoid leaving the reception area unattended without approval?
Does the receptionist avoid using a personal phone for non-work matters during duty?
Does the receptionist avoid committing to treatment schedules or fees without authorization?
Does the receptionist avoid gossip, arguments and giving unverified information?
""",
    },
    {
        "title": "Dental Laboratory Receptionist Evaluation",
        "target": "Lab Receptionist",
        "answered_by": "management",
        "description": "Performance evaluation based on the Role Clarity for Dental Laboratory Receptionist.",
        "questions": """## A. Front desk & client coordination
Are dentists, couriers and clients greeted and assisted courteously and professionally?
Are all laboratory cases received and documented with complete and accurate details?
Are job orders and acknowledgment receipts issued, with a tracking log of cases kept?
Are delivery and pickup schedules coordinated with affiliated clinics and branches?
Are inquiries about case status and due dates answered promptly?
## B. Documentation, billing, inventory & case management
Are all incoming and outgoing cases recorded accurately in the system or logbook?
Are required details checked before accepting a case (dentist, work type, shade, due date, instructions)?
Are cases completed and released on time, with deadlines met?
Are lab materials monitored, with management told when stock needs replenishing?
Does the lab receptionist help with lab billing, payment follow-ups and issuing receipts?
Are job orders, prescriptions, billing and financial records filed in order, complete, legible and updated daily?
## C. Communication & coordination
Are dentists' instructions relayed clearly and accurately to the laboratory technicians?
Are discrepancies, unclear prescriptions or delays reported to the Laboratory Manager?
Are case updates and changes communicated to dentists and clinics on time?
## D. Administrative & laboratory support
Are daily, weekly and monthly laboratory tracking reports prepared?
Are cases handled, labeled and organized safely (scanning, pouring, casting, plaster)?
Is the work area kept clean and sanitary?
Are materials used properly, avoiding waste?
## E. Work values & conduct
Is the lab receptionist on time, with consistent attendance?
Is proper grooming kept?
Are patient, dentist and laboratory information kept confidential?
Is no case received or released without proper documentation or acknowledgment?
Are cases handled carefully, with no mix-ups, swaps, damage or loss?
Does the lab receptionist avoid committing to deadlines or changes without consulting the Laboratory Manager?
Does the lab receptionist avoid using a personal phone for personal matters during work, especially with clients present?
Is the lab receptionist courteous, never arguing or raising their voice with clients, couriers or co-workers?
""",
    },
    {
        "title": "Head Receptionist Evaluation",
        "target": "Head Receptionist",
        "answered_by": "management",
        "description": "Performance evaluation based on the Role Clarity for Dental Head Receptionist.",
        "questions": """## A. Patient interaction
Are patients greeted and accommodated courteously on arrival?
Are bookings, cancellations and rescheduling handled correctly?
Are patients given the necessary instructions (preparation, follow-ups) as approved by Management?
Are basic inquiries answered and medical/dental concerns referred to the dentist or authorized staff?
Is patient privacy and confidentiality kept in all interactions?
## B. Administrative tasks
Are records of patient visits, daily logs and clinic schedules accurate?
Are receipts, records and reports prepared, organized and filed properly?
Are BIR filings and required documents submitted on time, in coordination with Management and accounting?
Are clinic forms, files and front desk supplies kept safe and monitored?
## C. Communication & coordination
Does the head receptionist act as the communication link between the branch receptionists and Management?
Are policies, memos and updates relayed to the branch receptionists?
Is scheduling and workflow coordinated smoothly with dentists, dental assistants and staff?
Are patient concerns, escalations and unusual incidents reported promptly to Management?
## D. Training, evaluation & mentorship
Are onboarding and training sessions held for new receptionists?
Is ongoing coaching given to improve the receptionists' performance and service?
Are reception procedures kept the same across branches?
Are newly hired receptionists evaluated during their probationary period?
Are reports on training outcomes, evaluations and recommendations submitted to Management?
## E. Boundaries & conduct
Does the head receptionist avoid giving medical, dental or treatment advice?
Are discounts, promos and financial transactions done only with prior authorization?
Are clinic policies, pricing and SOPs left unchanged unless approved?
Are disciplinary matters limited to recommendations, with final decisions left to Management?
""",
    },
    {
        "title": "Head Staff Evaluation",
        "target": "Head Staff",
        "answered_by": "dentists",
        "description": None,   # created earlier; keep its questions
        "questions": None,
    },
    {
        "title": "Dental Staff Consultant Evaluation",
        "target": "Dental Staff Consultant",
        "answered_by": "head_dentist",
        "description": "Performance evaluation based on the Role Clarity for Dental Staff Consultant.",
        "questions": """## A. Training & standardization
Are training sessions held on procedure protocols, sterilization and proper use of dental equipment?
Are new dental staff oriented on clinic standards, workflows and safety measures?
Is staff competency in assisting dentists evaluated, with extra training recommended when needed?
Are dental assistance procedures kept the same across branches?
## B. Assistance to the Head Dentist
Does the consultant support the Head Dentist in planning and carrying out clinic operations?
Does the consultant help the Head Dentist check that procedural standards are followed during treatments?
Are updates to protocols, equipment use and new techniques coordinated with the Head Dentist?
## C. Inventory & supplies management
Is the clinic's inventory of dental materials, tools and supplies monitored?
Are usage levels recorded and periodic stock checks done?
Are reports of lacking or low-stock items submitted to Management on time?
Are approved orders coordinated with suppliers or the designated staff?
Are clinic supplies stored and handled properly?
## D. Quality assurance & compliance
Is staff compliance with hygiene, sterilization and safety requirements monitored?
Are improvements in clinical workflow and staff–patient interaction recommended?
Are reports on staff performance, training outcomes and compliance given to the Head Dentist and Management?
## E. Coordination & conduct
Is the consultant available as a resource person for staff questions on standard procedures?
Are training schedules, inventory updates and improvements coordinated with the Head Dentist, Clinic Manager and Management?
Are hiring, termination and disciplinary matters limited to recommendations?
Are supplies purchased and expenses made only with Management approval?
Does the consultant avoid treating or diagnosing patients independently?
Is confidentiality of patient records, clinic operations and staff matters kept?
""",
    },
    {
        "title": "Associate Dentist Evaluation",
        "target": "Associate Dentist",
        "answered_by": "head_dentist",
        "description": "Performance evaluation based on the Role Clarity for Associate Dentist.",
        "questions": """## A. Patient care & clinical services
Are comprehensive oral examinations done with accurate diagnosis?
Are treatment plans appropriate to the clinical findings?
Are treatment options, risks, benefits and fees explained clearly to patients?
Are procedures done within the dentist's competence and licensure?
Are patient comfort, safety and infection control kept throughout treatment?
Are post-treatment instructions given and follow-up appointments scheduled?
Are cases that need referral recognized and coordinated with specialists?
## B. Clinical documentation
Are patient records completed immediately after every procedure?
Are diagnosis, treatment, prescriptions, informed consent and clinical notes documented accurately?
Are treatment plans documented before procedures start?
## C. Case management & laboratory coordination
Are laboratory prescriptions complete and accurate?
Do impressions, bite registrations and photos meet laboratory standards?
Is laboratory work reviewed before delivery to the patient?
Are laboratory concerns reported to management immediately?
## D. Infection control & equipment care
Are infection prevention and sterilization protocols strictly followed?
Are instruments and equipment inspected before use, with defects reported?
Is the treatment area clean and organized before and after every patient?
## E. Patient communication & service excellence
Is the dentist courteous, respectful and compassionate with patients?
Are patient concerns handled professionally?
Does the dentist coordinate well with receptionists, dental assistants and laboratory staff?
Does the dentist support patient retention and satisfaction (follow-ups, recalls)?
## F. Professional development & conduct
Are required meetings, trainings, calibration sessions and case discussions attended?
Are coaching, evaluations and feedback accepted professionally?
Does the dentist report on time and get ready before the first scheduled patient?
Are patient schedules respected with minimal delays?
Are treatment plans presented honestly, without unnecessary procedures or guaranteed outcomes?
Are commitments made only within approved clinic policies and fee schedules?
Are clinic materials and equipment used responsibly, without waste?
""",
    },
    {
        "title": "Head Dentist Evaluation",
        "target": "Head Dentist",
        "answered_by": "management",
        "description": "Performance evaluation based on the Role Clarity for Head Dentist.",
        "questions": """## A. Clinical leadership & patient care
Does the head dentist keep a patient caseload and perform complex procedures to a high standard?
Do diagnoses, treatment plans and charts meet legal, ethical and clinical standards?
Does the head dentist act as the final authority on complex cases and referrals?
Are escalated patient complaints and clinical disputes resolved well?
## B. Team mentorship & staff management
Are associate dentists, assistants and front-desk staff supervised clinically?
Are regular case reviews held, with constructive feedback and mentoring of junior staff?
Are periodic performance reviews, goal-setting and disciplinary actions led or supported?
Is the orientation of new dental staff led, and continuing education coordinated?
## C. Practice operations & compliance
Does the clinic comply with DOH and local health regulations, the Data Privacy Act and PRC/PDA guidelines?
Are safety, sterilization and hazard procedures overseen?
Are chart reviews and audits done to reduce documentation and clinical errors?
Does the head dentist help evaluate and recommend dental technology, tools and materials?
## D. Administrative & strategic partnership
Are clinical policies, SOPs and treatment protocols designed, updated and implemented?
Are budgets, supply costs and productivity goals monitored with management?
Does the head dentist serve as the main link between the clinical floor and the owners/management?
""",
    },
    {
        "title": "Finance Officer Evaluation",
        "target": "Finance Officer",
        "answered_by": "management",
        "description": "Performance evaluation based on the Role Clarity for Finance Officer.",
        "questions": """## A. Daily financial recording & monitoring
Are daily transactions recorded accurately and supported by proper documents?
Are revenue, collections, expenses, receivables, payables and bank records kept up to date?
Are branch financial reports reviewed for completeness and accuracy?
Are unusual or inconsistent transactions flagged?
## B. Cash handling & deposits
Are daily collections and cash balances of all branches monitored?
Are collections deposited according to company procedures?
Are cash collections reconciled with daily reports, receipts and deposit slips?
Are shortages and discrepancies reported to Management immediately?
## C. Billing & accounts receivable
Are accounts receivable records accurate, with outstanding balances monitored?
Are aging reports prepared and outstanding balances followed up with branch personnel?
Is HMO billing and collection documentation coordinated?
## D. Payroll & expenses
Is payroll information properly documented and authorized before processing, in coordination with HR?
Is employee compensation information kept confidential?
Are expenses supported by receipts, invoices and approvals?
Are recurring and unusual expenses monitored, with cost-control opportunities identified?
## E. Reconciliation & reporting
Are cash, bank, receivables and payables reconciled regularly?
Are monthly, quarterly and annual reports submitted on time?
Is budget vs. actual monitored, with significant variances explained?
## F. Inventory, controls & improvement
Are purchasing and material consumption reviewed against needs and budget?
Are financial controls followed, with weaknesses reported to Management?
Are financial records organized and audit-ready?
Are improvements to finance procedures recommended and implemented when approved?
## G. Training of new receptionists
Is the 5-day Finance training for newly hired receptionists conducted using the Finance Training Manual?
Is the final competency evaluation done and documented?
Are new receptionists kept from finance tasks until trained and authorized?
## H. Integrity & conduct
Are errors and discrepancies reported immediately, never concealed?
Are major financial commitments made only with Management approval?
""",
    },
    {
        "title": "Digital Content Associate Evaluation",
        "target": "Digital Content Associate",
        "answered_by": "management",
        "description": "Performance evaluation based on the Role Clarity for Digital Content Associate.",
        "questions": """## A. Content creation
Are photos and short videos/reels captured in the clinic as instructed?
Is content edited in line with clinic branding and standards?
Are creative content ideas proposed for approval?
## B. Content management
Is the target of six (6) approved posts per week met?
Is the approved posting schedule followed, with approved captions and hashtags?
Is only approved content posted?
## C. Community engagement
Are comments and messages on official posts monitored?
Are replies made only with the pre-approved reply scripts?
Are pricing, dental questions, appointment requests and complaints passed to the Receptionist or Head Staff?
## D. Collaboration & reporting
Are approvals and campaign directions coordinated with the Marketing Coordinator/Manager?
Are post performance and engagement reports submitted when required?
Are meetings and check-ins attended?
## E. Boundaries & confidentiality
Does the associate avoid giving treatment details, quotations or prices?
Does the associate avoid running paid ads or boosting without direction?
Are account passwords never changed or shared without written authorization?
Are no public statements or announcements released on behalf of the clinic?
Is patient confidentiality and privacy protected in all content?
""",
    },
    {
        "title": "Dental Technician (RPD) Evaluation",
        "target": "Dental Technician (RPD)",
        "answered_by": "dentists",
        "version": 2,
        "description": ("Evaluated by the dentist from the results of the cases received from this technician (Removable Appliances / "
                        "Orthodontic & Prosthetic department: dentures, non-metal RPDs, retainers, clear aligners, night guards). "
                        "Answer about the cases you received in the period; write the case numbers in Remarks."),
        "questions": """## A. Dentures & non-metal partial dentures (acrylic / flexible)
Do dentures and RPDs seat well and fit the tissues without sore spots or rocking?
Is retention right: not too tight, not loose?
Is the bite (occlusion) correct, with little adjustment needed at the chair?
Are the teeth set up well for looks and speech (shade, size, midline, smile line)?
Are the denture bases and borders smooth, well contoured and highly polished?
Are repairs, added teeth and relines returned correct and on time?
## B. Orthodontic retainers & appliances
Do retainers and appliances seat on the teeth without needing adjustment?
Are wires and clasps (Adams, C-clasps, labial bows) neatly adapted and holding well?
Do expansion appliances and active plates work as prescribed (jackscrew placement and function)?
Is the acrylic neatly trimmed and smooth, comfortable for the patient?
## C. Clear aligners & thermoformed appliances
Do clear aligners and trays fit the teeth snugly at delivery?
Are the edges trimmed smoothly along the gum line, without irritating the gums?
Are bleaching trays and sports guards thick enough and comfortable?
## D. Occlusal splints & night guards
Do night guards and splints seat passively and comfortably?
Is the bite on the splint balanced, with little adjustment needed?
Is the splint thickness right (correct vertical dimension) and the surface polished?
## E. Accuracy, finish & delivery
Does each case match the prescription (design, material, shade and instructions)?
Are the appliances free of voids, bubbles, rough spots or cracks?
Are cases delivered on time, including rush and emergency cases?
Are remakes rare for this technician's cases?
Are questions about unclear prescriptions raised before the work is done, not after?
""",
    },
    {
        "title": "Dental Technician (FPD / CAD-CAM) Evaluation",
        "target": "Dental Technician (FPD)",
        "answered_by": "dentists",
        "version": 1,
        "description": ("Evaluated by the dentist from the results of the cases received from this technician (Fixed Prosthodontics: "
                        "Exocad design, CAD/CAM milling and printing, crowns, bridges, veneers, inlays/onlays and implant restorations). "
                        "Answer about the cases you received in the period; write the case numbers in Remarks."),
        "questions": """## A. Fit & margins
Do crowns and bridges seat fully on the preparation without binding?
Are the margins sealed and accurate, with no open or overextended margins?
Is the internal fit right, with little adjustment needed at the chair?
Do implant crowns, custom abutments and screw-retained restorations fit passively?
## B. Contacts & occlusion
Are the contacts with neighboring teeth correct (not open, not too tight)?
Is the bite correct, with little occlusal adjustment needed?
Are bridge connectors strong and pontics designed to be easy to clean?
## C. Aesthetics
Does the shade match the prescription and the neighboring teeth?
Do the shape, contour and surface texture look natural?
Are staining, glazing and layering lifelike (translucency, character)?
Are contact areas and biting surfaces highly polished?
## D. Material & finish
Is the correct material used as prescribed (zirconia, e.max, PMMA, etc.)?
Are restorations free of chips, cracks, porosity or leftover milling marks?
Are temporary PMMA crowns, mock-ups and printed models accurate and usable?
## E. Accuracy, delivery & communication
Does each case match the prescription and the digital design that was approved?
Are cases delivered on time, including rush cases?
Are remakes and returns rare for this technician's cases?
Are problems with scans or impressions reported before the work is done?
Is the technician easy to coordinate with on design questions and adjustments?
""",
    },
]

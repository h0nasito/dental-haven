"""Dental Haven's own consent forms and patient instructions (wording supplied by the clinic, Nov 2026), kept word for word.

Blanks of the paper forms are filled in when the patient signs: from the record ({patient}, {age}, {address}, {dentist}) or
typed by the staff on the signing screen ({teeth}, {site}, {material}, {anesthesia}, {other_risks}, {fee}, {lab}). The
signature lines (patient / guardian, relationship, dentist, date) become the signature block of the signed copy.
"""

AGREE = ("I, {patient}, {age}, residing at {address}, have read all the terms and conditions above. I fully understand them "
         "and agree to conform to all conditions in this contract.")

ENDO = """TREATMENT TO BE DONE: I understand and consent to have endodontic (root canal) treatment performed by the dentist after the procedure, risks, benefits, alternatives, and associated costs have been fully explained to me. This procedure involves removing diseased, inflamed, or infected pulp tissue from inside the tooth, cleaning and shaping the root canals, and sealing the canal space, and may include diagnostic radiographs (X-rays) and local anesthesia.

RADIOGRAPHS (X-RAYS): I understand that X-rays or radiographs are necessary before, during, and after treatment as a diagnostic and procedural aid to evaluate root anatomy, canal length, and healing. I acknowledge that diagnostic imaging does not provide a 100% guarantee of all underlying conditions, as dental treatments are subject to unpredictable findings or complications that may require additions or adjustments to the treatment plan, along with my responsibility to pay all agreed costs.

DRUGS, MEDICATIONS & LOCAL ANESTHESIA: I understand that local anesthetics, analgesics, antibiotics, intracanal medicaments, or other medications used during or after treatment can cause side effects or allergic reactions such as redness, swelling of tissues, pain, itching, vomiting, prolonged numbness, or—in rare cases—anaphylactic shock. I confirm that I have disclosed all known allergies, medical conditions, and current medications.

ENDODONTICS (ROOT CANAL THERAPY) RISKS & LIMITATIONS:
• No Guarantee of Tooth Retention: I understand there is no guarantee that root canal treatment will save a tooth, and that a tooth may still require further endodontic surgery (apicoectomy) or extraction despite all efforts to save it.
• Post-Operative Discomfort & Flare-Ups: Temporary soreness, sensitivity to biting, swelling, or infection flare-ups may occur during or after treatment and may require medication or additional visits.
• Overextension / Underfilling of Material: Occasionally, root canal filling material or irrigants may extend beyond the root tip (apex) or be limited by canal anatomy; overextension does not necessarily affect the success of the treatment, though persistent symptoms may require follow-up care.
• Instrument Separation & Anatomical Complications: Endodontic files and drills are very fine instruments, and stresses inherent in their manufacture—as well as curved canals, blockages, or calcifications present in teeth—can cause instruments to separate (break) during use, or result in canal perforation or missed canals.
• Specialist Referral: I understand that referral to an endodontist (root canal specialist) for complex anatomy, instrument separation, retreatment, or additional procedures may become necessary following or during treatment, and I agree that I am responsible for any additional costs for treatment performed by the endodontist.
• Final Restoration Requirement: I understand that after root canal therapy is completed, the tooth becomes more brittle and requires a permanent restoration (such as a core buildup and dental crown) within the recommended timeframe to prevent tooth fracture or reinfection, which involves a separate fee.

ALTERNATIVES & NO GUARANTEE: I understand the alternatives to root canal treatment—primarily tooth extraction (with or without replacement options such as a dental implant, bridge, or partial denture)—and the risks of leaving the tooth untreated (such as worsening pain, spreading infection/abscess, bone loss, or tooth loss). I understand that dentistry is not an exact science and that no dentist can guarantee accurate or permanent results in all cases.

Payment Terms and Conditions
• Full Payment Upon Completion: Once treatment is completed, full payment of the total balance is required immediately upon completion of the procedure.
• Multi-Visit Endodontic Treatment (If Applicable): If root canal therapy requires multiple visits, a required down payment/initial installment is due on the first visit, with the remaining balance due in full upon final completion of the root canal obturation/procedure.
• Separate Fees for Additional Procedures: Quoted endodontic fees cover the root canal procedure only. Diagnostic X-rays, medications, emergency visits, specialist referrals, and the final permanent restoration (such as a core buildup, post, or dental crown) are billed separately unless explicitly itemized in a written treatment estimate.
• Unforeseen Treatment Modifications: Should clinical findings during the procedure require necessary modifications or additional treatments, any resulting adjustments in cost will be discussed with me and remain my financial responsibility.
• Insurance / HMO & Patient Responsibility: Regardless of any dental insurance or HMO coverage I may have, I am directly responsible for the timely payment of all agreed dental fees, co-payments, deductibles, or uncovered balances.
• Delinquent Accounts & Non-Refundable Services: Payments made for completed clinical services and materials used are non-refundable. In the event of unpaid or overdue balances, I agree to pay any collection fees, attorney's fees, or court costs incurred by the clinic to satisfy unpaid obligations.

Patient Authorization and Financial Acknowledgment
I hereby authorize the attending dentist and dental auxiliaries to proceed with the endodontic treatment as explained to me. I understand that treatment is subject to modification depending on undiagnosable circumstances that may arise during the procedure. I have read, understood, and agreed to the Payment Terms and Conditions stated above. All aspects of treatment have been properly explained to me, and I consent to undergo this dental treatment of my own free will, with full trust and confidence in my attending dentist.

PATIENT NAME: {patient}
TOOTH NUMBER(S): {teeth}"""

RESTORATION = """TREATMENT TO BE DONE: I understand and consent to have tooth restoration (dental filling) treatment performed by the dentist after the procedure, risks, benefits, alternatives, and associated costs have been fully explained to me. This may include diagnostic radiographs (X-rays), local anesthesia, removal of decayed or compromised tooth structure, and placement of restorative material.

RADIOGRAPHS (X-RAYS): I understand that an X-ray or radiograph may be necessary as a diagnostic aid to accurately assess the extent of tooth decay or fracture and to establish a proper treatment plan. I acknowledge that diagnostic imaging does not provide a 100% guarantee of all underlying conditions, as dental treatments may involve unpredictable findings once treatment begins that could require necessary additions or adjustments to the treatment plan, along with my responsibility to pay all agreed costs.

DRUGS, MEDICATIONS & LOCAL ANESTHESIA: I understand that local anesthetics, analgesics, antibiotics, or other medications used during or after treatment can cause side effects or allergic reactions such as redness, swelling of tissues, pain, itching, vomiting, prolonged numbness, or—in rare cases—anaphylactic shock. I confirm that I have disclosed all known allergies, medical conditions, and current medications.

Potential Risks and Complications
While tooth restorations are routine and generally safe, no dental procedure is completely free of risk. Possible risks include:
• Post-Operative Sensitivity or Discomfort: Temporary sensitivity to hot, cold, sweet, or biting pressure is common for a few days to several weeks. Occasionally, deeper decay may cause lingering sensitivity or pulpitis (nerve inflammation) that could later require endodontic (root canal) treatment or extraction.
• Bite / Occlusal Adjustment Needs: The restoration may initially feel slightly high or uneven once local anesthesia wears off and may require a quick adjustment.
• Wear, Chipping, Fracture, or Dislodgement: Restorative materials can wear down, chip, crack, stain over time, or debond—especially under heavy biting forces, teeth grinding/clenching (bruxism), or biting hard objects.
• Recurrent Decay or Gum Irritation: New decay can form around restoration margins if oral hygiene or diet factors persist; temporary gum irritation or bleeding can occur near the gumline.
• Allergic Reaction or Local Anesthesia Risks: Rare allergic reactions to restorative materials or local anesthetics may occur, along with standard anesthesia risks (e.g., temporary numbness beyond expected duration, lip/tongue biting while numb, soreness at the injection site, rare bruising or nerve irritation).
• Shade & Appearance: I understand that while tooth-colored restorative materials are matched closely to natural tooth shade, an exact color match cannot always be guaranteed.

RESTORATION WARRANTY & LIMITATIONS (3-MONTH COVERAGE):
• 3-Month Limited Warranty: The clinic provides a three (3)-month limited warranty from the date of placement covering replacement or repair of the restoration at no additional professional fee if it fractures, chips, or dislodges under normal chewing forces.
• Warranty Exclusions: This warranty does not cover breakage, dislodgement, or failure resulting from:
   o Biting on hard objects (e.g., ice, bones, hard nuts, shells, pens, or fingernails) or trauma/accidents.
   o Unmanaged teeth grinding or clenching (bruxism) when a recommended nightguard is not used.
   o New or recurrent tooth decay caused by poor oral hygiene, high-sugar/acidic diet, or missed follow-up visits.
   o Underlying tooth structure fracture, nerve inflammation requiring root canal therapy, or cases where a more extensive restoration (such as a dental crown/onlay) was advised but declined by the patient.
• Post-Warranty Period: Any repair, replacement, or further treatment required after three (3) months from the date of placement will be billed as a new procedure at standard clinic rates.

ALTERNATIVES & NO GUARANTEE: I understand the alternatives to tooth restoration (such as a dental crown/onlay, root canal therapy, extraction, or monitoring where clinically appropriate) and the risks of leaving decay untreated. I understand that dentistry is not an exact science and that no dentist can guarantee exact or permanent results in all cases.

Patient Authorization and Financial Acknowledgment
I hereby authorize the attending dentist and dental auxiliaries to proceed with the tooth restoration treatment as explained to me. I understand that treatment is subject to modification depending on undiagnosable circumstances that may arise during the procedure. Regardless of any dental insurance coverage I may have, I accept full responsibility for payment of all agreed dental fees (as well as any collection fees, attorney's fees, or court costs incurred to satisfy unpaid obligations). All aspects of treatment have been properly explained to me, and I consent to undergo this dental treatment of my own free will, with full trust and confidence in my attending dentist.

PATIENT NAME: {patient}
TOOTH NUMBER(S) / RESTORATIVE MATERIAL: {teeth} / {material}"""

EXTRACTION = """Before you give your permission for the removal of teeth, removal of impacted teeth or other minor and complex oral surgery and dental treatment, as well as the administration of certain anesthetics, you should understand that there are certain associated risks.

• Procedure & Tooth/Site Involved: We will be performing extraction / oral surgery on tooth/teeth #(s) {teeth} (and/or surgical site: {site}).
• Medical Disclosure & Pre-Procedure Safety: The patient/guardian confirms that all relevant medical history, current medications, drug allergies, bleeding tendencies, pregnancy/breastfeeding status, and systemic conditions (such as hypertension, diabetes, or heart conditions) have been disclosed truthfully prior to the procedure. Failure to disclose accurate medical information may increase surgical risks and release the clinic/dentist from liability for complications arising therefrom.

Common Risks & Potential Complications
Common risks include, but are not limited to:
1. Drug Reactions and Side Effects: Allergic reactions, nausea, rashes, or side effects from prescribed or administered medications (including antibiotics, analgesics, or anti-inflammatory drugs).
2. Damage to Adjacent Teeth or Fillings: Accidental chipping, loosening, or dislodgement of neighboring teeth, crowns, bridges, or existing dental restorations, especially when teeth are closely crowded, heavily restored, or have weakened enamel/roots.
3. Postoperative Infection: Bacterial infection at the extraction or surgical site requiring additional medication, drainage, or follow-up care—particularly if post-operative hygiene and instructions are not followed.
4. Postoperative Bleeding: Prolonged or recurrent bleeding that may require additional treatment, packing, sutures, or medical/surgical management.
5. Root Fragment Retention: Possibility of a small fragment of root or bone being left in the jaw when removal poses a higher risk of nerve or sinus injury than retention, or requiring surgical retrieval/extensive surgery.
6. Delayed Healing (Dry Socket / Alveolar Osteitis): Premature loss of the blood clot resulting in localized pain and delayed healing, necessitating frequent postoperative dressing/care and follow-up visits.
7. Sinus Involvement: Possible communication with or involvement of the maxillary sinus during removal of upper posterior teeth (molars/premolars), which may require additional treatment, sinus precautions, or surgical repair at a later date.
8. Nerve Involvement & Paresthesia: Possible involvement or irritation of nearby nerves—including, but not limited to, the inferior alveolar or lingual nerve during removal of lower molars/wisdom teeth—resulting in temporary or possibly permanent tingling, altered sensation, pain, or numbness of the lower lip, chin, gums, or tongue on the operated side.
9. IV / Injection Site Bruising or Phlebitis: Bruising, hematoma, or vein inflammation/irritation at the site of administration of intravenous or injectable medications, which may require further care.
10. Jaw Fracture: In rare circumstances (such as deeply impacted teeth, thin/compromised bone, or pathological conditions), breakage or fracture of the jaw.
11. Anesthesia-Related Effects: As a result of the injection or use of anesthesia, there may be swelling, trismus (jaw muscle stiffness/tenderness), or resultant numbness of the tongue, lips, teeth, jaws, and/or facial tissues that is usually temporary. In rare instances, such numbness or nerve irritation may be prolonged or permanent.
12. Other Risks: {other_risks}

Anesthesia Consent
I was given the option of different anesthetic techniques, and I consent for the following anesthetics to be used:
• Local anesthesia (injection)
• Local anesthesia (injection) with intravenous sedation (where applicable/offered)
• Local anesthesia (injection) with oral premedication (pills before treatment) / General anesthesia or hospital operating room (where applicable/referred)
Anesthesia chosen: {anesthesia}

Patient Responsibilities, Post-Op Compliance, & Limitation of Liability
• Post-Operative Care & Follow-Up: I agree to follow all written and verbal post-operative instructions (including biting on gauze, avoiding spitting/straws/smoking/rinsing vigorously during the initial healing period, taking prescribed medications as directed, and attending scheduled follow-up or suture-removal visits).
• No Guarantee & Clinic Safeguard: I am aware that the practice of dentistry and oral surgery is an inexact science, that no guarantees can be provided and none have been made to me regarding healing speed or exact outcomes, and that Dental Haven and the attending dentist are not liable for complications, delayed healing, infection, or bleeding resulting from undisclosed medical conditions, non-compliance with post-operative care, or missed follow-up appointments.

Acknowledgment & Signatures
I, {patient}, {age}, acknowledge that I have completely read the foregoing, have discussed any questions or concerns that I may have regarding my proposed surgery/dental treatment, and have been given satisfactory answers. I am aware that the practice of dentistry is an inexact science and that no guarantees can be provided and none have been made to me."""

FIXED_TRYIN = """Dear Patient,
Your custom Fixed Prosthesis is currently at the try-in stage prior to final laboratory glazing and processing. Before we proceed with final processing and cementation, please carefully inspect the prosthesis in your mouth with a mirror and confirm your approval of the following details. Keep in mind that while reasonable modifications can still be made during this try-in appointment, changes will no longer be possible once the prosthesis is sent back for final processing.

To ensure both you and your dentist are completely satisfied with your fixed bridge, please review and confirm the following:
1. Shade, Shape, & Size: I am satisfied with the color (shade), contour, and size of the teeth in relation to my natural teeth.
2. Tooth Display When Smiling: I am satisfied with the visibility and position of the teeth when I smile (neither excessive nor insufficient tooth display).
3. Alignment & Angulation: I am satisfied with the alignment, inclination, and symmetry of the teeth in relation to one another.
4. Lip & Facial Support: I am satisfied that my lips and facial profile look natural (not overly full, protruding, or sunken).
5. Dental Midline: I am satisfied with the alignment of the dental midline (center of the front teeth).
6. Initial Fit & Bite (Occlusion): The bridge feels comfortable, with even contact on both sides of my mouth and no premature high spots.
7. Speech & Phonetics: When I speak, the teeth do not click together, interfere with my tongue, or cause noticeable speech obstruction.
8. Acceptance of Anatomical Limitations: I understand that every patient's oral anatomy, bone support, and bite are unique, and that certain aesthetic or functional compromises may be unavoidable due to natural anatomical limitations.

Clinic Terms & Patient Acknowledgment
• Final Processing Lock & Re-Fabrication Fee: Once this wax/trial try-in is signed and released to the laboratory for final processing or glazing, all approved shade, contour, size, midline, and bite relationships are final. No modifications will be accommodated under the original try-in approval once final processing begins; any requested alteration or remake thereafter—or after final cementation—will require paying the applicable laboratory charges and the full total remake/re-fabrication fee of ₱{fee}.
• Temporary Restoration & Tooth Sensitivity During Processing: While the fixed prosthesis is undergoing laboratory processing, temporary crowns/bridges or provisional restorations protect prepared teeth. Mild thermal sensitivity, temporary looseness, or minor gum irritation may occur; patients must contact the clinic promptly if a temporary crown/bridge comes loose or breaks rather than leaving prepared teeth exposed or attempting self-re-cementation.
• Unsettled Balances Prior to Processing or Cementation: Dental Haven reserves the right to hold laboratory processing, final finishing, or final cementation/delivery of the fixed prosthesis until all agreed down payments, professional fees, and past-due balances are settled in full.
• Delayed Return After Try-In or During Provisional Phase: If the patient delays returning for scheduled try-in, post-processing adjustments, or final cementation without prior valid notice, Dental Haven is not liable for shifting of adjacent/opposing teeth, gum/soft-tissue changes, or fit discrepancies that may develop. Additional clinical re-evaluation, re-impression, or laboratory fees may apply if prolonged delay compromises the fit.
• Abutment Tooth Prognosis & Underlying Oral Condition: Approval of the try-in applies to the prosthetic design and trial fit and does not guarantee the long-term prognosis of underlying or supporting (abutment) teeth. Future tooth decay, pulpal/nerve complications, periodontal issues, or root/bone changes arising from oral hygiene lapses, heavy bite forces, or natural biological changes are outside the clinic's liability.
• Shade, Material, & Light Variation: While every effort is made to match the approved try-in, shade guide, or reference photos, subtle variations in translucency, surface luster, or shade appearance may occur due to ceramic/zirconia/metal processing, glazing, and lighting conditions.

""" + AGREE + """

Dental Laboratory: {lab}"""

FIXED_INSTALL = """Dear Patient,
Your custom Fixed Prosthesis is completed and ready for final installation (cementation). Prior to permanent cementation, please confirm your final acceptance of the prosthesis and acknowledge the clinical terms below:
1. Final Aesthetic & Functional Approval: I have examined the finished fixed bridge in my mouth and am fully satisfied with its shade, shape, size, midline, lip support, comfort, bite, and speech clarity.
2. Irreversibility After Permanent Cementation: I understand that once the fixed bridge is permanently cemented, modifications to shade, shape, or alignment are no longer possible, and any requested changes or remakes thereafter will incur full additional laboratory and clinical fees.
3. Post-Insertion Sensitivity & Bite Adjustment: I understand that mild, temporary sensitivity to hot/cold temperatures or minor bite awareness may occur for a few days following cementation. If my bite feels high or uneven after the anesthesia wears off, I must return promptly to the clinic for occlusal adjustment to prevent porcelain fracture or abutment tooth pain.
4. Oral Hygiene & Maintenance Responsibility: I understand that the long-term success of a fixed bridge depends on proper oral hygiene—including brushing, flossing underneath the pontic (using a floss threader, superfloss, or water flosser), and attending regular dental checkups and cleanings every six (6) months.
5. Risks & Limitations of Liability: I understand that Dental Haven and the attending dentist are not liable for bridge failure, porcelain chipping/fracture, recurrent decay on supporting (abutment) teeth, or gum disease resulting from poor oral hygiene, missed recall visits, chewing excessively hard objects (e.g., ice, bones, hard nuts), teeth grinding/clenching (bruxism), or physical trauma.

Clinic Terms & Patient Acknowledgment
• Post-Cementation Finality & Remake / Re-Fabrication Fee: Once the fixed crown, bridge, or restoration is permanently cemented, all approved shade, contour, size, midline, and bite relationships are considered final. Any post-cementation request for alterations, adjustments, or a remake—or any remake required due to patient preference or non-compliance—shall be subject to applicable clinical/laboratory charges and the full total remake/re-fabrication fee of ₱{fee}.
• Temporary Post-Cementation Sensitivity & Bite Check: Mild, temporary sensitivity to hot, cold, sweet, or biting pressure may occur for a few days following final cementation as the tooth and periodontal tissues adjust. If the bite feels high, uneven, or uncomfortable once local anesthesia wears off, the patient must return promptly to the clinic for occlusal adjustment to help prevent porcelain chipping/fracture, debonding, or abutment tooth discomfort.
• Settled Balances Prior to Final Cementation: Dental Haven reserves the right to withhold final cementation or release of the fixed prosthesis until all agreed down payments, professional/laboratory fees, and past-due balances are settled in full.
• Hygiene Under Pontics & Margins (Long-Term Care): The longevity of a fixed prosthesis depends heavily on daily plaque control and routine professional maintenance. Patients must brush thoroughly, clean beneath pontics and around crown margins daily (using floss threaders, superfloss, interdental brushes, or water flossers as advised), and attend regular dental checkups and professional cleanings every six (6) months.
• Exclusions from Liability (Hard Forces, Bruxism, & Decay): Dental Haven and the attending dentist are not liable for chipping, cracking, or fracture of ceramic/zirconia/composite surfaces, loss of cementation/debonding, recurrent decay on abutment or adjacent teeth, or periodontal breakdown resulting from chewing hard or sticky items (such as ice, bones, hard nuts, or candies), nighttime clenching or teeth grinding (bruxism) without a protective nightguard, missed recall visits, or inadequate oral hygiene.
• No Guarantee of Lifespan or Identical Shade: While every clinical and laboratory effort is made for a precise fit and natural appearance, no prosthesis lasts indefinitely or matches natural teeth in every lighting condition, and long-term durability varies based on individual oral health, bite forces, and biological factors.

""" + AGREE + """

Dental Laboratory: {lab}"""

DENTURE_TRYIN = """Dear Patient,
Your custom complete or partial denture is currently at the wax try-in stage prior to final processing and delivery. Because the denture teeth are temporarily set in wax, reasonable adjustments to tooth arrangement, shade, or bite can still be evaluated during this appointment. Once the wax try-in is approved and sent for processing, further changes will generally no longer be possible without additional fees or a remake.

To ensure mutual agreement before final processing, please inspect the wax try-in in your mouth and confirm your approval of each item below:
1. Shade, Shape, & Size: I approve the color (shade), contour, and size of the denture teeth.
2. Smile Line & Tooth Display: I approve the position and visibility of the teeth when smiling (neither excessive nor insufficient tooth display).
3. Alignment & Angulation: I approve the position, tilt, and symmetry of the teeth relative to one another.
4. Lip & Facial Support: I approve the facial and lip support provided by the try-in (neither overly full/protruding nor overly flat/sunken).
5. Dental Midline: I approve the alignment of the dental midline (center of the front teeth).
6. Bite & Contact (Occlusion): My bite feels comfortable with balanced contact on both sides of my mouth, without premature high spots or locking.
7. Speech & Phonetics: When speaking, I do not experience excessive clicking, whistling, or tongue interference beyond normal initial adaptation.
8. Anatomical & Clinical Limitations: I understand that every patient's oral anatomy, ridge resorption, and jaw relationship are unique, and that certain aesthetic or functional compromises may be unavoidable due to clinical or anatomical limitations.

Clinic Terms & Patient Acknowledgment
• Laboratory Processing Cutoff & Irreversibility: Once this wax try-in is signed and submitted to the laboratory for processing, all approved aesthetics, tooth arrangements, shade, and bite relationships are considered final. Requests to alter tooth shape, shade, midline, or bite after processing has started will not be accommodated under the original try-in approval and will require a separate paid modification or full remake.
• Unsettled Balances Prior to Processing or Delivery: Dental Haven reserves the right to hold laboratory processing, final finishing, or release/delivery of the denture until all agreed down payments, professional fees, and past-due balances are settled in full.
• Failure to Return for Timely Try-In, Adjustment, or Delivery: If the patient delays returning for scheduled try-in, post-processing adjustments, or final denture delivery without prior valid notice, Dental Haven is not liable for changes in gum/ridge contour, tissue shifts, or fit discrepancies that may develop over time. Additional clinical re-evaluation, relining, or laboratory fees may apply if prolonged delay alters the fit.
• Pre-Denture Oral Condition & Underlying Teeth/Tissues: Approval of the wax try-in pertains to the prosthetic setup and does not guarantee the long-term prognosis of remaining natural teeth, abutment teeth, or underlying oral tissues. Any future tooth decay, periodontal issues, root/bone changes, or tissue irritation arising from oral hygiene lapses or natural biological changes are outside the clinic's liability.
• No Guarantee of Identical Appearance to Trial/Sample: While every effort is made to match the approved wax try-in, shade guides, or reference photos, minor variations in finish, surface texture, or final appearance may occur due to material properties, laboratory processing, and lighting conditions.

""" + AGREE + """

Dental Laboratory: {lab}"""

DENTURE_INSTALL = """Dear Patient,
Your custom complete or partial denture is finished and ready for installation/delivery. Prior to final release, please review and confirm your acceptance of the finished prosthesis and the clinic terms below:
1. Shade, Shape, & Size: I am satisfied with the finished shade, shape, and size of the denture teeth.
2. Smile Line & Tooth Display: I am satisfied with the position of the teeth when I smile.
3. Alignment & Angulation: I am satisfied with the position and angulation of the teeth in relation to each other.
4. Lip & Facial Support: I am satisfied that my lip and facial appearance look natural.
5. Dental Midline: I am satisfied with the midline of the teeth.
6. Bite & Contact: My bite feels acceptable and the teeth make contact on both sides.
7. Speech: When I speak, the teeth are not clicking excessively or interfering unnecessarily with speech.
8. Acceptance of Individual & Unforeseeable Limitations: I understand that every mouth differs in size, shape, bone/tissue support, and biting forces, and that unforeseeable challenges or compromises may arise that cannot be resolved without clinical compromise.

Clinic Terms & Patient Acknowledgment
• Changes After Processing / Remake Fee: By signing below, I confirm my acceptance of the delivered denture and acknowledge that any changes requested after processing or delivery will incur additional charges, and if a remake is required, I agree to pay the full total fee of ₱{fee} for remaking the prosthesis.
• Adaptation Period & Post-Insertion Adjustments: I understand that initial soreness, pressure spots, increased saliva, or temporary difficulty chewing and speaking are common during the adjustment period. I will return promptly for scheduled post-insertion adjustments rather than attempting to adjust or file the denture myself.
• Care, Hygiene, & Breakage Exclusions: I agree to clean the denture daily, soak it as instructed, keep it out of reach of children and pets, and avoid hard, sticky, or abrasive items that can crack, warp, or fracture the denture. Dental Haven and the attending dentist are not liable for breakage, warping, loss, or tissue changes resulting from accidental drops, improper home care/cleaning, natural bone/gum shrinkage over time, or failure to attend follow-up visits.

""" + AGREE + """

Dental Laboratory: {lab}"""

ORTHO_INSTRUCTIONS = """BRUSHING YOUR TEETH WITH BRACES
Use a tooth brush with a soft bristles and a small strip of fluoride toothpaste. When you brush your teeth, move the brush in small, circular motions to reach food particles that may be under your gum line. Hold the tooth brush at an angle and brush slowly and carefully, covering all areas between the teeth, around the braces, and on the surface of each tooth. Brush your tongue and the roof of your mouth before you rinse. It is important to brush your teeth 4 times daily.

FLOSSING YOUR TEETH WITH BRACES
Traditional braces are composed of brackets bonded to the teeth and held together through wires that, over time, serve to pressure the teeth into a straighter position. Though metal braces were the most common type of aligners for decades, advances in orthodontics offer an array of options that give patients more aesthetically pleasing, and more comfortable, alternatives to attaining effective results.

FOODS TO AVOID WITH BRACES
• Examples of sticky foods to avoid:
   o Gum (sugar-free or regular)
   o Toffee
   o Tootsie Rolls
   o Caramels
• Examples of hard foods to avoid:
   o Ice
   o Nuts
   o Hard taco shells
   o French bread crust/rolls
   o Corn on the cob
   o Chips
• Examples of sugary foods to minimize:
   o Cake
   o Ice cream
   o Cookies
   o Candy
• Examples of sugary foods to minimize (limit to once a day):
   o Soda
   o Sweetened tea
   o Gatorade
   o Tea

LOOSE APPLIANCE
Dental wax covering the part of the appliance hurting the mouth is often a quick remedy for loose appliances. This wax is available at our office. Please ask at your visit if you would like to have some.

LOOSE WIRE
Dental wax can also help if you have a loose wire. Tweezers can be used to adjust the wire back into its proper place. However, please call the office first to make sure this is the best thing to do.

JUTTING OR POKING WIRE
Dental wax can provide short-term relief to the area of the jutting wire. The wire can be pushed down with a pencil eraser until corrected by the dentist at your next appointment.

LOOSE BAND OR BRACKET
In cases of a loose band or bracket, an appointment at our office should be scheduled immediately if the bracket has come fully loose. If a band comes loose from your tooth, call us immediately. While a tight band actually protects a tooth from decay, a loose band can be dangerous when it comes to decay underneath, that sometimes may occur very quickly. The free bracket should be wrapped in tissue and brought with you to your appointment.

ORAL SORENESS/DISCOMFORT
New appliances and adjustments can sometimes cause discomfort or soreness in the lips, teeth, tongue, and cheeks. Warm saltwater rinses, dental wax, and over-the-counter pain relievers may help; however, the dentist should be contacted if pain and discomfort persist."""

# code, title, body, start of the first draft it replaces (None = new form)
FORMS = [
    ("extraction", "Informed consent for oral surgery & tooth extraction", EXTRACTION,
     "I, {patient}, {age}, consent to the following procedure by {dentist} at Dental Haven {branch}"),
    ("restoration", "Treatment informed consent — Tooth restoration (dental filling)", RESTORATION, None),
    ("rct_prosth", "Treatment informed consent — Endodontics (root canal therapy)", ENDO,
     "I, {patient}, {age}, consent to the following treatment by {dentist} at Dental Haven {branch}"),
    ("fixed_tryin", "Fixed bridge try-in approval form", FIXED_TRYIN, None),
    ("fixed_install", "Fixed bridge final installation & cementation consent form", FIXED_INSTALL, None),
    ("denture_tryin", "Denture wax try-in approval form", DENTURE_TRYIN, None),
    ("denture_install", "Denture installation & final acceptance consent", DENTURE_INSTALL, None),
    ("ortho_instructions", "Instructions to orthodontic patients", ORTHO_INSTRUCTIONS, None),
]

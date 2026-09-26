"""Common patient questions for the website chat (English + Tagalog).

Each entry: key, keywords (phrases patients might type, English/Tagalog/Taglish), answer in English and
Tagalog, and an optional service slug (so "Book" pre-fills that service). Answers are general
information only: no prices, no clinic policies the clinic hasn't confirmed, no medical advice.
Clinic-specific things we don't know yet (HMO, discounts, payment options) are sent to the branch.
"""

FAQ = [
    {"key": "hurt", "service": "",
     "kw": ["does it hurt", "will it hurt", "painful ba", "masakit ba", "sasakit ba", "is it painful", "pain during", "anesthesia", "anesthesia",
            "turok", "injection", "numb", "manhid"],
     "en": "Most treatments are done with local anesthesia, so the area is numb and you should feel pressure rather than pain. "
           "If you're nervous, tell your dentist: they'll explain each step and go at your pace.",
     "tl": "Karamihan ng treatment ay ginagawa nang may local anesthesia, kaya manhid ang bahagi at pressure lang ang mararamdaman, hindi sakit. "
           "Kung kinakabahan kayo, sabihin lang po sa dentista: ipapaliwanag nila ang bawat hakbang at dahan-dahan lang."},
    {"key": "nervous", "service": "",
     "kw": ["takot", "natatakot", "scared", "afraid", "nervous", "anxious", "anxiety", "kinakabahan", "phobia", "kaba"],
     "en": "You're not alone: many patients feel nervous about the dentist. Our team takes it slowly, explains everything first, and you can ask to pause anytime. "
           "For children and patients with special needs, conscious sedation is also available when appropriate.",
     "tl": "Hindi po kayo nag-iisa: marami ang kinakabahan sa dentista. Dahan-dahan ang aming team, ipinapaliwanag muna ang lahat, at puwede kayong humingi ng pahinga anumang oras. "
           "Para sa mga bata at pasyenteng may special needs, may conscious sedation din kung angkop."},
    {"key": "cleaning_often", "service": "general-dentistry",
     "kw": ["how often cleaning", "how often should", "gaano kadalas", "every 6 months", "every six months", "ilang beses", "how often check"],
     "en": "Most people should have a check-up and professional cleaning every 6 months. Some patients, like those with gum problems or braces, may need it more often. "
           "Your dentist will tell you what's right for you.",
     "tl": "Karaniwan po, tuwing 6 na buwan ang check-up at professional cleaning. May mga pasyenteng kailangan nang mas madalas, gaya ng may problema sa gilagid o naka-braces. "
           "Sasabihin ng dentista kung ano ang tama para sa inyo."},
    {"key": "cleaning_long", "service": "general-dentistry",
     "kw": ["how long cleaning", "how long does cleaning", "gaano katagal ang cleaning", "gaano katagal linis", "cleaning takes", "how long is the cleaning"],
     "en": "A check-up and cleaning usually takes about 30 to 60 minutes, depending on how much tartar needs to be removed.",
     "tl": "Karaniwang 30 hanggang 60 minuto po ang check-up at cleaning, depende sa dami ng tartar na kailangang tanggalin."},
    {"key": "extraction_after", "service": "dental-implants",
     "kw": ["after extraction", "after tooth extraction", "pagkatapos bunot", "pagkatapos ng bunot", "after bunot", "bagong bunot", "aftercare",
            "after pulling", "can i eat after", "puwede na kumain", "pwede na kumain"],
     "en": "After an extraction: bite on the gauze for 30 to 45 minutes; for the first 24 hours don't spit hard, rinse, use a straw or smoke; "
           "eat soft, cool food and chew on the other side; a cold compress helps with swelling. "
           "Call the branch if the bleeding doesn't stop, or if pain or swelling gets worse after 2 to 3 days.",
     "tl": "Pagkatapos magpabunot: kagatin ang gauze nang 30 hanggang 45 minuto; sa unang 24 oras, huwag dumura nang malakas, magmumog, gumamit ng straw o manigarilyo; "
           "kumain ng malambot at malamig na pagkain at ngumuya sa kabilang side; makakatulong ang cold compress sa pamamaga. "
           "Tumawag po sa branch kung hindi tumitigil ang dugo, o lumala ang sakit o pamamaga pagkalipas ng 2 hanggang 3 araw."},
    {"key": "wisdom", "service": "dental-implants",
     "kw": ["wisdom", "impacted", "odontectomy", "bagang sa dulo", "huling bagang", "tumutubong bagang"],
     "en": "Wisdom teeth don't always need to be removed. Your dentist checks them with an X-ray (panoramic or 3D CBCT) to see their position. "
           "Removal is usually recommended if the tooth is impacted, keeps getting infected, causes pain, or damages the tooth next to it.",
     "tl": "Hindi po laging kailangang tanggalin ang wisdom tooth. Titingnan ito ng dentista gamit ang X-ray (panoramic o 3D CBCT) para makita ang posisyon. "
           "Karaniwang inirerekomendang tanggalin kung impacted, paulit-ulit na namamaga, masakit, o nasisira ang katabing ngipin."},
    {"key": "root_canal", "service": "general-dentistry",
     "kw": ["root canal", "rct", "patay na ugat", "nerve treatment", "infected tooth", "abscess"],
     "en": "A root canal saves a badly decayed or infected tooth instead of pulling it. The infected pulp inside is cleaned out, and the tooth is sealed. "
           "It's done with local anesthesia, and a crown is often recommended afterwards to protect the tooth.",
     "tl": "Ang root canal ay paraan para mailigtas ang ngiping sirang-sira o may impeksyon sa halip na bunutin. Nililinis ang loob ng ngipin at sinasara. "
           "Ginagawa ito nang may anesthesia, at madalas inirerekomenda ang crown pagkatapos para maprotektahan ang ngipin."},
    {"key": "whitening", "service": "aesthetic-dentistry", "guide": "veneers-vs-crowns",
     "kw": ["whitening", "pampaputi", "paputi", "yellow teeth", "madilaw", "dilaw na ngipin", "stain", "mantsa sa ngipin", "bleaching"],
     "en": "Professional whitening brightens natural teeth by several shades. Results vary from person to person, and some people feel temporary sensitivity for a day or two. "
           "Whitening doesn't change the color of crowns, veneers or fillings, so your dentist will check your teeth first.",
     "tl": "Ang professional whitening ay nagpapaputi ng natural na ngipin nang ilang shade. Iba-iba ang resulta, at may ilang nakakaramdam ng pansamantalang sensitivity nang isa o dalawang araw. "
           "Hindi nagbabago ng kulay ang crowns, veneers o pasta, kaya titingnan muna ng dentista ang inyong ngipin."},
    {"key": "braces_long", "service": "orthodontics", "guide": "braces-or-clear-aligners",
     "kw": ["how long braces", "braces take", "long braces", "tagal braces", "gaano katagal braces", "gaano katagal ang braces", "how long will i wear", "ilang taon braces", "braces duration", "adjustment"],
     "en": "Treatment with braces usually takes about 1 to 3 years, depending on how much the teeth need to move. You'll come back regularly, usually every month, for adjustments. "
           "After braces, wearing a retainer keeps your teeth in place.",
     "tl": "Karaniwang 1 hanggang 3 taon po ang braces, depende sa kung gaano kalaki ang kailangang galaw ng ngipin. Babalik kayo nang regular, kadalasan buwan-buwan, para sa adjustment. "
           "Pagkatapos ng braces, ang retainer ang magpapanatili sa ayos ng ngipin."},
    {"key": "missing_tooth", "service": "dental-implants", "guide": "dental-implants-what-to-expect",
     "kw": ["missing tooth", "nawalang ngipin", "walang ngipin", "bungi", "replace tooth", "palitan ang ngipin", "denture or implant", "implant or denture",
            "implant vs", "tooth gap", "nabunot na ngipin"],
     "en": "There are three main ways to replace a missing tooth: a dental implant (fixed, doesn't touch the neighboring teeth), a bridge (fixed, supported by the teeth beside the gap), "
           "or a denture (removable, and usually the most affordable). Your dentist will check your teeth and bone and explain which fits you best.",
     "tl": "May tatlong pangunahing paraan para palitan ang nawalang ngipin: dental implant (nakakabit, hindi ginagalaw ang katabing ngipin), bridge (nakakabit, nakakapit sa katabing ngipin), "
           "o pustiso (natatanggal, at kadalasang pinaka-abot-kaya). Titingnan ng dentista ang inyong ngipin at buto at ipapaliwanag kung alin ang bagay sa inyo."},
    {"key": "implant_long", "service": "dental-implants", "guide": "dental-implants-what-to-expect",
     "kw": ["how long implant", "gaano katagal implant", "implant process", "implant takes", "implant healing"],
     "en": "An implant is usually done in stages over a few months: planning with a 3D scan, placing the implant, a few months of healing while it bonds with the bone, then the final crown. "
           "Your dentist will give you a timeline for your case.",
     "tl": "Karaniwang ilang buwan po ang implant, sa ilang yugto: planning gamit ang 3D scan, paglalagay ng implant, ilang buwang paghilom habang kumakapit sa buto, at ang huling crown. "
           "Bibigyan kayo ng dentista ng timeline para sa inyong kaso."},
    {"key": "bleeding_gums", "service": "general-dentistry",
     "kw": ["bleeding gums", "gums bleed", "gums are bleeding", "gums bleeding", "bleeding when i brush", "dumudugo ang gilagid", "gums", "dumudugo gilagid", "dumudugong gilagid", "nagdudugo ang gilagid", "gum bleeding", "swollen gums", "gilagid"],
     "en": "Gums that bleed when you brush are often a sign of gum inflammation (gingivitis), usually from plaque and tartar. A professional cleaning and good daily brushing and flossing often help. "
           "It's best to have it checked, because untreated gum disease can get worse.",
     "tl": "Ang pagdurugo ng gilagid habang nagsisipilyo ay kadalasang senyales ng pamamaga ng gilagid (gingivitis), dahil sa plaque at tartar. Nakakatulong ang professional cleaning at maayos na pagsisipilyo at floss araw-araw. "
           "Mas mabuti pong ipa-check, dahil puwedeng lumala ang sakit sa gilagid kapag hindi naagapan."},
    {"key": "bad_breath", "service": "general-dentistry",
     "kw": ["bad breath", "mabaho hininga", "mabahong hininga", "halitosis", "bad smell mouth"],
     "en": "Bad breath is commonly caused by plaque, tartar, gum problems, cavities or a coated tongue. Brushing twice a day, cleaning your tongue, flossing, and a professional cleaning usually help. "
           "If it continues, your dentist can check for the cause.",
     "tl": "Karaniwang dahilan ng mabahong hininga ang plaque, tartar, problema sa gilagid, butas na ngipin o maruming dila. Nakakatulong ang pagsisipilyo nang dalawang beses sa isang araw, paglilinis ng dila, floss, at professional cleaning. "
           "Kung hindi nawawala, matitingnan ng dentista ang dahilan."},
    {"key": "sensitive", "service": "general-dentistry",
     "kw": ["sensitive", "sensitivity", "ngilo", "nangingilo", "ngumingilo", "cold drinks hurt", "malamig masakit"],
     "en": "Sensitive teeth can come from worn enamel, receding gums, a cavity, or a cracked filling. A toothpaste for sensitive teeth often helps, "
           "but it's good to have a check-up so the dentist can find and treat the cause.",
     "tl": "Ang pangingilo ay puwedeng dahil sa nasirang enamel, umuurong na gilagid, butas na ngipin, o sirang pasta. Nakakatulong ang toothpaste para sa sensitive teeth, "
           "pero mas mabuting magpa-check-up para malaman at magamot ng dentista ang dahilan."},
    {"key": "broken", "service": "aesthetic-dentistry", "guide": "veneers-vs-crowns",
     "kw": ["broken tooth", "chipped", "cracked", "nabasag", "nabiyak", "natapyas", "sira ang ngipin", "basag na ngipin", "chip"],
     "en": "If a tooth breaks or chips, rinse your mouth with warm water, keep any pieces, and call the nearest branch as soon as you can. "
           "Small chips can often be repaired with tooth-colored bonding; bigger breaks may need a crown.",
     "tl": "Kung nabasag o natapyas ang ngipin, magmumog ng maligamgam na tubig, itabi ang piraso kung mayroon, at tumawag agad sa pinakamalapit na branch. "
           "Ang maliit na tapyas ay kadalasang naaayos ng tooth-colored bonding; ang malaking sira ay puwedeng kailanganin ng crown."},
    {"key": "lost_filling", "service": "general-dentistry", "guide": "about-dental-fillings",
     "kw": ["natanggal pasta", "filling fell", "natanggal pasta", "natanggal ang pasta", "lost filling", "crown fell", "natanggal crown", "jacket natanggal", "natanggal ang jacket", "loose crown"],
     "en": "If a filling or crown comes off, keep the crown if you have it, avoid chewing on that side, and call the branch to have it checked and fixed soon.",
     "tl": "Kung natanggal ang pasta o crown, itabi po ang crown kung mayroon, iwasang ngumuya sa side na iyon, at tumawag sa branch para maipa-check at maayos agad."},
    {"key": "pregnant", "service": "general-dentistry",
     "kw": ["pregnant", "buntis", "pregnancy", "nagbubuntis", "breastfeeding", "nagpapasuso"],
     "en": "Dental check-ups and cleanings are safe and important during pregnancy, because pregnancy can make gums more prone to swelling and bleeding. "
           "Just tell your dentist you're pregnant and how many weeks. They'll plan your care accordingly, and X-rays are taken only if really needed.",
     "tl": "Ligtas at mahalaga po ang check-up at cleaning habang buntis, dahil mas madaling mamaga at dumugo ang gilagid sa pagbubuntis. "
           "Sabihin lang po sa dentista na buntis kayo at ilang linggo na. Iaangkop nila ang treatment, at magpapa-X-ray lang kung talagang kailangan."},
    {"key": "grinding", "service": "orthodontics",
     "kw": ["grinding", "bruxism", "nagngangalit", "nagngangalit ng ngipin", "clenching", "night guard", "gigil"],
     "en": "Teeth grinding or clenching, often at night, can wear down teeth and cause jaw pain or headaches. A custom night guard can protect your teeth, "
           "and your dentist can check your bite and jaw joint (TMJ).",
     "tl": "Ang paggigiling o pagngangalit ng ngipin, kadalasan sa gabi, ay puwedeng makasira ng ngipin at magdulot ng sakit sa panga o ulo. Makakatulong ang custom night guard, "
           "at matitingnan ng dentista ang inyong kagat at panga (TMJ)."},
    {"key": "crooked", "service": "orthodontics", "guide": "braces-or-clear-aligners",
     "kw": ["crooked", "sungki", "gap teeth", "gaps", "may siwang", "siwang", "uneven teeth", "overbite", "underbite", "tabingi", "sumasalungat"],
     "en": "Crooked teeth and gaps can be straightened with braces or clear aligners. For small gaps or uneven edges, veneers or bonding can also improve the look. "
           "Your dentist will check your bite and show you the options.",
     "tl": "Ang sungki at may siwang na ngipin ay naaayos ng braces o clear aligners. Para sa maliit na siwang o hindi pantay na gilid, puwede rin ang veneers o bonding. "
           "Titingnan ng dentista ang inyong kagat at ipapakita ang mga opsyon."},
    {"key": "walk_in", "service": "",
     "kw": ["walk in", "walk-in", "walkin", "need appointment", "kailangan ba ng appointment", "pwede pumunta", "puwede pumunta", "diretso na lang", "same day"],
     "en": "We recommend booking ahead so a dentist and chair are ready for you. For a same-day visit, please call the branch first to check availability.",
     "tl": "Mas mainam pong mag-book muna para nakahanda ang dentista at upuan para sa inyo. Para sa same-day na pagpunta, tumawag po muna sa branch para malaman kung may bakante."},
    {"key": "change_booking", "service": "",
     "kw": ["reschedule", "cancel", "move my appointment", "change my appointment", "i-cancel", "ipa-cancel", "ilipat ang schedule", "palitan ang schedule", "resched"],
     "en": "To reschedule or cancel, please call or text your branch. Our team will be happy to find you a new time.",
     "tl": "Para mag-reschedule o mag-cancel, tumawag o mag-text po sa inyong branch. Masaya ang aming team na hanapan kayo ng bagong oras."},
    {"key": "bring", "service": "",
     "kw": ["what to bring", "ano dadalhin", "anong dadalhin", "ano ang dadalhin", "requirements", "first appointment", "unang punta", "prepare for"],
     "en": "For your visit, bring a list of any medicines you take and let us know about allergies or health conditions. If you have recent dental X-rays, bring them too. "
           "Please arrive about 10 minutes early.",
     "tl": "Sa inyong pagbisita, dalhin po ang listahan ng mga gamot na iniinom ninyo at sabihin kung may allergy o karamdaman. Kung may bagong dental X-ray, dalhin din po. "
           "Pumunta nang mga 10 minuto bago ang oras."},
    {"key": "discount", "service": "",
     "kw": ["senior", "pwd", "discount", "promo", "sale", "libre", "free consultation", "philhealth", "hmo", "insurance", "maxicare", "intellicare",
            "gcash", "maya", "credit card", "installment", "hulugan", "hulog", "payment", "bayad"],
     "en": "For discounts, HMO, and payment options such as cards, e-wallets or installment plans, the branch will give you the exact details. Want our team to get in touch?",
     "tl": "Para sa discount, HMO, at paraan ng pagbabayad gaya ng card, e-wallet o hulugan, ang branch po ang magbibigay ng eksaktong detalye. Gusto n'yo po bang tawagan kayo ng aming team?"},
    {"key": "sedation", "service": "pediatric-dentistry", "guide": "childs-first-dental-visit",
     "kw": ["sedation", "sedate", "pampatulog", "tulog habang", "special needs", "autism", "autistic", "pwd patient"],
     "en": "We provide gentle care for children and patients with special needs, including conscious sedation when appropriate. "
           "Your dentist will assess the patient first and explain what's safest and most comfortable.",
     "tl": "Maingat po ang aming pag-aalaga sa mga bata at pasyenteng may special needs, kasama ang conscious sedation kung angkop. "
           "Titingnan muna ng dentista ang pasyente at ipapaliwanag kung ano ang pinakaligtas at komportable."},
    {"key": "kids_age", "service": "pediatric-dentistry",
     "guide": "childs-first-dental-visit",
     "kw": ["year old", "years old", "when should we visit", "when to bring", "first visit", "what age", "anong edad", "ilang taon dapat", "baby teeth", "first tooth", "unang ngipin", "toddler", "sanggol", "gatas na ngipin", "baby ko"],
     "en": "Bring your child for their first dental visit by their first birthday, or within 6 months of the first tooth. Baby teeth matter: they help your child eat, speak, and hold space for adult teeth.",
     "tl": "Dalhin po ang bata sa unang dental visit bago mag-isang taon, o sa loob ng 6 na buwan mula nang tumubo ang unang ngipin. Mahalaga ang gatas na ngipin: tumutulong ito sa pagkain, pagsasalita, at naglalaan ng puwang para sa permanenteng ngipin."},
    {"key": "denture_care", "service": "prosthodontics", "guide": "caring-for-dentures",
     "kw": ["denture", "pustiso", "dentures", "flexite", "false teeth"],
     "en": "We make complete and partial dentures, fitted in our own digital lab. New dentures take a few weeks to get used to, and we adjust them for comfort. "
           "Clean them daily and soak them overnight so they don't dry out.",
     "tl": "Gumagawa po kami ng complete at partial na pustiso, sa sarili naming digital lab. Ilang linggo ang pag-aadjust sa bagong pustiso, at inaayos namin ito para komportable. "
           "Linisin araw-araw at ibabad sa gabi para hindi matuyo."},
    {"key": "xray_safe", "service": "general-dentistry",
     "kw": ["x-ray safe", "xray safe", "radiation", "ligtas ba ang x-ray", "safe ba ang xray", "cbct safe"],
     "en": "Dental X-rays use a low dose of radiation, and they're taken only when they help your dentist diagnose or plan treatment. Let us know if you're pregnant.",
     "tl": "Mababa po ang radiation ng dental X-ray, at ginagawa lang ito kapag makakatulong sa diagnosis o plano ng treatment. Sabihin po kung kayo ay buntis."},
    {"key": "brushing", "service": "general-dentistry",
     "kw": ["how to brush", "paano magsipilyo", "toothpaste", "toothbrush", "sipilyo", "floss", "mouthwash"],
     "en": "Brush twice a day for 2 minutes with a fluoride toothpaste and a soft brush, clean between your teeth daily with floss, and limit sugary snacks and drinks. "
           "Regular check-ups catch small problems early.",
     "tl": "Magsipilyo nang dalawang beses sa isang araw, 2 minuto, gamit ang fluoride toothpaste at malambot na sipilyo; mag-floss araw-araw; at bawasan ang matatamis. "
           "Ang regular na check-up ay nakakahuli ng maliliit na problema bago lumala."},
]

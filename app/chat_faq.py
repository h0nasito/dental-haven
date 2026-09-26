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
    {"key": "extraction_after", "service": "oral-surgery",
     "kw": ["after extraction", "after tooth extraction", "pagkatapos bunot", "pagkatapos ng bunot", "after bunot", "bagong bunot", "aftercare",
            "after pulling", "can i eat after", "puwede na kumain", "pwede na kumain"],
     "en": "After an extraction: bite on the gauze for 30 to 45 minutes; for the first 24 hours don't spit hard, rinse, use a straw or smoke; "
           "eat soft, cool food and chew on the other side; a cold compress helps with swelling. "
           "Call the branch if the bleeding doesn't stop, or if pain or swelling gets worse after 2 to 3 days.",
     "tl": "Pagkatapos magpabunot: kagatin ang gauze nang 30 hanggang 45 minuto; sa unang 24 oras, huwag dumura nang malakas, magmumog, gumamit ng straw o manigarilyo; "
           "kumain ng malambot at malamig na pagkain at ngumuya sa kabilang side; makakatulong ang cold compress sa pamamaga. "
           "Tumawag po sa branch kung hindi tumitigil ang dugo, o lumala ang sakit o pamamaga pagkalipas ng 2 hanggang 3 araw."},
    {"key": "wisdom", "service": "oral-surgery",
     "kw": ["wisdom", "impacted", "odontectomy", "bagang sa dulo", "huling bagang", "tumutubong bagang"],
     "en": "Wisdom teeth don't always need to be removed. Your dentist checks them with an X-ray (panoramic or 3D CBCT) to see their position. "
           "Removal is usually recommended if the tooth is impacted, keeps getting infected, causes pain, or damages the tooth next to it.",
     "tl": "Hindi po laging kailangang tanggalin ang wisdom tooth. Titingnan ito ng dentista gamit ang X-ray (panoramic o 3D CBCT) para makita ang posisyon. "
           "Karaniwang inirerekomendang tanggalin kung impacted, paulit-ulit na namamaga, masakit, o nasisira ang katabing ngipin."},
    {"key": "root_canal", "service": "restorative-dentistry",
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
    {"key": "missing_tooth", "service": "prosthodontics", "guide": "dental-implants-what-to-expect",
     "kw": ["missing tooth", "nawalang ngipin", "walang ngipin", "bungi", "replace tooth", "palitan ang ngipin", "denture or implant", "implant or denture",
            "implant vs", "tooth gap", "nabunot na ngipin"],
     "en": "There are three main ways to replace a missing tooth: a dental implant (fixed, doesn't touch the neighboring teeth), a bridge (fixed, supported by the teeth beside the gap), "
           "or a denture (removable, and usually the most affordable). Your dentist will check your teeth and bone and explain which fits you best.",
     "tl": "May tatlong pangunahing paraan para palitan ang nawalang ngipin: dental implant (nakakabit, hindi ginagalaw ang katabing ngipin), bridge (nakakabit, nakakapit sa katabing ngipin), "
           "o pustiso (natatanggal, at kadalasang pinaka-abot-kaya). Titingnan ng dentista ang inyong ngipin at buto at ipapaliwanag kung alin ang bagay sa inyo."},
    {"key": "implant_long", "service": "prosthodontics", "guide": "dental-implants-what-to-expect",
     "kw": ["how long implant", "gaano katagal implant", "implant process", "implant takes", "implant healing"],
     "en": "An implant is usually done in stages over a few months: planning with a 3D scan, placing the implant, a few months of healing while it bonds with the bone, then the final crown. "
           "Your dentist will give you a timeline for your case.",
     "tl": "Karaniwang ilang buwan po ang implant, sa ilang yugto: planning gamit ang 3D scan, paglalagay ng implant, ilang buwang paghilom habang kumakapit sa buto, at ang huling crown. "
           "Bibigyan kayo ng dentista ng timeline para sa inyong kaso."},
    {"key": "bleeding_gums", "service": "periodontal-care",
     "kw": ["bleeding gums", "gums bleed", "gums are bleeding", "gums bleeding", "bleeding when i brush", "dumudugo ang gilagid", "gums", "dumudugo gilagid", "dumudugong gilagid", "nagdudugo ang gilagid", "gum bleeding", "swollen gums", "gilagid"],
     "en": "Gums that bleed when you brush are often a sign of gum inflammation (gingivitis), usually from plaque and tartar. A professional cleaning and good daily brushing and flossing often help. "
           "It's best to have it checked, because untreated gum disease can get worse.",
     "tl": "Ang pagdurugo ng gilagid habang nagsisipilyo ay kadalasang senyales ng pamamaga ng gilagid (gingivitis), dahil sa plaque at tartar. Nakakatulong ang professional cleaning at maayos na pagsisipilyo at floss araw-araw. "
           "Mas mabuti pong ipa-check, dahil puwedeng lumala ang sakit sa gilagid kapag hindi naagapan."},
    {"key": "receding", "service": "periodontal-care",
     "kw": ["receding gums", "receding gum", "gum recession", "umuurong na gilagid", "umuurong ang gilagid", "exposed root", "long teeth", "gum graft"],
     "en": "Receding gums expose the roots of the teeth, which can cause sensitivity and make teeth look longer. Common causes are gum disease and brushing too hard. "
           "Depending on the cause, treatment may include a deep cleaning (scaling and root planing) or gum grafting to cover and protect the exposed roots.",
     "tl": "Kapag umuurong ang gilagid, lumalabas ang ugat ng ngipin, kaya puwedeng mangilo at magmukhang mas mahaba ang ngipin. Karaniwang dahilan ang sakit sa gilagid at sobrang diin ng pagsisipilyo. "
           "Depende sa dahilan, puwedeng irekomenda ang deep cleaning (scaling and root planing) o gum grafting para matakpan at maprotektahan ang ugat."},
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
    {"key": "broken", "service": "restorative-dentistry", "guide": "veneers-vs-crowns",
     "kw": ["broken tooth", "chipped", "cracked", "nabasag", "nabiyak", "natapyas", "sira ang ngipin", "basag na ngipin", "chip"],
     "en": "If a tooth breaks or chips, rinse your mouth with warm water, keep any pieces, and call the nearest branch as soon as you can. "
           "Small chips can often be repaired with tooth-colored bonding; bigger breaks may need a crown.",
     "tl": "Kung nabasag o natapyas ang ngipin, magmumog ng maligamgam na tubig, itabi ang piraso kung mayroon, at tumawag agad sa pinakamalapit na branch. "
           "Ang maliit na tapyas ay kadalasang naaayos ng tooth-colored bonding; ang malaking sira ay puwedeng kailanganin ng crown."},
    {"key": "lost_filling", "service": "restorative-dentistry", "guide": "about-dental-fillings",
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
     "kw": ["walk in", "walk-in", "walkin", "need appointment", "need an appointment", "need to book", "kailangan ba mag-book", "kailangan ba ng appointment", "pwede pumunta", "puwede pumunta", "diretso na lang", "same day"],
     "en": "We recommend booking ahead so a dentist and chair are ready for you. For a same-day visit, please call the branch first to check availability.",
     "tl": "Mas mainam pong mag-book muna para nakahanda ang dentista at upuan para sa inyo. Para sa same-day na pagpunta, tumawag po muna sa branch para malaman kung may bakante."},
    {"key": "change_booking", "service": "",
     "kw": ["reschedule", "cancel", "move my appointment", "change my appointment", "i-cancel", "ipa-cancel", "ilipat ang schedule", "palitan ang schedule", "resched"],
     "en": "To reschedule or cancel, please call or text your branch. Our team will be happy to find you a new time.",
     "tl": "Para mag-reschedule o mag-cancel, tumawag o mag-text po sa inyong branch. Masaya ang aming team na hanapan kayo ng bagong oras."},
    {"key": "bring", "service": "",
     "kw": ["bring", "arrive early", "come early", "agahan", "maaga", "what to bring", "ano dadalhin", "anong dadalhin", "ano ang dadalhin", "requirements", "first appointment", "unang punta", "prepare for"],
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
    {"key": "emergency_offer", "service": "",
     "kw": ["emergency dental", "dental emergency", "emergency procedure", "emergency appointment", "same day emergency", "emergency ba", "urgent appointment"],
     "en": "For a dental emergency such as severe pain, a broken or knocked-out tooth, or swelling, call your nearest branch right away so we can try to see you as soon as possible during clinic hours (Monday to Saturday, 9 AM to 6 PM). "
           "For severe facial swelling, trouble breathing or swallowing, or bleeding that won't stop, go to the nearest hospital emergency room or call 911.",
     "tl": "Para sa dental emergency gaya ng matinding sakit, nabasag o natanggal na ngipin, o pamamaga, tumawag agad sa pinakamalapit na branch para masubukan namin kayong makita sa lalong madaling panahon sa oras ng clinic (Lunes hanggang Sabado, 9 AM hanggang 6 PM). "
           "Kung matindi ang pamamaga ng mukha, hirap huminga o lumunok, o hindi tumitigil ang dugo, pumunta sa pinakamalapit na emergency room o tumawag sa 911."},
    {"key": "knocked_out", "service": "",
     "kw": ["knocked out", "knocked-out", "tooth fell out", "natanggal ang ngipin", "nalaglag ang ngipin", "natanggal na ngipin", "tumalsik ang ngipin"],
     "en": "If a permanent tooth is knocked out: hold it by the crown (not the root), rinse it gently if dirty, and keep it moist in milk or saliva. Call the nearest branch right away: the sooner a dentist sees it, ideally within an hour, the better the chance of saving it.",
     "tl": "Kung natanggal ang permanenteng ngipin: hawakan sa korona (hindi sa ugat), banlawan nang marahan kung marumi, at panatilihing basa sa gatas o laway. Tumawag agad sa pinakamalapit na branch: mas maaga itong makita ng dentista, mas mabuti kung sa loob ng isang oras, mas malaki ang tsansang mailigtas."},
    {"key": "medication", "service": "",
     "kw": ["medicine", "medication", "gamot", "painkiller", "pain killer", "pain reliever", "mefenamic", "ibuprofen", "paracetamol", "biogesic", "antibiotic",
            "amoxicillin", "anong iinumin", "what can i take", "recommend something"],
     "en": "I'm not able to recommend or prescribe medicine in this chat, because the right choice depends on your health, allergies and other medicines. Please call your branch so a dentist can advise you. "
           "If the pain is severe, or you have swelling or a fever, see a dentist as soon as possible, or go to the emergency room if it's serious.",
     "tl": "Hindi po ako makapagrerekomenda o makapagreseta ng gamot dito, dahil depende ito sa inyong kalusugan, allergy at iba pang iniinom na gamot. Pakitawagan ang branch para mapayuhan kayo ng dentista. "
           "Kung matindi ang sakit, o may pamamaga o lagnat, magpatingin agad sa dentista, o pumunta sa emergency room kung malala."},
    {"key": "toothache_cause", "service": "general-dentistry",
     "kw": ["what's causing", "whats causing", "what is causing", "cause of my", "why does my tooth", "why is my tooth", "bakit sumasakit", "bakit masakit", "ano ang dahilan"],
     "en": "I can't tell what's causing it from a chat, but common causes of toothache include a cavity, a cracked tooth or filling, gum problems, an infection, or sensitive teeth. "
           "A dentist can find the cause with a quick exam and, if needed, an X-ray. Would you like to book a check-up?",
     "tl": "Hindi ko po masasabi ang dahilan sa chat, pero karaniwang sanhi ng sakit ng ngipin ang butas, bitak na ngipin o pasta, problema sa gilagid, impeksyon, o sensitive na ngipin. "
           "Malalaman ng dentista ang dahilan sa mabilis na pagsusuri at X-ray kung kailangan. Gusto n'yo po bang mag-book ng check-up?"},
    {"key": "which_right", "service": "",
     "kw": ["which procedure", "which treatment", "right for me", "best for me", "what do i need", "ano ang kailangan ko", "anong treatment", "bagay sa akin", "best option"],
     "en": "The best way to know is a consultation: your dentist checks your teeth, takes X-rays if needed, and explains your options, timelines and costs so you can choose what's right for you.",
     "tl": "Ang pinakamainam na paraan ay magpakonsulta: titingnan ng dentista ang inyong ngipin, kukuha ng X-ray kung kailangan, at ipapaliwanag ang mga opsyon, tagal at halaga para makapili kayo ng tama para sa inyo."},
    {"key": "languages", "service": "",
     "kw": ["language", "languages", "speak english", "speak tagalog", "what languages", "anong wika", "marunong ba mag-english", "nagsasalita"],
     "en": "This chat works in English and Tagalog: switch anytime with EN / TL at the top. For help in another language, please call your branch.",
     "tl": "Gumagana ang chat na ito sa English at Tagalog: puwedeng magpalit anumang oras gamit ang EN / TL sa itaas. Para sa ibang wika, pakitawagan ang branch."},
    {"key": "accessible", "service": "",
     "kw": ["wheelchair", "accessible", "accessibility", "disability", "disabled", "ramp", "elevator", "stairs", "hagdan", "naka-wheelchair"],
     "en": "Please call your branch before your visit so they can tell you about access at that location and prepare to assist you.",
     "tl": "Pakitawagan po ang branch bago pumunta para masabi nila ang tungkol sa pagpasok sa lugar na iyon at makapaghanda silang tumulong."},
    {"key": "companion", "service": "",
     "kw": ["bring someone", "bring a companion", "bring my", "companion", "kasama", "may kasama", "isama", "can my mom", "can my husband", "can my wife", "can my friend"],
     "en": "You're welcome to bring someone with you for support. Children should come with a parent or guardian.",
     "tl": "Puwede po kayong magsama ng kasama para sa suporta. Ang mga bata ay dapat may kasamang magulang o guardian."},
    {"key": "eat_before", "service": "",
     "kw": ["eat before", "kumain bago", "breakfast before", "before my appointment", "brush before", "brush my teeth before", "magsipilyo bago", "fast before", "ayuno"],
     "en": "For most treatments, yes: eat a light meal and brush your teeth before you come. If you're having sedation or certain surgeries, your dentist may ask you not to eat beforehand, so follow any instructions you're given.",
     "tl": "Sa karamihan ng treatment, opo: kumain nang magaan at magsipilyo bago pumunta. Kung may sedation o ilang surgery, puwedeng sabihan kayong huwag kumain bago nito, kaya sundin ang ibibigay na bilin."},
    {"key": "appointment_length", "service": "",
     "kw": ["how long will my appointment", "how long is my appointment", "how long is the appointment", "how long will the appointment", "gaano katagal ang appointment", "how long will i be there"],
     "en": "It depends on the treatment: a check-up and cleaning usually takes about 30 to 60 minutes, a filling 20 to 60 minutes, and longer treatments like root canals or surgery 1 to 2 hours. Tell me which treatment and I'll give you a closer estimate.",
     "tl": "Depende po sa treatment: karaniwang 30 hanggang 60 minuto ang check-up at cleaning, 20 hanggang 60 minuto ang pasta, at 1 hanggang 2 oras ang mas mahabang treatment gaya ng root canal o surgery. Sabihin kung anong treatment para mas eksakto ang sagot ko."},
    {"key": "book_here", "service": "",
     "kw": ["book through this chat", "book through the chat", "book here", "book in this chat", "book via chat", "dito na lang mag-book", "dito mag-book", "pwede ba dito"],
     "en": "Yes! Tap \"Book a visit\" and I'll take you straight to our booking page with your branch and treatment already filled in: just pick a time. Or tap \"Have our team call me\" and we'll call you to set it up.",
     "tl": "Opo! I-tap ang \"Mag-book\" at dadalhin ko kayo sa booking page na nakalagay na ang branch at treatment: pumili na lang ng oras. O i-tap ang \"Patawagan ako sa staff\" at tatawagan namin kayo."},
    {"key": "website", "service": "",
     "kw": ["website", "web site", "webpage", "online site"],
     "en": "You're on it: this is Dental Haven's website. Each branch also has its own Facebook page, which I can show you under Branches.",
     "tl": "Nandito na po kayo: ito ang website ng Dental Haven. May sariling Facebook page din ang bawat branch, na maipapakita ko sa Branches."},
    {"key": "parking", "service": "",
     "kw": ["parking", "park my car", "paradahan", "may parking", "saan mag-park", "saan magpark"],
     "en": "For parking at a specific branch, please call that branch; they'll tell you the nearest parking spot. I can also show you each branch's map.",
     "tl": "Para sa parking sa isang branch, pakitawagan po ang branch na iyon; sasabihin nila ang pinakamalapit na paradahan. Maipapakita ko rin ang mapa ng bawat branch."},
    {"key": "dont_see", "service": "",
     "kw": ["haven't asked", "havent asked", "don't see", "dont see", "not here", "other question", "another question", "ibang tanong", "wala dito", "may tanong pa ako"],
     "en": "No problem: our team can answer anything I can't. Leave your name and number and we'll get back to you, or call your nearest branch.",
     "tl": "Walang problema: masasagot ng aming team ang hindi ko kaya. Iwan ang pangalan at numero at babalikan namin kayo, o tumawag sa pinakamalapit na branch."},
    {"key": "materials_safe", "service": "",
     "kw": ["materials safe", "material safe", "safe materials", "materials you use safe", "ligtas ba ang materyales", "biocompatible", "mercury", "toxic"],
     "en": "Dental materials are made specifically for use in the mouth and are widely used and tested. Your dentist chooses materials that suit your health, and will discuss any concerns, including allergies or a preference for metal-free options.",
     "tl": "Ang dental materials ay ginawa para sa bibig at malawakang ginagamit at sinusuri. Pumipili ang dentista ng materyales na angkop sa inyong kalusugan, at pag-uusapan ang anumang alalahanin, kasama ang allergy o kagustuhan sa walang-metal na opsyon."},
    {"key": "allergy", "service": "",
     "kw": ["allergy", "allergies", "allergic", "allergic to metal", "nickel", "latex", "may allergy", "about any allergies", "any allergies", "allergies before", "tell you about my allergies"],
     "en": "Yes, please tell your dentist about any allergies before treatment, for example to metals like nickel, latex, anesthetics, or medicines. There are alternative materials for many treatments, such as metal-free crowns and ceramic braces.",
     "tl": "Opo, sabihin po sa dentista ang anumang allergy bago ang treatment, halimbawa sa metal gaya ng nickel, latex, anesthesia, o gamot. May alternatibong materyales para sa maraming treatment, gaya ng metal-free na crown at ceramic braces."},
    {"key": "choose_material", "service": "",
     "kw": ["choose the material", "choose my material", "pick the material", "pumili ng materyales", "pumili ng material", "can i choose", "material options"],
     "en": "Yes. When there's more than one suitable option, your dentist explains each one (how it looks, how long it lasts, and the cost) so you can choose what fits your needs and budget.",
     "tl": "Opo. Kapag may higit sa isang angkop na opsyon, ipapaliwanag ng dentista ang bawat isa (itsura, tibay at halaga) para mapili ninyo ang bagay sa inyong pangangailangan at budget."},
    {"key": "material_cost", "service": "",
     "kw": ["material affect the cost", "materials affect the cost", "material affect the price", "depends on the material", "depende sa materyales", "mas mahal ba", "cost depend on material"],
     "en": "Yes, the material affects the cost. For example, zirconia or porcelain crowns usually cost more than metal ones, and porcelain veneers more than composite. Your dentist will give you the price for each option before treatment.",
     "tl": "Opo, nakakaapekto ang materyales sa halaga. Halimbawa, mas mahal kadalasan ang zirconia o porcelain na crown kaysa metal, at ang porcelain veneers kaysa composite. Ibibigay ng dentista ang presyo ng bawat opsyon bago ang treatment."},
    {"key": "samples", "service": "",
     "kw": ["samples", "sample of the material", "show me the material", "show me samples", "see the materials", "makita ang materyales", "ipakita"],
     "en": "At your consultation you can ask your dentist to show you the options for your treatment, such as shade guides for tooth-colored materials, and explain how each one looks.",
     "tl": "Sa konsulta, puwede ninyong hilingin sa dentista na ipakita ang mga opsyon para sa inyong treatment, gaya ng shade guide para sa tooth-colored na materyales, at ipaliwanag ang itsura ng bawat isa."},
    {"key": "material_diff", "service": "",
     "kw": ["differences between the", "difference between the materials", "which material is better", "best material", "materials last", "each material", "anong materyales ang mas maganda"],
     "en": "Each material has trade-offs: tooth-colored options (composite, ceramic, zirconia, porcelain) look the most natural; metal options are very strong and often cost less; porcelain and zirconia usually last longest. Tell me the treatment (for example crowns, fillings or veneers) and I'll explain its options.",
     "tl": "May kanya-kanyang kalamangan ang bawat materyales: ang tooth-colored (composite, ceramic, zirconia, porcelain) ang pinaka-natural ang itsura; ang metal ay napakatibay at kadalasang mas mura; ang porcelain at zirconia ang karaniwang pinakamatagal. Sabihin ang treatment (hal. crown, pasta o veneers) at ipapaliwanag ko ang mga opsyon."},
    {"key": "temporary", "service": "restorative-dentistry",
     "kw": ["temporary crown", "temporary crowns", "temporary filling", "temporary fillings", "temporary", "pansamantalang"],
     "en": "Temporary crowns are usually made of acrylic or composite, and temporary fillings of a soft temporary filling material. They protect the tooth for a short time until the final crown or filling is ready, so avoid sticky and hard food on that side.",
     "tl": "Ang temporary crown ay kadalasang gawa sa acrylic o composite, at ang temporary na pasta ay sa malambot na pansamantalang materyales. Pinoprotektahan nito ang ngipin habang hinihintay ang final na crown o pasta, kaya iwasan ang malagkit at matigas na pagkain sa side na iyon."},
]

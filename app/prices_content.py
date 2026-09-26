"""SAMPLE prices, for testing the website chat only. They are NOT Dental Haven's prices.

Every row is marked sample=1. The public site never shows prices until a super admin confirms the
price list is real (Administration → Price list → "Show prices to patients"); the demo site shows
them labelled as sample prices. Replace them with the clinic's actual prices before confirming.
Keywords (comma separated, English and Tagalog) help the chat find the right item.
"""

# (name, service slug, from ₱, to ₱ or None, unit, keywords)
SAMPLE_PRICES = [
    # Preventive & Diagnostic
    ("Consultation & check-up", "general-dentistry", 500, None, "", "consult,consultation,check-up,checkup,check up,exam,konsulta,patingin"),
    ("Oral prophylaxis (cleaning)", "general-dentistry", 1000, 2000, "", "cleaning,linis,prophylaxis,prophy,oral prophylaxis,scaling and polishing,tartar"),
    ("Panoramic X-ray", "general-dentistry", 800, None, "", "panoramic,x-ray,xray,panoramic x-ray,pano"),
    ("Cephalometric X-ray", "general-dentistry", 800, None, "", "cephalometric,ceph,cephalo"),
    ("CBCT 3D X-ray", "general-dentistry", 3500, None, "", "cbct,3d x-ray,3d xray,cone beam"),
    ("Fluoride treatment", "general-dentistry", 800, None, "", "fluoride,varnish"),
    ("Dental sealant", "general-dentistry", 800, None, "per tooth", "sealant,sealants,pit and fissure"),
    ("Oral cancer screening", "general-dentistry", 500, None, "", "oral cancer,cancer screening,screening"),
    # Restorative
    ("Tooth filling (composite)", "restorative-dentistry", 1000, None, "per surface", "filling,pasta,composite filling,cavity,butas"),
    ("Tooth filling (amalgam)", "restorative-dentistry", 800, None, "per surface", "amalgam,silver filling"),
    ("Zirconia crown", "restorative-dentistry", 15000, None, "per unit", "zirconia,crown,jacket,cap,zirconia crown"),
    ("Porcelain-fused-to-metal crown", "restorative-dentistry", 8000, None, "per unit", "pfm,porcelain fused,metal crown,jacket,crown,cap"),
    ("Dental bridge", "restorative-dentistry", 24000, None, "3 units", "bridge,fixed bridge,tulay"),
    ("Inlay / onlay", "restorative-dentistry", 8000, None, "per tooth", "inlay,onlay,inlays,onlays"),
    ("Root canal therapy", "restorative-dentistry", 7000, None, "per tooth", "root canal,rct,endo,endodontic,nerve"),
    # Prosthodontics & Tooth Replacement
    ("Complete denture", "prosthodontics", 15000, None, "per arch", "complete denture,full denture,pustiso,dentures,denture"),
    ("Flexible partial denture", "prosthodontics", 10000, None, "", "flexible denture,flexite,partial denture,pustiso,valplast"),
    ("Dental implant", "prosthodontics", 60000, None, "per tooth, including crown", "implant,implants,dental implant,tanim na ngipin"),
    ("Composite veneers", "prosthodontics", 4000, None, "per tooth", "veneer,veneers,composite veneer,direct veneer"),
    ("Porcelain / E.max veneers", "prosthodontics", 15000, None, "per tooth", "porcelain veneer,emax,e.max,ceramic veneer"),
    # Orthodontics & TMJ
    ("Metal braces", "orthodontics", 40000, None, "total package", "braces,brace,metal braces,bracket,ortho"),
    ("Ceramic braces", "orthodontics", 60000, None, "total package", "ceramic braces,clear braces,tooth-colored braces"),
    ("Clear aligners", "orthodontics", 120000, None, "total", "aligner,aligners,invisalign,clear aligner,invisible braces"),
    ("Retainer", "orthodontics", 3000, None, "per arch", "retainer,retainers"),
    ("TMJ consultation", "orthodontics", 1000, None, "", "tmj,jaw pain,panga,jaw clicking"),
    # Oral Surgery
    ("Tooth extraction", "oral-surgery", 1000, None, "per tooth", "extraction,bunot,pull tooth,tooth removal,extract"),
    ("Wisdom tooth removal (odontectomy)", "oral-surgery", 8000, None, "per tooth", "wisdom,odontectomy,impacted,wisdom tooth,third molar"),
    ("Bone grafting", "oral-surgery", 15000, None, "per site", "bone graft,bone grafting,graft"),
    # Cosmetic Dentistry
    ("Teeth whitening", "aesthetic-dentistry", 12000, None, "", "whitening,bleaching,pampaputi,paputi,whiten"),
    ("Dental bonding", "aesthetic-dentistry", 1500, None, "per tooth", "bonding,dental bonding,chip repair"),
    ("Smile makeover consultation", "aesthetic-dentistry", 1000, None, "", "smile makeover,makeover,smile design"),
    # Periodontal (Gum) Care
    ("Scaling and root planing (deep cleaning)", "periodontal-care", 3000, None, "per quadrant", "deep cleaning,root planing,scaling and root planing,periodontitis,gum disease"),
    ("Gum grafting", "periodontal-care", 15000, None, "per site", "gum graft,gum grafting,receding gums,receding gum"),
    # Pediatrics & Special Care
    ("Silver diamine fluoride (SDF)", "pediatric-dentistry", 500, None, "per tooth", "sdf,silver diamine,silver fluoride"),
    ("Filling for kids", "pediatric-dentistry", 800, None, "per tooth", "kids filling,child filling,pasta ng bata,baby tooth filling"),
    ("Crown for kids", "pediatric-dentistry", 3500, None, "per tooth", "kids crown,crown for kids,stainless crown,child crown"),
]


# ---------------------------------------------------------------------------------------------------
# DENTAL HAVEN PRICE LIST 2026 (from "Dental_Haven_Pricelist_2026.pdf", Sept 2026).
# Used by the website chat and quotations only; never shown on the website pages.
# (name, service slug, price ₱, to ₱ or None, kind 'fixed'|'from'|'range', unit, keywords, note)
# Items the PDF gives no readable price for (dental implants, sapphire braces, ceramic braces class 2-3)
# are left out, so the chat offers a consultation instead of guessing.
# ---------------------------------------------------------------------------------------------------
CLINIC_PRICES_VERSION = 2
# v2: the clinic confirmed crown, bridge and veneer prices are per tooth.
PER_TOOTH_V2 = ("Porcelain E.max crown / bridge", "Zirconia crown / bridge", "Ceramic crown / bridge", "Milled PMMA crown / bridge",
                "3D-printed crown", "Endo crown: E.max", "Endo crown: zirconia", "Endo crown: ceramic", "Endo crown: milled PMMA",
                "Veneers: porcelain E.max", "Veneers: zirconia", "Veneers: ceramic", "Veneers: 3D-printed", "Veneers: direct composite")
RENAMES_V2 = {"Porcelain E.max crown / 3-unit bridge": "Porcelain E.max crown / bridge"}
BRACES_NOTE = "Payment packages with a downpayment and monthly payments are available; ask the branch for the package details."
CLINIC_PRICES = [
    # Diagnostics / X-rays
    ("Dental examination (check-up)", "general-dentistry", 650, None, "fixed", "", "check-up,checkup,check up,exam,examination,consultation,consult,konsulta,patingin", ""),
    ("Periapical X-ray (single tooth)", "general-dentistry", 600, None, "fixed", "", "periapical,pa x-ray,x-ray,xray,x ray,single tooth x-ray", ""),
    ("Panoramic X-ray", "general-dentistry", 1000, None, "fixed", "", "panoramic,pano,x-ray,xray,x ray", ""),
    ("Cephalometric X-ray (lateral or AP)", "general-dentistry", 1000, None, "fixed", "", "cephalometric,ceph,cephalo,x-ray,xray", ""),
    ("Carpal (hand-wrist) X-ray", "general-dentistry", 1000, None, "fixed", "", "carpal,hand x-ray,hand-wrist", ""),
    ("Transcranial (TMJ) X-ray", "general-dentistry", 1000, None, "fixed", "", "transcranial,tmj x-ray", ""),
    ("CBCT 3D scan, 3x3 field of view", "general-dentistry", 3500, None, "fixed", "", "cbct,3d x-ray,3d xray,3d scan,cone beam,x-ray,xray", ""),
    ("CBCT 3D scan, 12x9 field of view", "general-dentistry", 7500, None, "fixed", "", "cbct,3d x-ray,3d xray,3d scan,cone beam", ""),
    ("CBCT 3D scan, 16x14.5 field of view", "general-dentistry", 8500, None, "fixed", "", "cbct,3d x-ray,3d xray,3d scan,cone beam", ""),
    # Cleaning
    ("Oral prophylaxis (cleaning): mild", "general-dentistry", 980, None, "fixed", "", "cleaning,linis,magpalinis,prophylaxis,prophy,oral prophylaxis,scaling", "Regular cleanings, soft deposits."),
    ("Oral prophylaxis (cleaning): moderate", "general-dentistry", 1700, 2300, "range", "", "cleaning,linis,magpalinis,prophylaxis,prophy,oral prophylaxis,scaling", "Noticeable tartar and stains."),
    ("Oral prophylaxis (cleaning): severe", "general-dentistry", 2300, 2700, "range", "", "cleaning,linis,magpalinis,prophylaxis,prophy,oral prophylaxis,scaling", "Years without cleaning, heavy stains and tartar; a 2nd scaling is recommended."),
    # Preventive / pediatric
    ("Fluoride varnish (adult)", "general-dentistry", 1850, None, "fixed", "", "fluoride,varnish", ""),
    ("Fluoride varnish (child)", "pediatric-dentistry", 1500, None, "fixed", "", "fluoride,varnish,kids fluoride,child fluoride", ""),
    ("Dental sealant", "general-dentistry", 1000, None, "fixed", "", "sealant,sealants,pit and fissure", ""),
    ("Silver diamine fluoride (SDF)", "pediatric-dentistry", 1200, None, "fixed", "per quadrant", "sdf,silver diamine,silver fluoride", ""),
    ("Resin infiltration (ICON)", "general-dentistry", 2500, None, "fixed", "per tooth", "resin infiltration,icon,white spot,white spots,fluorosis", "Treats early decay and white spots without drilling or anesthesia."),
    ("Stainless steel crown (kids)", "pediatric-dentistry", 4500, None, "fixed", "per unit", "stainless steel crown,stainless crown,ssc,kids crown,crown for kids,child crown", ""),
    ("Strip-off crown (kids)", "pediatric-dentistry", 3000, None, "fixed", "per unit", "strip off crown,strip-off crown,strip crown,soc,kids crown,crown for kids", ""),
    # Restorations (fillings)
    ("Filling: back teeth (posterior)", "restorative-dentistry", 980, None, "from", "", "filling,fillings,pasta,magpapasta,posterior,back teeth,likod,cavity,butas", ""),
    ("Filling: front teeth (anterior)", "restorative-dentistry", 1200, 2700, "range", "", "filling,fillings,pasta,magpapasta,anterior,front teeth,harap,cavity,butas", ""),
    ("Filling: between teeth (Class 2)", "restorative-dentistry", 2500, 2700, "range", "", "filling,fillings,pasta,magpapasta,class 2,in between,pagitan,cavity,butas", ""),
    ("Filling: at the gumline (Class 5)", "restorative-dentistry", 1200, 2500, "range", "", "filling,fillings,pasta,magpapasta,class 5,gumline,gum line", ""),
    ("Medicament (liner or base)", "restorative-dentistry", 450, None, "fixed", "", "liner,base,medicament", ""),
    ("Diastema closure", "aesthetic-dentistry", 2700, 3700, "range", "", "diastema,gap between,space between,siwang,close the gap", ""),
    # Root canal & related
    ("Root canal therapy: standard", "restorative-dentistry", 9500, None, "from", "", "root canal,rct,endodontic,endo,pulp,patay na ugat", ""),
    ("Root canal therapy: difficult", "restorative-dentistry", 12500, None, "fixed", "", "root canal,rct,endodontic,endo,pulp", ""),
    ("Root canal retreatment", "restorative-dentistry", 15500, None, "fixed", "", "root canal,rct,retreatment,re-treatment,redo root canal", ""),
    ("Internal bleaching (after root canal)", "aesthetic-dentistry", 10000, None, "fixed", "", "internal bleaching,dark tooth,discolored tooth after root canal,non vital bleaching", "Whitens a tooth from the inside; takes about 7 to 14 days."),
    ("Post and core: porcelain", "restorative-dentistry", 10500, None, "fixed", "", "post and core,post,core", ""),
    ("Post and core: fiber", "restorative-dentistry", 6500, None, "fixed", "", "post and core,fiber post,post,core", ""),
    ("Tooth build-up", "restorative-dentistry", 3000, 4500, "range", "", "build up,build-up,buildup,core build", ""),
    ("Endo crown: E.max", "restorative-dentistry", 30000, None, "fixed", "per tooth", "endo crown,endocrown", ""),
    ("Endo crown: zirconia", "restorative-dentistry", 25000, None, "fixed", "per tooth", "endo crown,endocrown", ""),
    ("Endo crown: ceramic", "restorative-dentistry", 20000, None, "fixed", "per tooth", "endo crown,endocrown", ""),
    ("Endo crown: milled PMMA", "restorative-dentistry", 18000, None, "fixed", "per tooth", "endo crown,endocrown", ""),
    # Crowns & bridges
    ("Porcelain E.max crown / bridge", "restorative-dentistry", 35000, None, "fixed", "per tooth", "crown,crowns,jacket,cap,bridge,tulay,emax,e.max,porcelain crown", ""),
    ("Zirconia crown / bridge", "restorative-dentistry", 25000, None, "fixed", "per tooth", "crown,crowns,jacket,cap,bridge,tulay,zirconia", ""),
    ("Ceramic crown / bridge", "restorative-dentistry", 20000, None, "fixed", "per tooth", "crown,crowns,jacket,cap,bridge,tulay,ceramic crown", ""),
    ("Milled PMMA crown / bridge", "restorative-dentistry", 18000, None, "fixed", "per tooth", "crown,crowns,jacket,cap,bridge,tulay,pmma,milled", ""),
    ("3D-printed crown", "restorative-dentistry", 15000, None, "fixed", "per tooth", "crown,crowns,jacket,cap,3d printed,3d-printed,printed crown", ""),
    ("Inlay / onlay / overlay: 3D-printed PMMA", "restorative-dentistry", 8500, None, "fixed", "", "inlay,onlay,overlay,inlays,onlays", ""),
    ("Inlay / onlay / overlay: milled PMMA", "restorative-dentistry", 10500, None, "fixed", "", "inlay,onlay,overlay,inlays,onlays", ""),
    ("Inlay / onlay / overlay: porcelain", "restorative-dentistry", 15500, None, "fixed", "", "inlay,onlay,overlay,inlays,onlays", ""),
    # Veneers
    ("Veneers: porcelain E.max", "prosthodontics", 35000, None, "fixed", "per tooth", "veneer,veneers,laminate,laminates,emax,e.max,porcelain veneer", ""),
    ("Veneers: zirconia", "prosthodontics", 30000, None, "fixed", "per tooth", "veneer,veneers,laminate,laminates,zirconia veneer", ""),
    ("Veneers: ceramic", "prosthodontics", 25000, None, "fixed", "per tooth", "veneer,veneers,laminate,laminates,ceramic veneer", ""),
    ("Veneers: 3D-printed", "prosthodontics", 15000, None, "fixed", "per tooth", "veneer,veneers,laminate,laminates,3d printed veneer", ""),
    ("Veneers: direct composite", "prosthodontics", 10000, None, "fixed", "per tooth", "veneer,veneers,laminate,laminates,composite veneer,direct composite", ""),
    # Cosmetic
    ("Teeth whitening: in-clinic (chairside)", "aesthetic-dentistry", 10000, None, "fixed", "", "whitening,whiten,bleaching,bleach,pampaputi,paputi,magpaputi,chairside,in-office,in clinic", "1 to 2 shades lighter per session."),
    ("Teeth whitening: take-home kit", "aesthetic-dentistry", 15000, None, "fixed", "", "whitening,whiten,bleaching,bleach,pampaputi,paputi,take home,take-home,home whitening", "Custom trays and whitening gel to use at home."),
    # Gum care
    ("Deep scaling", "periodontal-care", 2000, 2500, "range", "per quadrant", "deep scaling,deep cleaning,deep clean,root planing,scaling and root planing,periodontitis,gum disease", "Usually done weekly, one quadrant at a time, under local anesthesia."),
    ("Gingivectomy (gum reshaping)", "periodontal-care", 10500, None, "fixed", "per arch", "gingivectomy,gum reshaping,gummy smile,gum contouring", ""),
    ("Crown lengthening", "periodontal-care", 8500, None, "fixed", "", "crown lengthening", ""),
    # Oral surgery
    ("Tooth extraction", "oral-surgery", 980, None, "from", "", "extraction,extract,bunot,magpabunot,pabunot,pull tooth,tooth removal", ""),
    ("Complicated extraction", "oral-surgery", 2000, 4000, "range", "", "complicated extraction,surgical extraction,curved root,ankylosed,extraction,bunot", ""),
    ("Odontectomy (impacted wisdom tooth): standard", "oral-surgery", 10500, None, "from", "", "odontectomy,wisdom,wisdom tooth,wisdom teeth,impacted,third molar,bagang sa dulo", ""),
    ("Odontectomy: difficult", "oral-surgery", 15000, 25000, "range", "", "odontectomy,wisdom,wisdom tooth,wisdom teeth,impacted,third molar", ""),
    ("Odontectomy: special case (e.g. impacted canine)", "oral-surgery", 35000, None, "fixed", "", "odontectomy,impacted canine,special case", ""),
    ("Sedation for oral surgery (partner anesthesiologist)", "oral-surgery", 25000, None, "fixed", "", "sedation,sedate,pampatulog,anesthesiologist", ""),
    ("Anesthesia (add-on)", "oral-surgery", 600, None, "fixed", "", "anesthesia,anaesthesia,turok", ""),
    ("Suture (add-on)", "oral-surgery", 600, None, "fixed", "", "suture,tahi,stitches", ""),
    ("Bone graft", "oral-surgery", 35000, None, "from", "", "bone graft,bone grafting,graft", ""),
    # Orthodontics
    ("Metal braces: Class 1", "orthodontics", 45000, 60000, "range", "", "braces,brace,metal braces,magpabrace,magpa-brace,bracket,ortho,class 1", BRACES_NOTE),
    ("Metal braces: Class 2 (overbite)", "orthodontics", 60000, 80000, "range", "", "braces,brace,metal braces,magpabrace,bracket,ortho,class 2,overbite", BRACES_NOTE),
    ("Metal braces: Class 3 (underbite)", "orthodontics", 80000, 100000, "range", "", "braces,brace,metal braces,magpabrace,bracket,ortho,class 3,underbite", BRACES_NOTE),
    ("Ceramic braces: Class 1", "orthodontics", 65000, 80000, "range", "", "ceramic braces,clear braces,tooth-colored braces", BRACES_NOTE),
    ("Self-ligating braces: Class 1", "orthodontics", 80000, 100000, "range", "", "self ligating,self-ligating,damon", BRACES_NOTE),
    ("Self-ligating braces: Class 2", "orthodontics", 90000, 110000, "range", "", "self ligating,self-ligating,damon", BRACES_NOTE),
    ("Self-ligating braces: Class 3", "orthodontics", 100000, 120000, "range", "", "self ligating,self-ligating,damon", BRACES_NOTE),
    ("Clear aligners", "orthodontics", 160000, None, "from", "", "aligner,aligners,invisalign,clear aligner,clear aligners,invisible braces", "Plus the digital treatment plan (ClinCheck)."),
    ("Aligner digital treatment plan (ClinCheck)", "orthodontics", 8500, None, "fixed", "", "clincheck,aligner plan", ""),
    ("Digital impression (3D scan)", "orthodontics", 1000, None, "fixed", "", "digital impression,3d scan,intraoral scan,scan", ""),
    ("Intraoral photos", "orthodontics", 1000, None, "fixed", "", "intraoral photos,photos", ""),
    ("Extraoral photos", "orthodontics", 1000, None, "fixed", "", "extraoral photos,photos", ""),
    ("Palatal expander", "orthodontics", 10000, None, "fixed", "per arch", "expander,palatal expander", ""),
    ("Bite plane (Catlan's appliance)", "orthodontics", 10000, None, "fixed", "per arch", "bite plane,bite plate,catlan,deep bite", ""),
    ("Ortho splint (TMJ)", "orthodontics", 8500, None, "fixed", "per arch", "splint,ortho splint,tmj,jaw pain", ""),
    ("Retainer: invisible (clear)", "orthodontics", 10000, None, "fixed", "per arch", "retainer,retainers,invisible retainer,clear retainer", ""),
    ("Retainer: Hawley", "orthodontics", 8000, None, "fixed", "per arch", "retainer,retainers,hawley", ""),
    ("Retainer: wrap-around Hawley", "orthodontics", 8500, None, "fixed", "per arch", "retainer,retainers,wrap around,wrap-around", ""),
    ("Retainer: lingual (fixed)", "orthodontics", 10000, None, "fixed", "per arch", "retainer,retainers,lingual retainer,fixed retainer,permanent retainer", ""),
    ("Retainer: all-metal", "orthodontics", 12000, None, "fixed", "per arch", "retainer,retainers,metal retainer,all metal", ""),
    # Removable dentures
    ("Denture, 1-6 teeth: ordinary base", "prosthodontics", 9500, None, "fixed", "", "denture,dentures,pustiso,partial denture,false teeth,ordinary base", ""),
    ("Denture, 1-6 teeth: Lucitone base (Germany)", "prosthodontics", 13500, None, "fixed", "", "denture,dentures,pustiso,partial denture,false teeth,lucitone", ""),
    ("Denture, 1-6 teeth: Basis Hi base (Japan)", "prosthodontics", 15000, None, "fixed", "", "denture,dentures,pustiso,partial denture,false teeth,basis", ""),
    ("Denture, 1-6 teeth: flexible base", "prosthodontics", 25500, None, "fixed", "", "denture,dentures,pustiso,partial denture,false teeth,flexible,flexite,valplast", ""),
    ("Denture, 1-6 teeth: Ivocap base", "prosthodontics", 35000, None, "fixed", "", "denture,dentures,pustiso,partial denture,false teeth,ivocap", ""),
    ("Denture, 7 teeth to complete: ordinary base", "prosthodontics", 11500, None, "fixed", "", "complete denture,full denture,buong pustiso,7 teeth,ordinary base", ""),
    ("Denture, 7 teeth to complete: Lucitone base (Germany)", "prosthodontics", 16000, None, "fixed", "", "complete denture,full denture,buong pustiso,7 teeth,lucitone", ""),
    ("Denture, 7 teeth to complete: Basis Hi base (Japan)", "prosthodontics", 18500, None, "fixed", "", "complete denture,full denture,buong pustiso,7 teeth,basis", ""),
    ("Denture, 7 teeth and up: flexible base", "prosthodontics", 29500, None, "fixed", "", "complete denture,full denture,7 teeth,flexible,flexite", "Not recommended for complete dentures."),
    ("Denture, 7 teeth to complete: Ivocap base", "prosthodontics", 37500, None, "fixed", "", "complete denture,full denture,buong pustiso,7 teeth,ivocap", ""),
]

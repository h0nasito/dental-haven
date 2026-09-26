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

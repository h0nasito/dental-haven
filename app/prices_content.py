"""SAMPLE prices, for testing the website chat only. They are NOT Dental Haven's prices.

Every row is marked sample=1. The public site never shows prices until a super admin confirms the
price list is real (Administration → Price list → "Show prices to patients"); the demo site shows
them labelled as sample prices. Replace them with the clinic's actual prices before confirming.
Keywords (comma separated, English and Tagalog) help the chat find the right item.
"""

# (name, service slug, from ₱, to ₱ or None, unit, keywords)
SAMPLE_PRICES = [
    ("Consultation & check-up", "general-dentistry", 500, None, "", "consult,consultation,check-up,checkup,check up,exam,konsulta,patingin"),
    ("Oral prophylaxis (cleaning)", "general-dentistry", 1000, 2000, "", "cleaning,linis,prophylaxis,prophy,oral prophylaxis,scaling,tartar"),
    ("Tooth filling (tooth-colored)", "general-dentistry", 1000, None, "per surface", "filling,pasta,composite filling,cavity,butas"),
    ("Root canal treatment", "general-dentistry", 7000, None, "per tooth", "root canal,rct,endo,nerve"),
    ("Panoramic X-ray", "general-dentistry", 800, None, "", "panoramic,x-ray,xray,panoramic x-ray,pano"),
    ("CBCT 3D X-ray", "general-dentistry", 3500, None, "", "cbct,3d x-ray,3d xray,cone beam"),
    ("Fluoride treatment", "pediatric-dentistry", 800, None, "", "fluoride,varnish"),
    ("Dental sealant", "pediatric-dentistry", 800, None, "per tooth", "sealant,sealants,pit and fissure"),
    ("Silver diamine fluoride (SDF)", "pediatric-dentistry", 500, None, "per tooth", "sdf,silver diamine,silver fluoride"),
    ("Filling for kids", "pediatric-dentistry", 800, None, "per tooth", "kids filling,child filling,pasta ng bata,baby tooth filling"),
    ("Crown for kids", "pediatric-dentistry", 3500, None, "per tooth", "kids crown,crown for kids,stainless crown,child crown"),
    ("Teeth whitening", "aesthetic-dentistry", 12000, None, "", "whitening,bleaching,pampaputi,paputi,whiten"),
    ("Composite veneers", "aesthetic-dentistry", 4000, None, "per tooth", "veneer,veneers,composite veneer,direct veneer"),
    ("Porcelain / E.max veneers", "aesthetic-dentistry", 15000, None, "per tooth", "porcelain veneer,emax,e.max,ceramic veneer"),
    ("Zirconia crown", "aesthetic-dentistry", 15000, None, "per unit", "zirconia,crown,jacket,cap,zirconia crown"),
    ("Porcelain-fused-to-metal crown", "aesthetic-dentistry", 8000, None, "per unit", "pfm,porcelain fused,metal crown,jacket,crown"),
    ("Dental bridge", "aesthetic-dentistry", 24000, None, "3 units", "bridge,fixed bridge,tulay"),
    ("Metal braces", "orthodontics", 40000, None, "total package", "braces,brace,metal braces,bracket,ortho"),
    ("Ceramic braces", "orthodontics", 60000, None, "total package", "ceramic braces,clear braces,tooth-colored braces"),
    ("Clear aligners", "orthodontics", 120000, None, "total", "aligner,aligners,invisalign,clear aligner,invisible braces"),
    ("Retainer", "orthodontics", 3000, None, "per arch", "retainer,retainers"),
    ("TMJ consultation", "orthodontics", 1000, None, "", "tmj,jaw pain,panga,jaw clicking"),
    ("Complete denture", "prosthodontics", 15000, None, "per arch", "complete denture,full denture,pustiso,dentures,denture"),
    ("Flexible partial denture", "prosthodontics", 10000, None, "", "flexible denture,flexite,partial denture,pustiso,valplast"),
    ("Tooth extraction", "dental-implants", 1000, None, "per tooth", "extraction,bunot,pull tooth,tooth removal,extract"),
    ("Wisdom tooth removal (odontectomy)", "dental-implants", 8000, None, "per tooth", "wisdom,odontectomy,impacted,wisdom tooth"),
    ("Dental implant", "dental-implants", 60000, None, "per tooth, including crown", "implant,implants,dental implant,tanim na ngipin"),
]

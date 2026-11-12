-- Common words patients use for each service (shown under the service when booking online), and the one they chose.
ALTER TABLE services ADD COLUMN patient_terms TEXT NOT NULL DEFAULT '';
ALTER TABLE booking_requests ADD COLUMN service_detail TEXT NOT NULL DEFAULT '';
UPDATE services SET patient_terms = 'Check-up / consultation
Cleaning (oral prophylaxis)
Fluoride' WHERE name = 'Preventive & Diagnostic Services' AND patient_terms = '';
UPDATE services SET patient_terms = 'Pasta (tooth filling)
Restoration (sira o butas na ngipin)
Root canal' WHERE name = 'Restorative Services' AND patient_terms = '';
UPDATE services SET patient_terms = 'Pustiso (dentures)
Jacket (crown)
Bridge
Implant' WHERE name = 'Prosthodontics & Tooth Replacement' AND patient_terms = '';
UPDATE services SET patient_terms = 'Braces
Braces adjustment
Retainer
Jaw pain (TMJ)' WHERE name = 'Orthodontics & TMJ' AND patient_terms = '';
UPDATE services SET patient_terms = 'Bunot (tooth extraction)
Wisdom tooth (bagang) removal' WHERE name = 'Oral Surgery' AND patient_terms = '';
UPDATE services SET patient_terms = 'Teeth whitening
Veneers' WHERE name = 'Cosmetic Dentistry' AND patient_terms = '';
UPDATE services SET patient_terms = 'Deep cleaning
Bleeding or swollen gums' WHERE name = 'Periodontal (Gum) Care' AND patient_terms = '';
UPDATE services SET patient_terms = 'Kids'' check-up
Kids'' cleaning
Kids'' pasta or bunot' WHERE name = 'Pediatrics & Special Care Dentistry' AND patient_terms = ''

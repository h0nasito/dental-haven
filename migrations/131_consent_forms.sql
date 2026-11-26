-- Patient consent forms: wording kept per form (edited by admin, approved by a dentist before use) and the signed copies.
CREATE TABLE consent_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE patient_consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    template_id INTEGER REFERENCES consent_templates(id),
    branch_id INTEGER REFERENCES branches(id),
    dentist_id INTEGER REFERENCES users(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    procedure_text TEXT,
    teeth TEXT,
    signed_by_name TEXT NOT NULL,
    signed_by_relation TEXT,
    signature_stored TEXT NOT NULL,
    signed_at TEXT NOT NULL,
    witness_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'valid',
    void_reason TEXT,
    voided_by INTEGER REFERENCES users(id),
    voided_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_patient_consents_patient ON patient_consents(patient_id);
INSERT INTO role_permissions (role, permission) SELECT DISTINCT role, 'consent.take' FROM role_permissions WHERE permission IN ('patients.manage', 'clinical.edit')

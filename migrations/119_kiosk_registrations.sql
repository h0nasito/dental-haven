-- New-patient kiosk: a patient fills in their details on a clinic tablet; staff review each one before a patient record is made.
CREATE TABLE kiosk_registrations (
    id INTEGER PRIMARY KEY,
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    signature_name TEXT NOT NULL DEFAULT '',
    photo_name TEXT NOT NULL DEFAULT '',
    started_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TEXT,
    patient_id INTEGER REFERENCES patients(id),
    review_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_kiosk_reg_status ON kiosk_registrations(status, branch_id)

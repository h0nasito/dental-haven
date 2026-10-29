-- Rows of every MyMedsPH billing report uploaded, so reports uploaded one dentist at a time add up per bill day.
CREATE TABLE IF NOT EXISTS legacy_billing_report_rows (
    key TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    patient TEXT NOT NULL,
    dentist TEXT NOT NULL DEFAULT '',
    clinic TEXT NOT NULL DEFAULT '',
    procedures TEXT NOT NULL DEFAULT '',
    gross INTEGER NOT NULL DEFAULT 0,
    discount INTEGER NOT NULL DEFAULT 0,
    net INTEGER NOT NULL DEFAULT 0,
    paid INTEGER NOT NULL DEFAULT 0,
    balance INTEGER NOT NULL DEFAULT 0
)

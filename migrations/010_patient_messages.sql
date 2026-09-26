-- Automatic messages to patients (email now, SMS when a provider is set up). The text itself is not stored.
CREATE TABLE patient_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event TEXT NOT NULL,                 -- approved | declined | rescheduled | cancelled | reminder
  channel TEXT NOT NULL,               -- email | sms
  patient_id INTEGER REFERENCES patients(id),
  appointment_id INTEGER REFERENCES appointments(id),
  booking_request_id INTEGER REFERENCES booking_requests(id),
  branch_id INTEGER REFERENCES branches(id),
  recipient_masked TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,                -- sent | failed | not_set_up | demo | skipped
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE INDEX idx_patient_messages_appt ON patient_messages(appointment_id);
CREATE INDEX idx_patient_messages_req ON patient_messages(booking_request_id);

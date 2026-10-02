-- Patients shared by all branches (e.g. imported from a clinic-wide MyMedsPH export): staff of every branch can see them.
ALTER TABLE patients ADD COLUMN shared INTEGER NOT NULL DEFAULT 0;

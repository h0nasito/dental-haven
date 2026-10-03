-- About us on the website: team members (dentists, staff, lab) and clinic activities with photos.
CREATE TABLE team_members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  grp TEXT NOT NULL DEFAULT 'dentist' CHECK (grp IN ('dentist','staff','lab')),
  credentials TEXT NOT NULL DEFAULT '',
  bio TEXT NOT NULL DEFAULT '',
  photo_path TEXT NOT NULL DEFAULT '',
  consent_note TEXT NOT NULL DEFAULT '',
  published INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE team_member_branches (
  member_id INTEGER NOT NULL REFERENCES team_members(id) ON DELETE CASCADE,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  PRIMARY KEY (member_id, branch_id)
);
CREATE TABLE activities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  happened_on TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'event',
  body TEXT NOT NULL DEFAULT '',
  branch_id INTEGER REFERENCES branches(id),
  consent_note TEXT NOT NULL DEFAULT '',
  published INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_activities_pub ON activities(published, happened_on);
CREATE TABLE activity_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
  image_path TEXT NOT NULL,
  caption TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_activity_photos ON activity_photos(activity_id, sort_order)

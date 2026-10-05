-- Individual access: switch single permissions on (granted = 1) or off (granted = 0) for one user, on top of their role.
CREATE TABLE user_permissions (
  user_id INTEGER NOT NULL REFERENCES users(id),
  permission TEXT NOT NULL,
  granted INTEGER NOT NULL CHECK (granted IN (0, 1)),
  PRIMARY KEY (user_id, permission)
)

"""Audit trail. Stored in the database (access-restricted), never in application logs."""
from __future__ import annotations

import json

from flask import g, has_request_context

from .db import get_db
from .util import now_str


def record(action: str, entity_type: str, entity_id=None, summary: str = "", details=None, branch_id=None,
           actor_id=None, conn=None):
    conn = conn or get_db()
    if actor_id is None and has_request_context() and g.get("user") is not None:
        actor_id = g.user.id
    conn.execute(
        "INSERT INTO audit_log (at, actor_id, action, entity_type, entity_id, branch_id, summary, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (now_str(), actor_id, action, entity_type, entity_id, branch_id, summary[:300],
         json.dumps(details or {}, default=str)),
    )


def diff(before: dict | None, after: dict, fields) -> dict:
    """Return {field: [old, new]} for changed fields."""
    before = before or {}
    changes = {}
    for f in fields:
        old, new = before.get(f), after.get(f)
        if (old if old is not None else "") != (new if new is not None else ""):
            changes[f] = [old, new]
    return changes

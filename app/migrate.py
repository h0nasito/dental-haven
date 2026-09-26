"""Apply SQL migrations in migrations/ in filename order. Tracks applied files in schema_migrations."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .db import Conn

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _to_postgres(sql: str) -> str:
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    return sql


def _statements(sql: str) -> list[str]:
    # strip line comments, then split on semicolons at end of statements
    cleaned = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", cleaned) if s.strip()]


def run_migrations(conn: Conn, verbose: bool = True) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {r["name"] for r in conn.all("SELECT name FROM schema_migrations")}
    done = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        if conn.database.is_postgres:
            sql = _to_postgres(sql)
        with conn.transaction():
            for stmt in _statements(sql):
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (path.name, datetime.now().isoformat(timespec="seconds")),
            )
        done.append(path.name)
        if verbose:
            print(f"applied {path.name}")
    return done

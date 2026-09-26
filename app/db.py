"""Thin database layer.

Development/demo uses SQLite (Python standard library). The SQL in this project is
kept portable so production can run on PostgreSQL: set DATABASE_URL=postgresql://...
and install psycopg (see docs/DEPLOYMENT.md). Queries use "?" placeholders; the
Postgres adapter rewrites them to "%s".
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable

from flask import current_app, g


class Row(dict):
    """dict with attribute access, so templates can use row.name or row['name']."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover - mirrors attribute semantics
            raise AttributeError(item) from exc


def _sqlite_row_factory(cursor, row):
    return Row({col[0]: row[idx] for idx, col in enumerate(cursor.description)})


class Database:
    def __init__(self, url: str):
        self.url = url
        self.is_postgres = url.startswith("postgres")
        self._local = threading.local()

    # -- connections -------------------------------------------------------
    def connect(self):
        if self.is_postgres:  # pragma: no cover - not available in the dev sandbox
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore

            conn = psycopg.connect(self.url, row_factory=dict_row, autocommit=True)
            return conn
        path = self.url.replace("sqlite:///", "", 1)
        conn = sqlite3.connect(path, timeout=15, isolation_level=None)  # autocommit; we manage transactions
        conn.row_factory = _sqlite_row_factory
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 15000")
        return conn

    def sql(self, query: str) -> str:
        if self.is_postgres:  # pragma: no cover
            return query.replace("?", "%s")
        return query


def get_db() -> "Conn":
    if "db_conn" not in g:
        database: Database = current_app.extensions["database"]
        g.db_conn = Conn(database, database.connect())
    return g.db_conn


def close_db(_exc=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.raw.close()


class Conn:
    """Wraps a DB-API connection with small helpers."""

    def __init__(self, database: Database, raw):
        self.database = database
        self.raw = raw
        self._depth = 0

    def execute(self, query: str, params: Iterable[Any] = ()):
        cur = self.raw.cursor()
        cur.execute(self.database.sql(query), tuple(params))
        return cur

    def executemany(self, query: str, seq_of_params):
        cur = self.raw.cursor()
        cur.executemany(self.database.sql(query), [tuple(p) for p in seq_of_params])
        return cur

    def all(self, query: str, params: Iterable[Any] = ()) -> list[Row]:
        cur = self.execute(query, params)
        rows = cur.fetchall()
        return [r if isinstance(r, Row) else Row(r) for r in rows]

    def one(self, query: str, params: Iterable[Any] = ()) -> Row | None:
        cur = self.execute(query, params)
        row = cur.fetchone()
        if row is None:
            return None
        return row if isinstance(row, Row) else Row(row)

    def scalar(self, query: str, params: Iterable[Any] = ()):
        row = self.one(query, params)
        if row is None:
            return None
        return next(iter(row.values()))

    def insert(self, table: str, values: dict[str, Any]) -> int:
        cols = ", ".join(values.keys())
        marks = ", ".join("?" for _ in values)
        row = self.one(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING id", values.values())
        return int(row["id"])

    def update(self, table: str, row_id: int, values: dict[str, Any]) -> None:
        sets = ", ".join(f"{k} = ?" for k in values)
        self.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*values.values(), row_id])

    @contextmanager
    def transaction(self, immediate: bool = False):
        """Nested-safe transaction. immediate=True takes the write lock up front in SQLite,
        which serialises concurrent schedulers so conflict checks cannot race."""
        if self._depth == 0:
            if self.database.is_postgres:  # pragma: no cover
                # SERIALIZABLE gives the same guarantee as SQLite's write lock for conflict checks.
                self.raw.execute("BEGIN ISOLATION LEVEL SERIALIZABLE" if immediate else "BEGIN")
            else:
                self.raw.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        self._depth += 1
        try:
            yield self
        except Exception:
            self._depth -= 1
            if self._depth == 0:
                self.raw.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self.raw.execute("COMMIT")


def standalone_connection(url: str) -> Conn:
    database = Database(url)
    return Conn(database, database.connect())

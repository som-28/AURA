"""Shared persistence adapter for local JSON and Neon/PostgreSQL AURA state."""
from __future__ import annotations

import os
from contextvars import ContextVar, Token
from functools import lru_cache
from typing import Any


_request_owner_id: ContextVar[str | None] = ContextVar("aura_request_owner_id", default=None)


def set_request_owner_id(owner_id: str) -> Token:
    return _request_owner_id.set(owner_id)


def get_request_owner_id() -> str | None:
    return _request_owner_id.get()


def reset_request_owner_id(token: Token) -> None:
    _request_owner_id.reset(token)


class PostgresStateBackend:
    """Store structured AURA state and current resume files in PostgreSQL."""

    def __init__(self, dsn: str, owner_id: str):
        self.dsn = dsn
        self.default_owner_id = owner_id
        self._schema_ready = False

    @property
    def owner_id(self) -> str:
        return _request_owner_id.get() or self.default_owner_id

    def _connect(self):
        try:
            import psycopg
        except ImportError as error:
            raise RuntimeError("Neon PostgreSQL storage needs psycopg[binary]; install the project requirements") from error
        connection = psycopg.connect(self.dsn, autocommit=True, connect_timeout=10)
        if not self._schema_ready:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS aura_state (
                    owner_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (owner_id, namespace)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS aura_files (
                    owner_id TEXT NOT NULL,
                    file_key TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    content BYTEA NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (owner_id, file_key)
                )
            """)
            self._schema_ready = True
        return connection

    def read_state(self, namespace: str, default: Any) -> Any:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM aura_state WHERE owner_id = %s AND namespace = %s",
                (self.owner_id, namespace),
            ).fetchone()
        return row[0] if row else default

    def write_state(self, namespace: str, value: Any) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as connection:
            connection.execute("""
                INSERT INTO aura_state (owner_id, namespace, data, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (owner_id, namespace)
                DO UPDATE SET data = excluded.data, updated_at = now()
            """, (self.owner_id, namespace, Jsonb(value)))

    def write_state_if_absent(self, namespace: str, value: Any) -> bool:
        from psycopg.types.json import Jsonb

        with self._connect() as connection:
            row = connection.execute("""
                INSERT INTO aura_state (owner_id, namespace, data, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (owner_id, namespace) DO NOTHING
                RETURNING namespace
            """, (self.owner_id, namespace, Jsonb(value))).fetchone()
        return row is not None

    def write_file(self, file_key: str, file_name: str, content_type: str, content: bytes) -> None:
        with self._connect() as connection:
            connection.execute("""
                INSERT INTO aura_files (owner_id, file_key, file_name, content_type, content, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (owner_id, file_key)
                DO UPDATE SET file_name = excluded.file_name,
                              content_type = excluded.content_type,
                              content = excluded.content,
                              updated_at = now()
            """, (self.owner_id, file_key, file_name, content_type, content))

    def read_file(self, file_key: str) -> tuple[str, str, bytes] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT file_name, content_type, content FROM aura_files WHERE owner_id = %s AND file_key = %s",
                (self.owner_id, file_key),
            ).fetchone()
        return (row[0], row[1], bytes(row[2])) if row else None

    def file_exists(self, file_key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM aura_files WHERE owner_id = %s AND file_key = %s",
                (self.owner_id, file_key),
            ).fetchone()
        return row is not None

    def delete_file(self, file_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM aura_files WHERE owner_id = %s AND file_key = %s",
                (self.owner_id, file_key),
            )


@lru_cache(maxsize=4)
def _database_backend(dsn: str, owner_id: str) -> PostgresStateBackend:
    return PostgresStateBackend(dsn, owner_id)


def get_database_backend() -> PostgresStateBackend | None:
    backend_name = os.getenv("AURA_STORAGE_BACKEND", "local").strip().lower()
    if backend_name == "local":
        return None
    if backend_name != "neon":
        raise RuntimeError("AURA_STORAGE_BACKEND must be 'local' or 'neon'")
    # Neon CLI injects DATABASE_URL; keep NEON_DATABASE_URL as an explicit
    # override for deployments that name the secret themselves.
    dsn = (os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not dsn:
        raise RuntimeError("Set NEON_DATABASE_URL or DATABASE_URL when AURA_STORAGE_BACKEND=neon")
    owner_id = os.getenv("AURA_USER_ID", "single-user").strip()
    if not owner_id:
        raise RuntimeError("AURA_USER_ID must be a non-empty stable identifier")
    return _database_backend(dsn, owner_id)

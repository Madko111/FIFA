"""Postgres backend for user settings and KPI tracking.

Exposes the same shape as the legacy JSON-file API:
- get_user_language(user_id) -> str | None
- set_user_language(user_id, language)
- load_kpi_data() -> {"daily_stats": {}, "user_interactions": {user_id_str: iso_ts}}
- track_user_interaction(user_id)

If DATABASE_URL is not set, all calls are no-ops returning empty data, so the bot
keeps working in environments without Postgres.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")

_pool: Optional[ConnectionPool] = None


def _get_pool() -> Optional[ConnectionPool]:
    global _pool
    if not DATABASE_URL:
        return None
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
        )
        _init_schema()
    return _pool


def _init_schema() -> None:
    assert _pool is not None
    with _pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id      BIGINT PRIMARY KEY,
                language     TEXT,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_interactions (
                user_id BIGINT PRIMARY KEY,
                last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        conn.commit()


def is_enabled() -> bool:
    return bool(DATABASE_URL)


def get_user_language(user_id: int) -> Optional[str]:
    pool = _get_pool()
    if pool is None:
        return None
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT language FROM user_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row["language"] if row else None


def set_user_language(user_id: int, language: str) -> None:
    pool = _get_pool()
    if pool is None:
        return
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, language, last_updated)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET language = EXCLUDED.language,
                  last_updated = NOW();
            """,
            (user_id, language),
        )
        conn.commit()


def track_user_interaction(user_id: int) -> None:
    pool = _get_pool()
    if pool is None:
        return
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_interactions (user_id, last_seen)
            VALUES (%s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET last_seen = NOW();
            """,
            (user_id,),
        )
        conn.commit()


def load_kpi_data() -> dict:
    """Mimics legacy JSON shape so callers don't have to change."""
    pool = _get_pool()
    if pool is None:
        return {"daily_stats": {}, "user_interactions": {}}
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id, last_seen FROM user_interactions;")
        rows = cur.fetchall()
    interactions = {str(r["user_id"]): r["last_seen"].isoformat() for r in rows}
    return {"daily_stats": {}, "user_interactions": interactions}


def migrate_from_json(user_settings_path: str, kpi_data_path: str) -> tuple[int, int]:
    """One-shot migration from old JSON files. Returns (users_inserted, interactions_inserted)."""
    import json

    pool = _get_pool()
    if pool is None:
        return (0, 0)

    users = 0
    interactions = 0

    if os.path.exists(user_settings_path):
        with open(user_settings_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        with pool.connection() as conn, conn.cursor() as cur:
            for uid, payload in data.items():
                lang = (payload or {}).get("language")
                if not lang:
                    continue
                ts = (payload or {}).get("last_updated") or datetime.now().isoformat()
                cur.execute(
                    """
                    INSERT INTO user_settings (user_id, language, last_updated)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                      SET language = EXCLUDED.language,
                          last_updated = EXCLUDED.last_updated;
                    """,
                    (int(uid), lang, ts),
                )
                users += 1
            conn.commit()

    if os.path.exists(kpi_data_path):
        with open(kpi_data_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        kpi_interactions = (data or {}).get("user_interactions") or {}
        with pool.connection() as conn, conn.cursor() as cur:
            for uid, ts in kpi_interactions.items():
                cur.execute(
                    """
                    INSERT INTO user_interactions (user_id, last_seen)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET last_seen = EXCLUDED.last_seen;
                    """,
                    (int(uid), ts),
                )
                interactions += 1
            conn.commit()

    return (users, interactions)

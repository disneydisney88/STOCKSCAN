"""Shared intraday state in the existing CCASS Turso database."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

TURSO_DATABASE_URL = "TURSO_DATABASE_URL"
TURSO_AUTH_TOKEN = "TURSO_AUTH_TOKEN"


def configured() -> bool:
    return bool(os.getenv(TURSO_DATABASE_URL, "").strip() and os.getenv(TURSO_AUTH_TOKEN, "").strip())


def _http_url(url: str) -> str:
    return "https://" + url[len("libsql://"):] if url.lower().startswith("libsql://") else url


def _client():
    try:
        import libsql_client
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("libsql-client is required when Turso state is enabled") from exc
    return libsql_client.create_client_sync(
        _http_url(os.environ[TURSO_DATABASE_URL].strip()),
        auth_token=os.environ[TURSO_AUTH_TOKEN].strip(),
    )


def _ensure_schema(client) -> None:
    client.execute(
        """CREATE TABLE IF NOT EXISTS intraday_state (
             trade_date TEXT NOT NULL,
             symbol TEXT NOT NULL,
             state_json TEXT NOT NULL,
             updated_at TEXT NOT NULL,
             PRIMARY KEY (trade_date, symbol)
        )"""
    )


def load(day: date) -> dict:
    with _client() as client:
        _ensure_schema(client)
        result = client.execute(
            "SELECT symbol, state_json FROM intraday_state WHERE trade_date=?",
            [day.isoformat()],
        )
    return {str(row[0]): json.loads(str(row[1])) for row in result.rows}


def save(day: date, state: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    statements = [
        (
            """INSERT INTO intraday_state(trade_date,symbol,state_json,updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(trade_date,symbol) DO UPDATE SET
               state_json=excluded.state_json, updated_at=excluded.updated_at""",
            [day.isoformat(), symbol, json.dumps(value, ensure_ascii=False), now],
        )
        for symbol, value in state.items()
    ]
    if not statements:
        return
    with _client() as client:
        _ensure_schema(client)
        client.batch(statements)

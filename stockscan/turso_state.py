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
    client.execute(
        """CREATE TABLE IF NOT EXISTS intraday_alerts (
             ts TEXT NOT NULL, trade_date TEXT NOT NULL, code5 TEXT NOT NULL,
             symbol TEXT, name TEXT, alert_type TEXT, count_today INTEGER,
             level_from INTEGER, level_to INTEGER, chg_pct REAL, last_done REAL,
             turnover_intraday REAL, mcap_now REAL, ratio_intraday REAL,
             off_hours INTEGER, corp_action_suspect INTEGER,
             resumption_suspect INTEGER, price_gap_suspect INTEGER,
             source TEXT DEFAULT '',
             PRIMARY KEY (ts, trade_date, code5, alert_type)
        )"""
    )
    client.execute(
        """CREATE TABLE IF NOT EXISTS scan_heartbeat (
             source TEXT PRIMARY KEY, last_scan_ts TEXT NOT NULL
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


def append_alerts(day: date, alerts: list[dict], source: str = "") -> None:
    """逐條 alert 入 Turso（PK ts+trade_date+code5+alert_type 天然去重）。"""
    if not alerts or not configured():
        return
    cols = ("ts", "code5", "symbol", "name", "alert_type", "count_today", "level_from",
            "level_to", "chg_pct", "last_done", "turnover_intraday", "mcap_now",
            "ratio_intraday", "off_hours", "corp_action_suspect", "resumption_suspect",
            "price_gap_suspect")
    stmt = ("INSERT OR IGNORE INTO intraday_alerts (ts, trade_date, code5, symbol, name, "
            "alert_type, count_today, level_from, level_to, chg_pct, last_done, "
            "turnover_intraday, mcap_now, ratio_intraday, off_hours, corp_action_suspect, "
            "resumption_suspect, price_gap_suspect, source) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    now = datetime.now(timezone.utc).isoformat()
    statements = []
    for a in alerts:
        row = dict(a)
        statements.append((stmt, [
            row.get("ts"), day.isoformat(), str(row.get("code5", "")).zfill(5),
            row.get("symbol"), row.get("name"), row.get("alert_type"),
            row.get("count_today"), row.get("level_from"), row.get("level_to"),
            row.get("chg_pct"), row.get("last_done"), row.get("turnover_intraday"),
            row.get("mcap_now"),
            row.get("ratio_intraday") if row.get("ratio_intraday") != "" else None,
            row.get("off_hours"), row.get("corp_action_suspect"),
            row.get("resumption_suspect"), row.get("price_gap_suspect"), source,
        ]))
    if not statements:
        return
    with _client() as client:
        _ensure_schema(client)
        client.batch(statements)


def touch_heartbeat(source: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _client() as client:
        _ensure_schema(client)
        client.execute(
            """INSERT INTO scan_heartbeat (source, last_scan_ts) VALUES (?, ?)
               ON CONFLICT (source) DO UPDATE SET last_scan_ts = excluded.last_scan_ts""",
            [source or "unknown", now])


def other_source_minutes_ago(source: str = "") -> float | None:
    """另一邊（雲／本機）最近一次掃描距現在幾分鐘；冇紀錄回 None。"""
    with _client() as client:
        _ensure_schema(client)
        result = client.execute(
            "SELECT source, last_scan_ts FROM scan_heartbeat ORDER BY last_scan_ts DESC")
    from datetime import datetime as _dt

    for row in result.rows:
        src, ts = str(row[0]), str(row[1])
        if src and src != source:
            try:
                last = _dt.fromisoformat(ts)
                return (_dt.now(last.tzinfo) - last).total_seconds() / 60
            except ValueError:
                continue
    return None


def recent_alerts(days: int = 3, limit: int = 500):
    """tab2 用：最近 N 日 alert DataFrame（倒序）；唔係 configured 時回 None。"""
    if not configured():
        return None
    import pandas as pd

    with _client() as client:
        _ensure_schema(client)
        result = client.execute(
            "SELECT * FROM intraday_alerts ORDER BY ts DESC LIMIT ?",
            [limit])
    cols = ["ts", "trade_date", "code5", "symbol", "name", "alert_type", "count_today",
            "level_from", "level_to", "chg_pct", "last_done", "turnover_intraday",
            "mcap_now", "ratio_intraday", "off_hours", "corp_action_suspect",
            "resumption_suspect", "price_gap_suspect", "source"]
    return pd.DataFrame(result.rows, columns=cols)

"""Queries for the normalized historical event database."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from config import DATA_DIR

EVENTS_DB = DATA_DIR / "events.db"


def events_after(code5: str, start: str | date, days: int,
                 db_path: Path = EVENTS_DB) -> list[dict]:
    """Return events for ``code5`` whose announce date is in the window.

    The window is inclusive at both ends. Rows with an unparsed announce date
    are intentionally excluded because they cannot be ordered by date; they
    remain in the database for audit via ``date_parse_failed`` and raw_json.
    """
    start_date = date.fromisoformat(start) if isinstance(start, str) else start
    end_date = start_date + timedelta(days=days)
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT event_type, code5, name, announce_date, key_date_1,
                      key_date_2, price_1, price_2, ratio, agent, status,
                      raw_json, date_parse_failed
                 FROM events
                WHERE code5 = ?
                  AND announce_date >= ?
                  AND announce_date <= ?
                ORDER BY announce_date, rowid""",
            (code5.replace(".hk", "").zfill(5), start_date.isoformat(),
             end_date.isoformat()),
        ).fetchall()
    return [dict(row) for row in rows]

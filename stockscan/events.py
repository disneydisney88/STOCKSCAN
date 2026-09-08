"""Queries for the normalized historical event database."""
from __future__ import annotations

import sqlite3
import re
from datetime import date, timedelta
from pathlib import Path

from config import DATA_DIR

EVENTS_DB = DATA_DIR / "events.db"


def corporate_action_on(code5: str, effective_date: str | date,
                        db_path: Path = EVENTS_DB) -> dict | None:
    """Return a same-day consolidation/split event, if one is recorded."""
    day = effective_date.isoformat() if isinstance(effective_date, date) else str(effective_date)
    code = code5.replace(".hk", "").zfill(5)
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            """SELECT event_type, code5, name, announce_date, key_date_1,
                      key_date_2, ratio, status, raw_json
                 FROM events
                WHERE code5 = ?
                  AND event_type IN ('CONSOLIDATION', 'SPLIT')
                  AND (key_date_1 = ? OR key_date_2 = ?)
                ORDER BY rowid LIMIT 1""",
            (code, day, day),
        ).fetchone()
    return dict(row) if row else None


def action_prev_close(prev_close: float, event: dict | None) -> tuple[float, int]:
    """Adjust the old close for a simple ``old:new`` consolidation/split ratio.

    Returns ``(effective_prev_close, corp_action_suspect)``. Unknown or
    ambiguous ratios are deliberately marked suspect so scanners do not alert.
    """
    if not event:
        return prev_close, 0
    ratio = str(event.get("ratio") or "")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", ratio)]
    if len(nums) != 2 or nums[0] <= 0 or nums[1] <= 0:
        return prev_close, 1
    text = ratio.lower().replace(" ", "")
    if ":" in text or "/" in text or "=" in text or "對" in text:
        return prev_close * nums[0] / nums[1], 0
    if event.get("event_type") == "CONSOLIDATION" and ("合" in ratio or "合股" in ratio):
        return prev_close * nums[0] / nums[1], 0
    if event.get("event_type") == "SPLIT" and ("拆" in ratio or "股" in ratio):
        return prev_close * nums[0] / nums[1], 0
    return prev_close, 1


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

#!/usr/bin/env python
"""匯入 TGWebExporter 已存文字訊息；只讀 message_text，不碰 media。"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_rtss_alerts import COLUMNS
from stockscan.io_utils import today_hkt, write_csv
from stockscan.rtss_parser import parse_alert

HKT = ZoneInfo("Asia/Hong_Kong")
CHAT_KEY = "-2795969450"
DEFAULT_SOURCE = Path(r"C:\TGWebExporter\RTSS_Output\rtss_messages.sqlite")
RTSS_DIR = Path("data/rtss")


def _timestamp_date(value: str) -> date | None:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).astimezone(HKT).date()
    except (TypeError, ValueError, OverflowError, OSError):
        try:
            return datetime.fromisoformat(str(value)).astimezone(HKT).date()
        except (TypeError, ValueError):
            return None


def _rows_from_source(source: Path):
    if source.suffix.lower() in {".sqlite", ".db"}:
        with sqlite3.connect(source) as conn:
            query = "select chat_key, message_id, timestamp_text, message_text, source_url from messages where chat_key = ?"
            yield from conn.execute(query, (CHAT_KEY,))
    elif source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("chat_key", "")) == CHAT_KEY:
                    yield (row.get("chat_key"), row.get("message_id"), row.get("timestamp_text"),
                           row.get("message_text"), row.get("source_url", ""))
    else:
        raise ValueError(f"unsupported source format: {source}")


def import_backfill(source: Path, start: date, end: date) -> dict:
    grouped: dict[date, dict[str, dict]] = {}
    total = parsed = failed = 0
    min_seen = max_seen = None
    for chat_key, message_id, timestamp_text, message_text, source_url in _rows_from_source(source):
        msg_date = _timestamp_date(timestamp_text)
        if not msg_date:
            continue
        min_seen = msg_date if min_seen is None else min(min_seen, msg_date)
        max_seen = msg_date if max_seen is None else max(max_seen, msg_date)
        if not start <= msg_date <= end:
            continue
        total += 1
        parsed_row = parse_alert(message_text or "")
        if parsed_row["parse_failed"]:
            failed += 1
            continue
        parsed += 1
        parsed_row.update({
            "message_date": msg_date.isoformat(),
            "message_key": f"{chat_key}:{message_id}",
            "raw_text": str(message_text or "").strip(),
        })
        grouped.setdefault(msg_date, {})[parsed_row["message_key"]] = parsed_row

    for msg_date in sorted(grouped):
        path = RTSS_DIR / f"rtss_alerts_{msg_date:%Y%m%d}.csv"
        frame = pd.DataFrame(grouped[msg_date].values(), columns=COLUMNS)
        write_csv(frame.sort_values(["time", "code5"]), path)
    print(f"[rtss-backfill] source range={min_seen}..{max_seen}; in_range={total}; parsed={parsed}; parse_failed={failed}; days={len(grouped)}")
    return {"source_min": min_seen, "source_max": max_seen, "in_range": total,
            "parsed": parsed, "parse_failed": failed, "days": len(grouped)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--from", dest="from_date", type=date.fromisoformat, default=date(2025, 8, 29))
    ap.add_argument("--to", dest="to_date", type=date.fromisoformat, default=today_hkt())
    args = ap.parse_args()
    if not args.source.exists():
        raise SystemExit(f"source not found: {args.source}")
    import_backfill(args.source, args.from_date, args.to_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

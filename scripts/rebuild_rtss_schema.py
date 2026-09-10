"""用現有 RTSS raw／alert 檔重建新逐條 schema，唔讀 Telegram API。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_rtss_alerts import COLUMNS, RTSS_DIR, _write_metadata, write_daily_by_stock
from stockscan.io_utils import today_hkt, write_csv
from stockscan.rtss_parser import parse_alert


def rebuild_day(day: date) -> Path:
    source = RTSS_DIR / f"rtss_alerts_{day:%Y%m%d}.csv"
    raw_source = RTSS_DIR / f"raw_dom_{day:%Y%m%d}.jsonl"
    records: dict[str, dict] = {}
    if source.exists() and source.stat().st_size > 0:
        old = pd.read_csv(source, dtype=str, encoding="utf-8-sig")
        for row in old.to_dict("records"):
            text = str(row.get("raw_text") or "")
            parsed = parse_alert(text, row.get("date") or row.get("message_date") or day.isoformat(),
                                 row.get("msg_id") or row.get("message_key") or None)
            key = f"{parsed['code5']}|{parsed['alert_ts']}" if parsed["alert_ts"] else f"msg|{parsed['msg_id']}"
            records[key] = parsed
    if raw_source.exists():
        for line in raw_source.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed = parse_alert(row.get("raw_text", ""), row.get("message_date") or day.isoformat(),
                                 row.get("message_key") or None)
            key = f"{parsed['code5']}|{parsed['alert_ts']}" if parsed["alert_ts"] else f"msg|{parsed['msg_id']}"
            records[key] = parsed
    frame = pd.DataFrame(list(records.values()), columns=COLUMNS)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["code5", "alert_ts"], keep="last")
        frame = frame.sort_values(["alert_ts", "code5"], na_position="last").reset_index(drop=True)
    write_csv(frame, source)
    _write_metadata(frame, source)
    write_daily_by_stock(day, frame)
    return source


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", type=date.fromisoformat, default=date(2025, 8, 29))
    ap.add_argument("--to", dest="to_date", type=date.fromisoformat, default=today_hkt())
    args = ap.parse_args()
    if args.from_date > args.to_date:
        raise SystemExit("--from 不可晚於 --to")
    total = 0
    for offset in range((args.to_date - args.from_date).days + 1):
        rebuild_day(args.from_date + timedelta(days=offset))
        total += 1
    print(f"[rtss-rebuild] rebuilt {total} daily files: {args.from_date}..{args.to_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

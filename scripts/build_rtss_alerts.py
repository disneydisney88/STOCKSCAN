#!/usr/bin/env python
"""將 T1 raw DOM text 轉成 gitignored RTSS alert CSV。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stockscan.io_utils import today_hkt, write_csv
from stockscan.rtss_parser import parse_alert

RTSS_DIR = Path("data/rtss")
COLUMNS = [
    "msg_type", "code5", "name", "mcap", "turnover", "chg_pct",
    "last_price", "time", "count_today", "level_range", "parse_failed",
    "message_date", "message_key", "raw_text",
]


def build_day(day: date, raw_path: Path | None = None, out_path: Path | None = None) -> Path:
    raw_path = raw_path or RTSS_DIR / f"raw_dom_{day:%Y%m%d}.jsonl"
    out_path = out_path or RTSS_DIR / f"rtss_alerts_{day:%Y%m%d}.csv"
    records: dict[str, dict] = {}
    if out_path.exists():
        try:
            old = pd.read_csv(out_path, dtype={"code5": str}, encoding="utf-8-sig")
            for row in old.to_dict("records"):
                key = f"{str(row.get('code5', '')).zfill(5)}|{row.get('time', '')}"
                records[key] = row
        except (OSError, ValueError) as exc:
            print(f"[rtss-output] ignored unreadable existing CSV {out_path}: {exc}", file=sys.stderr)
    if raw_path.exists():
        for line_no, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                print(f"[rtss-output] ignored malformed raw line {raw_path}:{line_no}", file=sys.stderr)
                continue
            parsed = parse_alert(raw.get("raw_text", ""))
            parsed["message_date"] = raw.get("message_date") or day.isoformat()
            parsed["message_key"] = raw.get("message_key", "")
            key = f"{parsed.get('code5', '')}|{parsed.get('time', '')}"
            if key == "|":
                key = f"raw|{parsed.get('message_key', '')}"
            records[key] = parsed
    frame = pd.DataFrame(list(records.values()), columns=COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["time", "code5"], na_position="last").reset_index(drop=True)
    write_csv(frame, out_path)
    failed = int(frame["parse_failed"].sum()) if not frame.empty else 0
    print(f"[rtss-output] {day:%Y%m%d}: {len(frame)} alerts ({failed} parse_failed) -> {out_path}")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD；預設 today_hkt()")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--from", dest="from_date")
    ap.add_argument("--to", dest="to_date")
    args = ap.parse_args()
    if args.backfill:
        if not args.from_date or not args.to_date:
            raise SystemExit("--backfill 必須同時提供 --from 及 --to")
        start, end = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    else:
        start = end = date.fromisoformat(args.date) if args.date else today_hkt()
    if start > end:
        raise SystemExit("日期範圍無效")
    for offset in range((end - start).days + 1):
        build_day(start + timedelta(days=offset))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from stockscan.rtss_parser import clean_alert_text, parse_alert

RTSS_DIR = Path("data/rtss")
COLUMNS = [
    "msg_id", "alert_ts", "date", "time", "code5", "name", "msg_type",
    "count_today", "level_from", "level_to", "mcap", "mcap_raw", "turnover",
    "turnover_raw", "chg_pct", "last_price", "category", "raw_text", "parse_failed",
]


def build_day(day: date, raw_path: Path | None = None, out_path: Path | None = None,
              fresh: bool = False) -> Path:
    raw_path = raw_path or RTSS_DIR / f"raw_dom_{day:%Y%m%d}.jsonl"
    out_path = out_path or RTSS_DIR / f"rtss_alerts_{day:%Y%m%d}.csv"
    records: dict[str, dict] = {}
    if out_path.exists() and not fresh:
        try:
            old = pd.read_csv(out_path, dtype={"code5": str}, encoding="utf-8-sig")
            for row in old.to_dict("records"):
                row["raw_text"] = clean_alert_text(str(row.get("raw_text") or ""))
                if not row["raw_text"] or not str(row.get("code5") or "").strip():
                    continue
                key = f"{str(row.get('code5', '')).zfill(5)}|{row.get('alert_ts', '') or row.get('time', '')}"
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
            parsed = parse_alert(raw.get("raw_text", ""), raw.get("message_date") or day.isoformat(),
                                 raw.get("message_key") or None)
            key = f"{parsed.get('code5', '')}|{parsed.get('alert_ts', '')}"
            if key == "|":
                key = f"raw|{parsed.get('msg_id', '')}"
            records[key] = parsed
    frame = pd.DataFrame(list(records.values()), columns=COLUMNS)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["code5", "alert_ts"], keep="last")
        frame = frame.sort_values(["alert_ts", "code5"], na_position="last").reset_index(drop=True)
    write_csv(frame, out_path)
    _write_metadata(frame, out_path)
    write_daily_by_stock(day, frame)
    failed = int(frame["parse_failed"].sum()) if not frame.empty else 0
    print(f"[rtss-output] {day:%Y%m%d}: {len(frame)} alerts ({failed} parse_failed) -> {out_path}")
    return out_path


def _write_metadata(frame: pd.DataFrame, out_path: Path) -> None:
    values = pd.to_datetime(frame.get("alert_ts", pd.Series(dtype=str)), errors="coerce")
    valid = values.dropna()
    metadata = {
        "rows": len(frame),
        "earliest_alert_ts": valid.min().strftime("%Y-%m-%d %H:%M:%S") if not valid.empty else None,
        "latest_alert_ts": valid.max().strftime("%Y-%m-%d %H:%M:%S") if not valid.empty else None,
        "unique_key": ["code5", "alert_ts"],
    }
    try:
        out_path.with_suffix(".meta.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except PermissionError as exc:
        print(f"[rtss-output] warning: metadata locked, skipped {out_path}: {exc}", file=sys.stderr)


def write_daily_by_stock(day: date, frame: pd.DataFrame) -> Path:
    out_path = RTSS_DIR / f"rtss_daily_by_stock_{day:%Y%m%d}.csv"
    if frame.empty:
        summary = pd.DataFrame(columns=["code5", "name", "alert_count", "max_count_today",
                                       "first_ts", "last_ts", "max_chg_pct", "msg_types"])
    else:
        work = frame.copy()
        work["alert_ts"] = pd.to_datetime(work["alert_ts"], errors="coerce")
        work["chg_pct"] = pd.to_numeric(work["chg_pct"], errors="coerce")
        work["count_today"] = pd.to_numeric(work["count_today"], errors="coerce")
        summary = work.groupby("code5", as_index=False).agg(
            name=("name", "first"), alert_count=("alert_ts", "count"),
            max_count_today=("count_today", "max"), first_ts=("alert_ts", "min"),
            last_ts=("alert_ts", "max"), max_chg_pct=("chg_pct", "max"),
            msg_types=("msg_type", lambda s: ";".join(sorted(set(s.dropna().astype(str)))))
        )
    return write_csv(summary, out_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD；預設 today_hkt()")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--from", dest="from_date")
    ap.add_argument("--to", dest="to_date")
    ap.add_argument("--fresh", action="store_true", help="ignore existing alert CSV and rebuild from raw")
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
        build_day(start + timedelta(days=offset), fresh=args.fresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

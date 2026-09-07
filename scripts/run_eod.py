#!/usr/bin/env python
"""CLI：python scripts/run_eod.py [--date 2026-09-04] [--codes 1393,8483]
                [--workers 2] [--cache-only] [--no-intraday-after]
跑訊號 A；掃 2026-09-04 時自動同 RTSS fixture 對照。
--cache-only：零 API，純用 data/cache/daily/（回填／重算用）。"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stockscan.lb_client import LB, MissingCredentialsError
from stockscan.scan_eod import run


def main() -> int:
    ap = argparse.ArgumentParser(description="訊號 A：收市爆量榜")
    ap.add_argument("--date", help="YYYY-MM-DD（預設今日 HKT；週末自動退返上一個交易日）")
    ap.add_argument("--codes", help="只掃呢啲代號（5 位，逗號分開），debug 用")
    ap.add_argument("--workers", type=int, default=2, help="快取拉數線程數（預設 2）")
    ap.add_argument("--cache-only", action="store_true", help="零 API，純快取計算")
    ap.add_argument("--notify", action="store_true", help="推 Telegram（憑證喺 .env）")
    ap.add_argument("--dry-run", action="store_true", help="印出 Telegram 訊息唔發送")
    args = ap.parse_args()

    date_arg = _date.fromisoformat(args.date) if args.date else None
    codes = [c.strip() for c in args.codes.split(",")] if args.codes else None
    try:
        lb = None if args.cache_only else LB()
        df, meta = run(lb, date_arg, cache_only=args.cache_only,
                       codes=codes, workers=args.workers)
    except MissingCredentialsError as e:
        print(f"[run_eod] {e}", file=sys.stderr)
        return 2
    if df.empty:
        print("[run_eod] 今日冇命中（CSV 已寫，空表）。")
    else:
        cols = ["code5", "name", "close", "chg_pct", "turnover_day", "mcap_total", "ratio"]
        print(df[cols].to_string(index=False))
    if (args.notify or args.dry_run) and not df.empty:
        from stockscan.notify import send_eod_table

        send_eod_table(df, _date.fromisoformat(meta["scan_date"]), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

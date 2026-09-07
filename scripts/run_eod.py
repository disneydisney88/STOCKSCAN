#!/usr/bin/env python
"""CLI：python scripts/run_eod.py [--date 2026-09-04]
跑訊號 A；掃 2026-09-04 時自動同 RTSS fixture 對照。"""
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
    args = ap.parse_args()

    date_arg = _date.fromisoformat(args.date) if args.date else None
    try:
        lb = LB()
        df, meta = run(lb, date_arg)
    except MissingCredentialsError as e:
        print(f"[run_eod] {e}", file=sys.stderr)
        return 2
    if df.empty:
        print("[run_eod] 今日冇命中（CSV 已寫，空表）。")
    else:
        cols = ["code5", "name", "close", "chg_pct", "turnover_day", "mcap_total", "ratio"]
        print(df[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

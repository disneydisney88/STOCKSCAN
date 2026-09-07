#!/usr/bin/env python
"""P2 接口：批量對照 RTSS fixture。
今晚只有 09-04；之後有新 fixture（tests/fixtures/rtss_YYYYMMDD.csv）就：
    python scripts/compare_rtss.py --date 2026-09-04
    python scripts/compare_rtss.py --all      （掃晒所有 fixture）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import FIXTURE_DIR, RTSS_FIXTURE_DATE
from stockscan.scan_eod import compare_rtss


def main() -> int:
    ap = argparse.ArgumentParser(description="對照 RTSS fixture")
    ap.add_argument("--date", help="YYYYMMDD（單日）")
    ap.add_argument("--all", action="store_true", help="掃晒 tests/fixtures/rtss_*.csv")
    args = ap.parse_args()

    dates = []
    if args.all:
        dates = [p.stem.replace("rtss_", "") for p in sorted(FIXTURE_DIR.glob("rtss_*.csv"))]
    elif args.date:
        dates = [args.date.replace("-", "")]
    else:
        dates = [RTSS_FIXTURE_DATE]

    rc = 0
    for ymd in dates:
        radar = Path("data/eod") / f"radar_eod_{ymd}.csv"
        if not radar.exists():
            print(f"[compare] {ymd}：未有 radar CSV，跳過（先跑 run_eod --date）")
            rc = 1
            continue
        res = compare_rtss(radar, fixture_date=ymd)
        print(f"[compare] {ymd}：命中 {res['hit_count']}/{res['n_fixture']}"
              f"　漏={res['missing']}　多={res['extra']}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

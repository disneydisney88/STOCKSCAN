#!/usr/bin/env python
"""CLI：python scripts/run_intraday.py [--loop 60]
掃一次即市（訊號 B）；--loop 60 每 60 秒循環（本機用，Streamlit 唔用）。"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stockscan.lb_client import LB, MissingCredentialsError
from stockscan.scan_intraday import scan_once


def main() -> int:
    ap = argparse.ArgumentParser(description="訊號 B：即市急升異動掃一次")
    ap.add_argument("--loop", type=int, default=0, help="每隔 N 秒循環（0=只跑一次）")
    args = ap.parse_args()

    try:
        lb = LB()
    except MissingCredentialsError as e:
        print(f"[run_intraday] {e}", file=sys.stderr)
        return 2

    while True:
        try:
            alerts, near, meta = scan_once(lb)
        except MissingCredentialsError as e:
            print(f"[run_intraday] {e}", file=sys.stderr)
            return 2
        print(f"[run_intraday] {meta['scan_time']}　quoted={meta['quoted']} "
              f"pool={meta['pool']}　alert={meta['alerts']}　off_hours={meta['off_hours']}")
        if not alerts.empty:
            print(alerts.to_string(index=False))
        else:
            print("[run_intraday] 呢一輪冇新 alert。近門檻 top20：")
            if not near.empty:
                print(near.to_string(index=False))
        print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
        if not args.loop:
            break
        time.sleep(args.loop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

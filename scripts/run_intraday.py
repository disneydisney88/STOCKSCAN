#!/usr/bin/env python
"""CLI：python scripts/run_intraday.py [--loop 60] [--once]
訊號 B：即市急升＋爆量掃描。

--once（預設）：掃一次就出。
--loop N：每 N 秒一輪；只喺交易日 09:30–12:00、13:00–16:10 HKT 掃，
其餘時間（午休／收市後／假日）每 INTRA_POLL_SEC 秒檢查一次，唔會報錯。
Ctrl-C 安全退出（state 每輪落盤）。"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import INTRA_POLL_SEC, DISCLAIMER
from stockscan.calendar_hk import in_scan_session
from stockscan.lb_client import LB, MissingCredentialsError
from stockscan.scan_intraday import scan_once


def _sleep(seconds: int) -> None:
    """分段瞓，Ctrl-C 可以快啲走。"""
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(min(5, max(0, end - time.time())))


def main() -> int:
    ap = argparse.ArgumentParser(description="訊號 B：即市急升＋爆量")
    ap.add_argument("--loop", type=int, default=0,
                    help=f"每隔 N 秒一輪（0=只跑一次；建議 {INTRA_POLL_SEC}）")
    ap.add_argument("--once", action="store_true", help="只跑一輪（同 --loop 0）")
    args = ap.parse_args()
    loop = args.loop if args.loop else 0

    try:
        lb = LB()
    except MissingCredentialsError as e:
        print(f"[run_intraday] {e}", file=sys.stderr)
        return 2

    while True:
        if loop and not in_scan_session():
            now = time.strftime("%H:%M:%S")
            print(f"[run_intraday] {now} 非掃描時段（交易日 09:30–12:00／13:00–16:10 HKT），"
                  f"{INTRA_POLL_SEC}s 後再檢查。")
            _sleep(INTRA_POLL_SEC)
            continue
        try:
            alerts, near, meta = scan_once(lb, date.today())
        except MissingCredentialsError as e:
            print(f"[run_intraday] {e}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            raise
        print(f"[run_intraday] {meta['scan_time']}　quoted={meta['quoted']} "
              f"pool={meta['pool']}　alert={meta['alerts']}　off_hours={meta['off_hours']}　"
              f"{meta['elapsed_s']}s")
        if not alerts.empty:
            print(alerts.to_string(index=False))
        else:
            print("[run_intraday] 呢一輪冇新 alert。近門檻 top20（按升幅）：")
            if not near.empty:
                print(near.to_string(index=False))
        print(DISCLAIMER)
        if not loop or args.once:
            break
        _sleep(loop)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[run_intraday] Ctrl-C 離開；state 已喺每輪落盤。")

#!/usr/bin/env python
"""P2：回填 N 個交易日訊號 A → 逐日 radar CSV + radar_eod_panel.csv。

用法：python scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07
純快取模式（零 API）；交易日清單由快取日期聯盟推導（≥200 隻有 bar 嗰日先算交易日，
快取覆蓋唔到嘅日子會自動跳過並印警告）。"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CACHE_DIR, DISCLAIMER, EOD_DIR
from stockscan.io_utils import ensure_dirs, today_hkt, write_csv
from stockscan.scan_eod import OUT_COLUMNS, build_eod


def trading_days_from_cache(start: date, end: date, min_symbols: int = 200) -> list[date]:
    """快取日期聯盟：夠多隻有 bar 嘅日子先當交易日（停牌個別股唔算）。"""
    counts: Counter = Counter()
    for p in (CACHE_DIR / "daily").glob("*.csv"):
        try:
            df = pd.read_csv(p, usecols=["date"])
        except Exception:  # noqa: BLE001
            continue
        for d in df["date"]:
            counts[d] += 1
    days = []
    for d, n in sorted(counts.items()):
        if n >= min_symbols and start.isoformat() <= d <= end.isoformat():
            days.append(date.fromisoformat(d))
    return days


def main() -> int:
    ap = argparse.ArgumentParser(description="回填訊號 A 面板")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    ensure_dirs()
    days = trading_days_from_cache(start, end)
    if not days:
        print("[backfill] 快取入面搵唔到任何交易日——檢查 data/cache/daily/。")
        return 1
    print(f"[backfill] {start} → {end}：{len(days)} 個交易日（快取推導）："
          f"{days[0]} … {days[-1]}")

    panels: list[pd.DataFrame] = []
    counts: list[int] = []
    for d in days:
        df, meta = build_eod(None, d, cache_only=True)
        fname = f"radar_eod_{d:%Y%m%d}.csv"
        write_csv(df, EOD_DIR / fname)
        counts.append(len(df))
        if not df.empty:
            panel = df.copy()
            panel.insert(0, "scan_date", d.isoformat())
            panels.append(panel)
        print(f"[backfill] {d}：命中 {len(df)}（no_cache={meta['no_cache']}，"
              f"當日無bar={meta['no_bar_on_date']}）")

    panel_all = pd.concat(panels, ignore_index=True) if panels else pd.DataFrame()
    panel_path = EOD_DIR / "radar_eod_panel.csv"
    write_csv(panel_all, panel_path)
    print(f"[backfill] 面板 {len(panel_all)} 行 → {panel_path}")

    # ── 摘要統計（寫 stdout；HANDOVER §9 由呢度抄）──
    if counts:
        s = pd.Series(counts)
        print(f"[backfill] 每日上榜數：中位 {s.median():.0f}／最少 {s.min()}／最多 {s.max()}")
    if not panel_all.empty:
        top = panel_all["code5"].value_counts().head(10)
        print("[backfill] 上榜次數最多頭 10：")
        for code5, n in top.items():
            name = panel_all.loc[panel_all["code5"] == code5, "name"].iloc[0]
            print(f"  {code5} {name}：{n} 次")
        mc = pd.to_numeric(panel_all["mcap_total"], errors="coerce")
        print(f"[backfill] 市值 <3 億佔比：{(mc < 3e8).mean():.1%}")
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

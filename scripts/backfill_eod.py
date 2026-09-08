#!/usr/bin/env python
"""P2：回填 N 個交易日訊號 A → 逐日 radar CSV + radar_eod_panel.csv。

用法：python scripts/backfill_eod.py --start 2026-08-10 --end 2026-09-07
純快取模式（零 API）；交易日清單由快取日期聯盟推導（≥200 隻有 bar 嗰日先算交易日，
快取覆蓋唔到嘅日子會自動跳過並印警告）。"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
import re
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CACHE_DIR, DATA_DIR, DISCLAIMER, EOD_DIR
from stockscan.io_utils import ensure_dirs, today_hkt, write_csv
from stockscan.scan_eod import OUT_COLUMNS, build_eod
from stockscan.events import EVENTS_DB


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


def code5(value) -> str:
    match = re.search(r"(\d{1,5})", str(value))
    return match.group(1).zfill(5) if match else ""


def apply_historical_shares(panel: pd.DataFrame) -> pd.DataFrame:
    """Use the latest X0 filing at each scan date and flag uncertain mcap."""
    shares_path = DATA_DIR / "raw" / "shares_outstanding_panel_X0.csv"
    if panel.empty or not shares_path.exists():
        panel["mcap_unreliable"] = 1
        return panel
    shares = pd.read_csv(shares_path, encoding="utf-8-sig", dtype=object)
    shares["code5"] = shares["code"].map(code5)
    shares["shares_outstanding"] = pd.to_numeric(shares["shares_outstanding"], errors="coerce")
    shares["report_month"] = pd.to_datetime(shares["report_month"], errors="coerce")
    shares = shares.dropna(subset=["code5", "report_month", "shares_outstanding"])
    shares = shares.sort_values("report_month")
    panel = panel.copy()
    panel["_scan_dt"] = pd.to_datetime(panel["scan_date"])
    panel["_month"] = panel["_scan_dt"].values.astype("datetime64[M]")
    panel = pd.merge_asof(
        panel.sort_values("_scan_dt"),
        shares[["code5", "report_month", "shares_outstanding"]].sort_values("report_month"),
        left_on="_scan_dt", right_on="report_month", by="code5", direction="backward")
    fallback = pd.to_numeric(panel["mcap_total"], errors="coerce")
    old_close = pd.to_numeric(panel["close"], errors="coerce")
    panel["mcap_unreliable"] = panel["shares_outstanding"].isna().astype(int)
    if EVENTS_DB.exists():
        import sqlite3
        with sqlite3.connect(EVENTS_DB) as con:
            event_codes = {
                row[0] for row in con.execute(
                    """SELECT DISTINCT code5 FROM events
                       WHERE event_type IN ('CONSOLIDATION','SPLIT','PLACING','RIGHTS')
                         AND announce_date IS NOT NULL
                         AND announce_date <= ?""",
                    (panel["scan_date"].max(),),
                )
            }
        panel.loc[panel["code5"].isin(event_codes), "mcap_unreliable"] = 1
    panel["mcap_total"] = (old_close * panel["shares_outstanding"]).where(
        panel["shares_outstanding"].notna(), fallback).round()
    panel = panel.drop(columns=["_scan_dt", "_month", "report_month", "shares_outstanding"], errors="ignore")
    return panel.sort_values(["scan_date", "mcap_total"]).reset_index(drop=True)


def write_monthly_rtss_compare(panel: pd.DataFrame) -> pd.DataFrame:
    """Compare panel code/date pairs with RTSS's OCR daily summary by month."""
    path = DATA_DIR / "raw" / "RTSS_Detailed_Final.xlsx"
    rtss = pd.read_excel(path, sheet_name="每日摘要", usecols=["日期", "股票編號"])
    rtss["scan_date"] = pd.to_datetime(rtss["日期"], errors="coerce").dt.date.astype("string")
    rtss["code5"] = rtss["股票編號"].map(code5)
    rtss = rtss.dropna(subset=["scan_date"])
    ours = panel[["scan_date", "code5"]].drop_duplicates()
    rtss = rtss[["scan_date", "code5"]].drop_duplicates()
    merged = ours.merge(rtss, on=["scan_date", "code5"], how="outer", indicator=True)
    merged["month"] = merged["scan_date"].str[:7]
    out = merged.groupby("month").agg(
        ours=("_merge", lambda s: int((s != "right_only").sum())),
        rtss=("_merge", lambda s: int((s != "left_only").sum())),
        hits=("_merge", lambda s: int((s == "both").sum())),
        extra=("_merge", lambda s: int((s == "left_only").sum())),
        missing=("_merge", lambda s: int((s == "right_only").sum())),
    ).reset_index()
    out["hit_rate"] = (out["hits"] / out["rtss"].where(out["rtss"].gt(0), 1)).round(4)
    (DATA_DIR / "reports").mkdir(parents=True, exist_ok=True)
    write_csv(out, DATA_DIR / "reports" / "rtss_monthly_compare.csv")
    return out


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
    panel_full = apply_historical_shares(panel_all)
    panel_path = EOD_DIR / "radar_eod_panel_full.csv"
    write_csv(panel_full, panel_path)
    # Keep the legacy path for the existing Streamlit tab and downstream tools.
    write_csv(panel_full, EOD_DIR / "radar_eod_panel.csv")
    compare = write_monthly_rtss_compare(panel_full)
    print(f"[backfill] 面板 {len(panel_full)} 行 → {panel_path}")
    print(f"[backfill] RTSS 月度對照 {len(compare)} 個月 → data/reports/rtss_monthly_compare.csv")

    # ── 摘要統計（寫 stdout；HANDOVER §9 由呢度抄）──
    if counts:
        s = pd.Series(counts)
        print(f"[backfill] 每日上榜數：中位 {s.median():.0f}／最少 {s.min()}／最多 {s.max()}")
    if not panel_full.empty:
        top = panel_full["code5"].value_counts().head(10)
        print("[backfill] 上榜次數最多頭 10：")
        for code5, n in top.items():
            name = panel_full.loc[panel_full["code5"] == code5, "name"].iloc[0]
            print(f"  {code5} {name}：{n} 次")
        mc = pd.to_numeric(panel_full["mcap_total"], errors="coerce")
        print(f"[backfill] 市值 <3 億佔比：{(mc < 3e8).mean():.1%}")
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

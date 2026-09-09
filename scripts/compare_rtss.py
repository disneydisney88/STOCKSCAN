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




def _load_rtss_daily_summary() -> pd.DataFrame:
    """F2：RTSS 每日摘要（OCR 清洗版）→ 去重（date, code5）＋只留代表市值 <10 億。"""
    import pandas as pd

    from config import DATA_DIR
    xl = DATA_DIR / "raw" / "RTSS_Detailed_Final.xlsx"
    df = pd.read_excel(xl, sheet_name="每日摘要", dtype=str)
    df = df.dropna(subset=["日期", "股票編號"]).copy()
    df["date"] = df["日期"].str.strip()
    df["code5"] = df["股票編號"].astype(str).str.extract(r"(\d{4,5})")[0].str.zfill(5)
    df = df.dropna(subset=["code5"])
    # 代表市值（億）：<10 億細市值榜先算（大市值榜唔係我哋口徑）
    mcap_yi = pd.to_numeric(df.get("代表市值（億）"), errors="coerce")
    df = df[mcap_yi < 10]
    df = df.drop_duplicates(subset=["date", "code5"])
    return df[["date", "code5"]]


def run_monthly(start: str = "2026-04", end: str = "2026-07") -> pd.DataFrame:
    """F2 重做 M3 對照：RTSS 每日摘要（去重＋細市值）vs 我哋面板，按月計。"""
    import pandas as pd

    from config import DATA_DIR, EOD_DIR

    panel_path = EOD_DIR / "radar_eod_panel_full.csv"
    panel_path = panel_path if panel_path.exists() else EOD_DIR / "radar_eod_panel.csv"
    ours = pd.read_csv(panel_path, dtype={"code5": str}, encoding="utf-8-sig")
    ours = ours[["scan_date", "code5"]].drop_duplicates()
    ours.columns = ["date", "code5"]
    ours = ours[ours["date"].str[:7].between(start, end)]
    rtss = _load_rtss_daily_summary()
    rtss = rtss[rtss["date"].str[:7].between(start, end)]
    # F2 補充：RTSS Telegram 假期／週末照出，只對返我哋面板有嘅交易日
    rtss = rtss[rtss["date"].isin(set(ours["date"]))]

    rows = []
    for month in sorted(rtss["date"].str[:7].unique()):
        r = set(rtss.loc[rtss["date"].str[:7] == month, "code5"])
        o = set(ours.loc[ours["date"].str[:7] == month, "code5"])
        # 按月用 (date, code5) pair 計先準
        rp = set(map(tuple, rtss.loc[rtss["date"].str[:7] == month, ["date", "code5"]].values))
        op = set(map(tuple, ours.loc[ours["date"].str[:7] == month, ["date", "code5"]].values))
        hits = len(rp & op)
        rows.append({
            "month": month, "ours_pairs": len(op), "rtss_pairs": len(rp),
            "hits": hits, "extra": len(op - rp), "missing": len(rp - op),
            "hit_rate": round(hits / max(len(rp), 1), 4),
        })
    out = pd.DataFrame(rows)
    dest = DATA_DIR / "reports" / "rtss_monthly_compare_v2.csv"
    out.to_csv(dest, index=False, encoding="utf-8-sig")
    print(out.to_string(index=False))
    print(f"→ {dest}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="對照 RTSS fixture")
    ap.add_argument("--date", help="YYYYMMDD（單日）")
    ap.add_argument("--all", action="store_true", help="掃晒 tests/fixtures/rtss_*.csv")
    ap.add_argument("--monthly", action="store_true", help="F2：RTSS 每日摘要 vs 面板按月對照（04→07）")
    args = ap.parse_args()
    if args.monthly:
        run_monthly("2026-04", "2026-07")
        return 0

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

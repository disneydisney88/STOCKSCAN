#!/usr/bin/env python
"""P5 B1：春江鴨——爆量上榜 ＋ 貨源異動證據（券商射倉 ±5 日；CCASS Top10 待 M7 通後自動補）。

輸出 data/reports/spring_duck_YYYYMMDD.csv：面板欄 + top10_pct + has_broker_shot + spring_duck_flag。
spring_duck_flag=1 = 上榜日 ±5 日有券商射倉（或者 CCASS Top10 資料存在）。
只列數字旗標，唔構成投資建議。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, EOD_DIR
from stockscan.io_utils import today_hkt, write_csv


def build() -> pd.DataFrame:
    panel = pd.read_csv(EOD_DIR / "radar_eod_panel_full.csv",
                        dtype={"code5": str}, encoding="utf-8-sig")
    # 補上 panel 之後嘅新日子（例如 09-08 單日 radar）
    covered = set(panel["scan_date"])
    extra = []
    for f in sorted(EOD_DIR.glob("radar_eod_2*.csv")):
        d = f.name.replace("radar_eod_", "").replace(".csv", "")
        if len(d) == 8 and d not in covered:
            df = pd.read_csv(f, dtype={"code5": str}, encoding="utf-8-sig")
            if not df.empty:
                df.insert(0, "scan_date", f"{d[:4]}-{d[4:6]}-{d[6:]}")
                extra.append(df)
    if extra:
        panel = pd.concat([panel] + extra, ignore_index=True)

    if "has_broker_shot" not in panel.columns:
        panel["has_broker_shot"] = 0
    panel["has_broker_shot"] = pd.to_numeric(panel["has_broker_shot"], errors="coerce").fillna(0)
    if "ccass_top10_pct_t2" not in panel.columns:
        panel["ccass_top10_pct_t2"] = None
    cc = pd.to_numeric(panel["ccass_top10_pct_t2"], errors="coerce")
    panel["spring_duck_flag"] = ((panel["has_broker_shot"] == 1) | cc.notna()).astype(int)
    panel["top10_pct"] = cc
    cols = ["scan_date", "code5", "name", "close", "chg_pct", "turnover_day",
            "mcap_total", "ratio", "top10_pct", "has_broker_shot", "spring_duck_flag"]
    return panel[[c for c in cols if c in panel.columns]]


def main() -> int:
    df = build()
    dest = DATA_DIR / "reports" / f"spring_duck_{today_hkt():%Y%m%d}.csv"
    write_csv(df, dest)
    flagged = df[df["spring_duck_flag"] == 1]
    print(f"[spring_duck] {len(df)} 行，flag=1 共 {len(flagged)} 行 "
          f"（{len(flagged) / max(len(df), 1) * 100:.1f}%）→ {dest}")
    if not flagged.empty:
        recent = flagged.sort_values("scan_date").groupby("code5").tail(1).tail(10)
        for _, r in recent.iterrows():
            print(f"  {r['scan_date']} {r['code5']} {r['name']}")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

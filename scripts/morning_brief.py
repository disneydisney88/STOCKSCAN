#!/usr/bin/env python
"""P5 B3：三訊號匯合 morning brief——「爆量 + 貨源 + 事件前置」齊中嘅股。

輸出 data/reports/morning_brief_YYYYMMDD.md（Actions 收市後跑；只列名單旗標，
唔排名唔推薦）。使用 spring_duck.py／l_shape.py 嘅 build()。
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, EOD_DIR, DISCLAIMER
from stockscan.io_utils import today_hkt, write_csv


def latest_radar() -> pd.DataFrame:
    files = sorted(EOD_DIR.glob("radar_eod_2*.csv"))
    files = [f for f in files if "panel" not in f.name]
    if not files:
        return pd.DataFrame()
    df = pd.read_csv(files[-1], dtype={"code5": str}, encoding="utf-8-sig")
    df.insert(0, "scan_date", files[-1].stem.replace("radar_eod_", ""))
    return df


def main() -> int:
    from scripts.l_shape import build as lshape_build
    from scripts.spring_duck import build as duck_build

    d = today_hkt()
    radar = latest_radar()
    if radar.empty:
        print("[brief] 冇 radar CSV——先跑 run_eod.py")
        return 1
    duck = duck_build()
    lshape = lshape_build()

    duck_flags = set(duck.loc[duck["spring_duck_flag"] == 1, "code5"]) if not duck.empty else set()
    lshape_stage = {} if lshape.empty else {
        r["code5"]: r["l_shape_stage"] for _, r in lshape.iterrows()}

    radar["spring_duck"] = radar["code5"].isin(duck_flags).astype(int)
    radar["l_shape_stage"] = radar["code5"].map(lshape_stage).fillna("")
    radar["三訊號齊"] = ((radar["spring_duck"] == 1)
                     & (radar["l_shape_stage"] == "GO_等表演")).astype(int)

    scan_date = radar["scan_date"].iloc[0]
    md = [f"# STOCKSCAN Morning Brief {scan_date}",
          "",
          f"當日爆量榜 {len(radar)} 隻；春江鴨（貨源）旗 {int(radar['spring_duck'].sum())}；"
          f"L 型前置（事件）旗 {int((radar['l_shape_stage'] == 'GO_等表演').sum())}；"
          f"三訊號齊 {int(radar['三訊號齊'].sum())} 隻。",
          "",
          "| code5 | 名稱 | close | 升跌% | 成交額 | 市值 | 倍數 | 春江鴨 | L型 |",
          "|---|---|---:|---:|---:|---:|---:|:-:|:-:|"]
    for _, r in radar.iterrows():
        md.append(
            f"| {r['code5']} | {r['name']} | {r['close']} | {r['chg_pct']} | "
            f"{pd.to_numeric(r['turnover_day']) / 1e6:,.1f}M | "
            f"{pd.to_numeric(r['mcap_total']) / 1e8:,.2f}億 | {r['ratio']} | "
            f"{'✅' if r['spring_duck'] else '—'} | {r['l_shape_stage'] or '—'} |")
    md += ["", "> 只供學術研究及風險分析，不構成投資建議。只列名單旗標，唔排名唔推薦。"]
    dest = DATA_DIR / "reports" / f"morning_brief_{d:%Y%m%d}.md"
    dest.write_text("\n".join(md), encoding="utf-8")
    print(f"[brief] → {dest}")
    print("\n".join(md[:14]))
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

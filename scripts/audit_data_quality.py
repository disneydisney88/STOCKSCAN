#!/usr/bin/env python
"""P4 Z4：數據質量審計（只記錄，唔改數）。

1. radar_eod_panel_full.csv 嘅 mcap_unreliable 佔比＋按月分佈
2. 種子檔 08-31「市值」vs 面板 2026-08-31 mcap_total：差 >30% 嘅股票列表
3. 即市 alert 嘅 suspect 旗統計
產出：stdout + data/reports/data_quality_audit_YYYYMMDD.csv（第 2 項明細）
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, EOD_DIR, INTRADAY_DIR
from stockscan.io_utils import parse_cn_number, today_hkt, write_csv


def main() -> int:
    lines: list[str] = []

    def say(msg: str) -> None:
        print(msg)
        lines.append(msg)

    # 1) mcap_unreliable 按月
    panel = read_panel = pd.DataFrame()
    for name in ("radar_eod_panel_full.csv", "radar_eod_panel.csv"):
        p = EOD_DIR / name
        if p.exists():
            panel = pd.read_csv(p, dtype={"code5": str}, encoding="utf-8-sig")
            say(f"[1] 面板檔：{name}（{len(panel)} 行）")
            break
    if not panel.empty and "mcap_unreliable" in panel.columns:
        panel["month"] = panel["scan_date"].astype(str).str[:7]
        g = panel.groupby("month")["mcap_unreliable"].agg(["sum", "count"])
        g["unreliable_pct"] = (g["sum"] / g["count"] * 100).round(1)
        say(f"mcap_unreliable 總數：{int(g['sum'].sum())}/{len(panel)} 行 "
            f"（{g['sum'].sum() / len(panel) * 100:.1f}%）")
        say("按月：")
        for month, r in g.iterrows():
            say(f"  {month}: {int(r['sum'])}/{int(r['count'])} ({r['unreliable_pct']}%)")
    else:
        say("[1] 面板冇 mcap_unreliable 欄——跳過")

    # 2) 種子 08-31 市值 vs 面板 2026-08-31 mcap_total
    seed_path = DATA_DIR / "universe_seed_20260831.csv"
    day = panel[panel["scan_date"] == "2026-08-31"] if not panel.empty else pd.DataFrame()
    if seed_path.exists() and not day.empty:
        seed = pd.read_csv(seed_path, encoding="utf-8-sig", dtype=str)
        seed["code5"] = seed["編號"].str.strip().str[:5]
        seed["seed_mcap"] = seed["市值"].map(parse_cn_number)
        m = day.merge(seed[["code5", "seed_mcap"]], on="code5", how="inner")
        m = m.dropna(subset=["seed_mcap", "mcap_total"])
        m["diff_pct"] = (pd.to_numeric(m["mcap_total"]) / m["seed_mcap"] - 1).abs() * 100
        big = m[m["diff_pct"] > 30].sort_values("diff_pct", ascending=False)
        say(f"[2] 08-31 對照：可比 {len(m)} 隻，差 >30% 共 {len(big)} 隻 "
            f"（{len(big) / max(len(m), 1) * 100:.1f}%）")
        if not big.empty:
            big2 = big.copy()
            big2["原因猜測"] = big2["diff_pct"].apply(
                lambda x: "合股/拆股（~整數倍）" if x > 60 else "配股/供股/內資股攤薄或股數口徑差異")
            out = big2[["code5", "name", "seed_mcap", "mcap_total", "diff_pct", "原因猜測"]]
            dest = DATA_DIR / "reports" / f"data_quality_audit_{today_hkt():%Y%m%d}.csv"
            write_csv(out, dest)
            say(f"明細 → {dest}")
            for _, r in big2.head(10).iterrows():
                say(f"  {r['code5']} {r['name']} 種子={r['seed_mcap']:.0f} "
                    f"面板={r['mcap_total']:.0f} 差={r['diff_pct']:.0f}% {r['原因猜測']}")
    else:
        say("[2] 種子檔或面板 08-31 缺——跳過")

    # 3) 即市 alert suspect 旗
    alerts = pd.read_csv(INTRADAY_DIR / f"alerts_{today_hkt():%Y%m%d}.csv",
                         encoding="utf-8-sig") \
        if (INTRADAY_DIR / f"alerts_{today_hkt():%Y%m%d}.csv").exists() else pd.DataFrame()
    say(f"[3] 今日即市 alert：{len(alerts)} 條")
    if not alerts.empty:
        for col in ("corp_action_suspect", "resumption_suspect", "price_gap_suspect"):
            if col in alerts.columns:
                say(f"  {col}=1：{int(pd.to_numeric(alerts[col], errors='coerce').fillna(0).sum())} 條")

    dest = DATA_DIR / "reports" / f"data_quality_audit_{today_hkt():%Y%m%d}.txt"
    dest.write_text("\n".join(lines), encoding="utf-8")
    print(f"審計全文 → {dest}")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

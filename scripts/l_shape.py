#!/usr/bin/env python
"""P5 B2：L 型候選——事件前置（賣殼/換主完成、未見後續配股供股，等表演）。

定義（只列旗標）：過去 180 日內有 GO 或 TRANSFER_MB（轉主板/換主類），
之後未見 PLACING／RIGHTS → l_shape_stage = GO_等表演；
有後續配供 → GO_已配供。交叉 L 型研究 xlsx 待 KL 放 data/raw（未放，純 events.db 版）。
輸出 data/reports/l_shape_candidates_YYYYMMDD.csv。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from stockscan.events import events_after
from stockscan.io_utils import today_hkt, write_csv


def build(universe_codes: set[str] | None = None) -> pd.DataFrame:
    con = pd.read_csv(EOD_PANEL, dtype={"code5": str}, encoding="utf-8-sig") \
        if Path(EOD_PANEL).exists() else pd.DataFrame()
    codes = set(con["code5"]) if not con.empty else (universe_codes or set())
    today = today_hkt()
    rows = []
    for code in sorted(codes):
        evs = events_after(code, today - timedelta(days=180), 180)
        gov = [e for e in evs if e["event_type"] in ("GO", "TRANSFER_MB")]
        if not gov:
            continue
        gov.sort(key=lambda e: e["announce_date"])
        last = gov[-1]
        follow = [e for e in evs
                  if e["event_type"] in ("PLACING", "RIGHTS")
                  and e["announce_date"] >= (last["announce_date"] or "")]
        rows.append({
            "code5": code,
            "name": last.get("name") or "",
            "event_type": last["event_type"],
            "last_event_date": last["announce_date"],
            "days_since": (today - date.fromisoformat(last["announce_date"])).days
            if last["announce_date"] else "",
            "has_follow_up_raise": int(bool(follow)),
            "l_shape_stage": "GO_已配供" if follow else "GO_等表演",
        })
    return pd.DataFrame(rows)


EOD_PANEL = DATA_DIR / "eod" / "radar_eod_panel_full.csv"


def main() -> int:
    df = build()
    dest = DATA_DIR / "reports" / f"l_shape_candidates_{today_hkt():%Y%m%d}.csv"
    write_csv(df, dest)
    stage2 = df[df["l_shape_stage"] == "GO_等表演"] if not df.empty else df
    print(f"[l_shape] 候選 {len(df)} 隻，其中「GO_等表演」{len(stage2)} 隻 → {dest}")
    if not stage2.empty:
        for _, r in stage2.sort_values("days_since").head(10).iterrows():
            print(f"  {r['code5']} {r['name']} {r['last_event_date']} "
                  f"（{r['days_since']} 日前）")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

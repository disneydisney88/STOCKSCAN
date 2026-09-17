#!/usr/bin/env python
"""P6b PART 2：由 Turso（直連，繞開 Render）抽 CCASS 集中度，對齊做成 GO 預示器特徵。

誠實紅線：
- CCASS 日期係結算日（T+2 口徑）——特徵 cutoff 用 scan_date 之前 2 個**交易日**
  （面板交易日曆），結算日紀錄晚過 cutoff 唔准用，防未來函數。
- `SUSPECT_DENOMINATOR`／`exclude_from_analysis` 紀錄照列旗標，唔靜靜剔除。
- 覆蓋唔到（未 warm／窗口冇早過 cutoff 嘅紀錄）一律 `unknown`，唔當 0。

輸出 data/reports/ccass_concentration_features.csv：
  code5, scan_date, ccass_top10_pct, ccass_top5_pct, ccass_top10_delta,
  ccass_window_days, ccass_asof_date, ccass_suspect_denominator,
  ccass_top10_pct_known, concentration_rising
（concentration_rising：delta > +1pp＝1，delta < −1pp＝0，中間/未知＝unknown）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stockscan.ccass_turso import concentration_series, fetch_stock_payloads  # noqa: E402
from stockscan.io_utils import today_hkt, write_csv  # noqa: E402

PANEL = ROOT / "data" / "eod" / "radar_eod_panel_full.csv"
REPORTS = ROOT / "data" / "reports"
LAG_TRADING_DAYS = 2
RISING_PP = 1.0


def trading_cutoffs(scan_dates: list[str]) -> dict[str, str]:
    """scan_date → 2 個交易日之前嘅日子（用面板全局交易日曆）。"""
    cal = sorted(set(scan_dates))
    pos = {d: i for i, d in enumerate(cal)}
    out = {}
    for d in scan_dates:
        i = pos.get(d, -1)
        out[d] = cal[i - LAG_TRADING_DAYS] if i >= LAG_TRADING_DAYS else ""
    return out


def build(panel_path: Path = PANEL) -> Path:
    panel = pd.read_csv(panel_path, dtype={"code5": str}, encoding="utf-8-sig")
    panel["code5"] = panel["code5"].str.zfill(5)
    pairs = panel[["code5", "scan_date"]].drop_duplicates().reset_index(drop=True)
    cutoffs = trading_cutoffs(sorted(pairs["scan_date"].unique()))

    codes = sorted(pairs["code5"].unique())
    payloads = fetch_stock_payloads(codes)
    series_by_code = {c: concentration_series(p) for c, p in payloads.items()}

    rows = []
    for r in pairs.itertuples(index=False):
        cutoff = cutoffs[r.scan_date]
        recs = series_by_code.get(r.code5) or []
        usable = [x for x in recs
                  if x["date"] and cutoff and x["date"] <= cutoff]
        row = {
            "code5": r.code5, "scan_date": r.scan_date,
            "ccass_asof_date": "", "ccass_top10_pct": "", "ccass_top5_pct": "",
            "ccass_top10_delta": "", "ccass_window_days": "",
            "ccass_suspect_denominator": "",
            "ccass_top10_pct_known": 0, "concentration_rising": "",
        }
        if usable:  # records 係由新到舊
            latest, oldest = usable[0], usable[-1]
            t10 = pd.to_numeric(pd.Series([latest["top10_pct"]]), errors="coerce").iloc[0]
            row.update({
                "ccass_asof_date": latest["date"],
                "ccass_top10_pct": round(float(t10), 4) if pd.notna(t10) else "",
                "ccass_top5_pct": latest["top5_pct"] if latest["top5_pct"] is not None else "",
                "ccass_suspect_denominator": int(latest["suspect_denominator"]),
                "ccass_top10_pct_known": int(pd.notna(t10)),
            })
            if len(usable) >= 2:
                o10 = pd.to_numeric(pd.Series([oldest["top10_pct"]]), errors="coerce").iloc[0]
                if pd.notna(t10) and pd.notna(o10):
                    delta = float(t10) - float(o10)
                    row["ccass_top10_delta"] = round(delta, 4)
                    row["ccass_window_days"] = len(usable)
                    row["concentration_rising"] = (
                        1 if delta > RISING_PP else (0 if delta < -RISING_PP else 0.5))
                    # 0.5＝窗口內基本無變（±1pp 內），照列數字唔歸邊
        rows.append(row)

    feat = pd.DataFrame(rows)
    dest = write_csv(feat, REPORTS / "ccass_concentration_features.csv")
    known = int(feat["ccass_top10_pct_known"].sum())
    rising = int((feat["concentration_rising"] == 1).sum())
    print(f"[ccass_feat] pairs={len(feat)} stocks_in_cache={len(series_by_code)}/{len(codes)} "
          f"top10_known={known}（{known / len(feat):.1%}）rising={rising}")
    print(f"[ccass_feat] cutoff=scan_date−{LAG_TRADING_DAYS}交易日；輸出 {dest}")
    print(f"[ccass_feat] today={today_hkt()}；未知覆蓋一律 unknown，唔當 0")
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=Path, default=PANEL)
    args = ap.parse_args()
    build(args.panel)

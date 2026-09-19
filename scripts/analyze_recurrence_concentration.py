#!/usr/bin/env python
"""P6c 反覆上榜 × 集中度交叉（規格書 §6 延伸，KL 09-12/09-19 問題）。

問題：「越上榜嘅股，貨源係越歸邊定越散？」——用 recurrence_YYYYMMDD.csv
（上榜次數）join ccass_concentration_features.csv（Webb dump of-issued Top10%），
按（上榜次數組 × 集中度 bin）出 led_to_go / led_to_perform 率。只列數字。

輸出 data/reports/recurrence_concentration_cross.csv。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stockscan.io_utils import today_hkt, write_csv  # noqa: E402

REPORTS = ROOT / "data" / "reports"


def main() -> int:
    rec_files = sorted(REPORTS.glob("recurrence_????????.csv"))
    if not rec_files:
        raise SystemExit("未有 recurrence_*.csv——先跑 scripts/analyze_recurrence.py")
    rec = pd.read_csv(rec_files[-1], dtype={"code5": str}, encoding="utf-8-sig")
    feat = pd.read_csv(REPORTS / "ccass_concentration_features.csv",
                       dtype={"code5": str}, encoding="utf-8-sig")

    # 每股一股數 anchor 概念：集中度取該股 dump 源中位數（2025H2 窗口）
    per_stock = (feat.dropna(subset=["dump_top10_pct_of_issued"])
                 .groupby("code5")["dump_top10_pct_of_issued"].median()
                 .rename("dump_top10_median_pct").reset_index())
    m = rec.merge(per_stock, on="code5", how="left")

    x = m["dump_top10_median_pct"]
    m["conc_bin"] = pd.cut(x, [-np.inf, 20, 40, 60, np.inf],
                           labels=["<20%", "20-40%", "40-60%", ">=60%"]) \
        .astype(object).where(x.notna(), "unknown")
    app = pd.to_numeric(m["total_appearances"], errors="coerce").fillna(1)
    m["app_bin"] = pd.cut(app, [0, 1, 4, np.inf], labels=["單次", "2-4次", ">=5次"]) \
        .astype(str)

    rows = []
    for outcome, col in (("led_to_go", "fu_go"), ("led_to_perform", "ret_t60")):
        for (ab, cb), g in m.groupby(["app_bin", "conc_bin"], observed=True):
            if outcome == "led_to_go":
                rate = pd.to_numeric(g["fu_go"], errors="coerce").mean()
                n = int(g["fu_go"].notna().sum())
            else:
                t60 = pd.to_numeric(g["ret_t60"], errors="coerce")
                t60 = t60[t60.notna() & (pd.to_numeric(
                    g.loc[t60.index, "ret_t60_est"], errors="coerce").fillna(1) == 0)]
                rate = (t60 > 0).mean() if len(t60) else np.nan
                n = len(t60)
            rows.append({"app_bin": ab, "conc_bin": str(cb), "outcome": outcome,
                         "n": n, "rate": round(float(rate), 4) if pd.notna(rate) else "",
                         "note": "insufficient_sample" if n < 20 else ""})
    out = pd.DataFrame(rows)
    dest = write_csv(out, REPORTS / "recurrence_concentration_cross.csv")
    print(f"[rec_x_conc] {len(out)} 行 → {dest}")
    show = out[(out["outcome"] == "led_to_go") & (out["n"] >= 20)]
    print(show.to_string(index=False))
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

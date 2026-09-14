#!/usr/bin/env python
"""P6 反覆上榜分析（規格書 §6，KL 09-12 特別提）。

每隻股：總上榜次數、連續 run（下一個交易日又上榜算同一 run）、
最長間隔（日曆日）、跨季／跨年重現；再接追蹤簿簿A嘅
has_capital_action／fu_*／ret_t20／ret_t60（ret 屬首次入冊口徑），
睇「反覆上榜 vs 有冇財技 vs 長線 ret」。只列數字，唔落結論。

輸出 data/reports/recurrence_YYYYMMDD.csv（YYYYMMDD = today_hkt）。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR  # noqa: E402
from stockscan.io_utils import today_hkt, write_csv  # noqa: E402

EOD_PANEL = DATA_DIR / "eod" / "radar_eod_panel_full.csv"
REPORTS = DATA_DIR / "reports"

RET_COLS = ["has_capital_action", "fu_go", "fu_rights", "fu_placing",
            "fu_consolidation", "fu_cb", "first_action_type",
            "ret_t20", "ret_t20_est", "ret_t60", "ret_t60_est"]


def _runs(dates: list[str], calendar: list[str]) -> int:
    """連續 run 數：外現日期喺全局交易日曆上貼住上一個上榜日就同 run。"""
    if not dates:
        return 0
    pos = {d: i for i, d in enumerate(calendar)}
    runs = 1
    for a, b in zip(dates[:-1], dates[1:]):
        if pos.get(b, -1) - pos.get(a, -10**9) != 1:
            runs += 1
    return runs


def main() -> int:
    panel = pd.read_csv(EOD_PANEL, dtype={"code5": str}, encoding="utf-8-sig")
    panel["code5"] = panel["code5"].str.zfill(5)
    calendar = sorted(panel["scan_date"].unique())

    rows = []
    for code, g in panel.sort_values("scan_date").groupby("code5"):
        dates = sorted(g["scan_date"].unique())
        gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days
                for a, b in zip(dates[:-1], dates[1:])]
        quarters = {pd.Timestamp(d).quarter for d in dates}
        q_labels = {f"{pd.Timestamp(d).year}Q{pd.Timestamp(d).quarter}" for d in dates}
        years = {pd.Timestamp(d).year for d in dates}
        rows.append({
            "code5": code,
            "name": g["name"].dropna().iloc[0] if g["name"].notna().any() else "",
            "total_appearances": len(dates),
            "distinct_runs": _runs(dates, calendar),
            "longest_gap_days": max(gaps) if gaps else 0,
            "first_scan_date": dates[0],
            "last_scan_date": dates[-1],
            "n_quarters": len(q_labels),
            "spans_quarters": int(len(q_labels) >= 2),
            "n_years": len(years),
            "spans_year": int(len(years) >= 2),
        })
    rec = pd.DataFrame(rows)

    # 接簿A：有冇財技 + 首次入冊 ret
    tf_path = REPORTS / "tracking_first.csv"
    if tf_path.exists():
        tf = pd.read_csv(tf_path, dtype={"code5": str}, encoding="utf-8-sig")
        rec = rec.merge(tf[["code5", "name"] + RET_COLS], on="code5",
                        how="left", suffixes=("", "_tf"))
        if "name_tf" in rec.columns:
            rec["name"] = rec["name"].fillna(rec["name_tf"])
            rec = rec.drop(columns=["name_tf"])

    dest = write_csv(rec, REPORTS / f"recurrence_{today_hkt():%Y%m%d}.csv")
    print(f"[recurrence] {len(rec)} 隻 → {dest}")
    multi = rec[rec["total_appearances"] >= 2]
    print(f"[recurrence] 上榜 ≥2 次：{len(multi)} 隻（{len(multi)/len(rec):.1%}）；"
          f"≥5 次：{int((rec['total_appearances'] >= 5).sum())} 隻；"
          f"跨季：{int(rec['spans_quarters'].sum())} 隻；跨年：{int(rec['spans_year'].sum())} 隻")
    for grp_name, grp in (("單次", rec[rec["total_appearances"] == 1]),
                          ("2-4次", rec[(rec["total_appearances"] >= 2) & (rec["total_appearances"] <= 4)]),
                          ("≥5次", rec[rec["total_appearances"] >= 5])):
        for ca, ca_label in ((1, "有財技"), (0, "冇財技")):
            sub = grp[grp["has_capital_action"] == ca]
            r20 = pd.to_numeric(sub["ret_t20"], errors="coerce")
            r20 = r20[pd.to_numeric(sub["ret_t20_est"], errors="coerce").fillna(1) == 0]
            if len(r20):
                print(f"[recurrence] {grp_name}×{ca_label}: n={len(r20)}　"
                      f"t20中位={r20.median():+.4f}%　勝率={(r20 > 0).mean():.4f}")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

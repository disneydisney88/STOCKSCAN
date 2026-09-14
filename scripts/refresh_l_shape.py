#!/usr/bin/env python
"""P6 L 型名單季度版本對比（規格書 §4）。

L 型候選＝已上榜股中，過去 180 日有 GO／換主（TRANSFER_MB），
之後未見 PLACING／RIGHTS（等表演）——沿用 scripts/l_shape.py B2 定義，
改做「as-of 季度末」快照，5 個季度版本 l_shape_{Q}.csv +
l_shape_version_diff.csv（新入／畢業_開始配供／跌出）。

交叉核對：data/raw/ 兩隻 KL L 型研究 xlsx（主表「代號」欄）標 in_kl_xlsx。
可重跑（每季首個交易日）；全部本地計，只列數字，唔構成投資建議。
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR  # noqa: E402
from scripts.build_tracking import load_events_by_code  # noqa: E402
from stockscan.io_utils import today_hkt, write_csv  # noqa: E402

EOD_PANEL = DATA_DIR / "eod" / "radar_eod_panel_full.csv"
REPORTS = DATA_DIR / "reports"
GO_TYPES = ("GO", "TRANSFER_MB")
RAISE_TYPES = ("PLACING", "RIGHTS")
WINDOW_DAYS = 180

QUARTERS = [("2025Q3", date(2025, 9, 30)), ("2025Q4", date(2025, 12, 31)),
            ("2026Q1", date(2026, 3, 31)), ("2026Q2", date(2026, 6, 30)),
            ("2026Q3", date(2026, 9, 30))]

KL_XLSX = [DATA_DIR / "raw" / "20260718_Lshape_合併主表_79隻_框架已填.xlsx",
           DATA_DIR / "raw" / "L型研究I版_最終版_GO兌現機制_20260731.xlsx"]


def kl_xlsx_codes() -> set[str]:
    """由 KL L 型研究 xlsx 抽「代號」欄 5 位代號（讀唔到就空集＋警告，唔炸）。"""
    codes: set[str] = set()
    for f in KL_XLSX:
        if not f.exists():
            print(f"[l_shape] 警告：交叉核對 xlsx 唔存在：{f.name}")
            continue
        try:
            df = pd.read_excel(f, sheet_name=None, header=None, dtype=str)
        except Exception as e:  # noqa: BLE001——核對用，失敗唔阻主流程
            print(f"[l_shape] 警告：讀唔到 {f.name}（{e!r}），跳過交叉核對")
            continue
        for sheet in df.values():
            for col in sheet.columns:
                for v in sheet[col].dropna().astype(str):
                    m = re.fullmatch(r"\d{5}(?:\.HK)?", v.strip())
                    if m:
                        codes.add(m.group(0)[:5])
    return codes


def candidates_asof(as_of: date, universe: pd.DataFrame,
                    events_by_code: dict[str, list[dict]]) -> pd.DataFrame:
    """as-of 快照：universe（code5, name）入面符合 L 型候選定義嘅股。"""
    start = (as_of - timedelta(days=WINDOW_DAYS)).isoformat()
    end = as_of.isoformat()
    rows = []
    for r in universe.itertuples(index=False):
        evs = [e for e in events_by_code.get(r.code5, [])
               if start <= str(e["announce_date"]) <= end]
        gov = sorted((e for e in evs if e["event_type"] in GO_TYPES),
                     key=lambda e: str(e["announce_date"]))
        if not gov:
            continue
        last = gov[-1]
        last_d = str(last["announce_date"])
        follow = [e for e in evs if e["event_type"] in RAISE_TYPES
                  and str(e["announce_date"]) >= last_d]
        if follow:  # 已開始配供＝唔再係「等表演」候選
            continue
        rows.append({
            "code5": r.code5,
            "name": r.name if pd.notna(r.name) else (last.get("name") or ""),
            "last_go_type": last["event_type"],
            "last_go_date": last_d,
            "days_since_go": (as_of - date.fromisoformat(last_d)).days,
            "in_kl_xlsx": 0,
        })
    return pd.DataFrame(rows)


def raise_between(code: str, d1: str, d2: str,
                  events_by_code: dict[str, list[dict]]) -> str:
    """(d1, d2] 內第一個 PLACING／RIGHTS 公佈日（畢業證據），冇就空字串。"""
    evs = [e for e in events_by_code.get(code, [])
           if e["event_type"] in RAISE_TYPES and d1 < str(e["announce_date"]) <= d2]
    return min((str(e["announce_date"]) for e in evs), default="")


def main() -> int:
    panel = pd.read_csv(EOD_PANEL, dtype={"code5": str}, encoding="utf-8-sig")
    panel["code5"] = panel["code5"].str.zfill(5)
    events_by_code = load_events_by_code()
    kl_codes = kl_xlsx_codes()
    today = today_hkt()

    versions: dict[str, pd.DataFrame] = {}
    asofs: dict[str, date] = {}
    for qname, qend in QUARTERS:
        as_of = min(qend, today)
        asofs[qname] = as_of
        uni = panel[pd.to_datetime(panel["scan_date"]) <= pd.Timestamp(as_of)][
            ["code5", "name"]].drop_duplicates("code5")
        cand = candidates_asof(as_of, uni, events_by_code)
        if not cand.empty:
            cand["in_kl_xlsx"] = cand["code5"].isin(kl_codes).astype(int)
            cand = cand.sort_values(["in_kl_xlsx", "days_since_go"],
                                    ascending=[False, True]).reset_index(drop=True)
        versions[qname] = cand
        dest = write_csv(cand, REPORTS / f"l_shape_{qname}.csv")
        print(f"[l_shape] {qname}（as-of {as_of}）已上榜 {len(uni)} 隻 → 候選 {len(cand)} → {dest}")

    # 版本對比：新入／畢業_開始配供／跌出
    diffs = []
    for (q_prev, _), (q_cur, _) in zip(QUARTERS[:-1], QUARTERS[1:]):
        prev, cur = versions[q_prev], versions[q_cur]
        prev_codes = set(prev["code5"]) if not prev.empty else set()
        cur_codes = set(cur["code5"]) if not cur.empty else set()
        d1, d2 = asofs[q_prev].isoformat(), asofs[q_cur].isoformat()
        names = {r["code5"]: r["name"] for _, r in
                 pd.concat([prev, cur]).drop_duplicates("code5").iterrows()}
        for code in sorted(cur_codes - prev_codes):
            diffs.append({"from_q": q_prev, "to_q": q_cur, "code5": code,
                          "name": names.get(code, ""), "change_type": "新入",
                          "evidence_date": "", "note": ""})
        for code in sorted(prev_codes - cur_codes):
            rd = raise_between(code, d1, d2, events_by_code)
            if rd:
                diffs.append({"from_q": q_prev, "to_q": q_cur, "code5": code,
                              "name": names.get(code, ""), "change_type": "畢業_開始配供",
                              "evidence_date": rd, "note": "期內有 PLACING/RIGHTS 公佈"})
            else:
                diffs.append({"from_q": q_prev, "to_q": q_cur, "code5": code,
                              "name": names.get(code, ""), "change_type": "跌出",
                              "evidence_date": "", "note": "GO 老化出 180 日窗或未再上榜"})
    diff_df = pd.DataFrame(diffs)
    dest = write_csv(diff_df, REPORTS / "l_shape_version_diff.csv")
    if not diff_df.empty:
        print("[l_shape] 版本對比：", diff_df.groupby(["from_q", "to_q", "change_type"])
              .size().to_dict())
    print(f"[l_shape] version_diff {len(diff_df)} 行 → {dest}")
    print("[l_shape] 下次 refresh：每季首個交易日（跑 python scripts/refresh_l_shape.py）")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

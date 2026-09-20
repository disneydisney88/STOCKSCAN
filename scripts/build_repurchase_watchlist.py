#!/usr/bin/env python
"""P6c 回購×歸邊 watchlist：回購中 × CCASS Top10 歸邊 × 上榜/L型 交叉清單。

三重證據邏輯（只列數字旗標，唔構成投資建議）：
- 回購中：repurchase_daily（研究站同花順快照）內最近有回購紀錄
- 歸邊：CCASS Top10 ≥60%（dump of-issued / warm cache 兩源取最新可得）
- 近月上榜：面板有上榜日

注意：回購快照係 2026-09-19 一次性抓取（1,000 筆，疑似 API 截斷），
「回購中」定義以快照內最新回購日距快照日 ≤45 日計；歷史回購史未有。
輸出 data/reports/buyback_concentrated_watchlist.csv
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stockscan.io_utils import today_hkt, write_csv  # noqa: E402

REPORTS = ROOT / "data" / "reports"
DB = ROOT / "data" / "events.db"
FEATURES = REPORTS / "ccass_concentration_features.csv"
PANEL = ROOT / "data" / "eod" / "radar_eod_panel_full.csv"
CONCENTRATED_PCT = 60.0
RECENT_DAYS = 45


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rp = pd.read_sql_query(
        "SELECT code5, name, repurchase_date, shares, amount_hkd, ytd_pct_of_issued "
        "FROM repurchase_daily", con, dtype={"code5": str})
    con.close()
    if rp.empty:
        print("[watchlist] repurchase_daily 係空——先跑 import_dt_events.py")
        return 1
    rp["code5"] = rp["code5"].str.zfill(5)
    rp["repurchase_date"] = pd.to_datetime(rp["repurchase_date"], errors="coerce")
    ref = rp["repurchase_date"].max()  # 快照內最新回購日＝「今日」代理
    agg = rp.groupby("code5").agg(
        name=("name", "first"),
        rep_n=("repurchase_date", "count"),
        rep_last=("repurchase_date", "max"),
        rep_shares_sum=("shares", "sum"),
        rep_ytd_pct_max=("ytd_pct_of_issued", "max"),
    ).reset_index()
    agg["回購中"] = ((ref - agg["rep_last"]).dt.days <= RECENT_DAYS).astype(int)

    # Top10 最新可得（warm cache 優先，dump of-issued 次之）
    feat = pd.read_csv(FEATURES, dtype={"code5": str}, encoding="utf-8-sig")
    feat["cc10"] = pd.to_numeric(feat.get("ccass_top10_pct"), errors="coerce")
    feat["dump_raw"] = pd.to_numeric(feat.get("dump_top10_pct_of_issued_raw"), errors="coerce")
    feat["d0"] = pd.to_datetime(feat.get("dump_asof_date"), errors="coerce")
    top_rows = []
    for code, g in feat.groupby("code5"):
        w = g[g["cc10"].notna()]
        if len(w):
            w = w[w["cc10"].notna()].sort_values("scan_date")
            top_rows.append({"code5": code, "top10": float(w["cc10"].iloc[-1]),
                             "top10_src": "warm_cache", "top10_date": str(w["scan_date"].iloc[-1])})
            continue
        w = g[g["dump_raw"].notna()]
        if len(w):
            w = w.sort_values("scan_date")
            top_rows.append({"code5": code, "top10": float(w["dump_raw"].iloc[-1]),
                             "top10_src": "dump_of_issued", "top10_date": str(w["scan_date"].iloc[-1])})
    top = pd.DataFrame(top_rows)
    top["歸邊"] = (top["top10"] >= CONCENTRATED_PCT).astype(int)

    panel = pd.read_csv(PANEL, dtype={"code5": str}, encoding="utf-8-sig")
    app = panel.groupby("code5").agg(
        app_n=("scan_date", "count"), last_scan=("scan_date", "max")).reset_index()
    app["code5"] = app["code5"].str.zfill(5)

    w = agg.merge(top, on="code5", how="left").merge(app, on="code5", how="left")
    w["近月上榜"] = w["last_scan"].notna().astype(int)
    # L 型階段（最新季度）
    lq = sorted(REPORTS.glob("l_shape_20*_Q*.csv"))
    lmap = {}
    if lq:
        ldf = pd.read_csv(lq[-1], dtype={"code5": str}, encoding="utf-8-sig")
        if "l_shape_stage" in ldf.columns:
            lmap = dict(zip(ldf["code5"].str.zfill(5), ldf["l_shape_stage"]))
    w["L型階段"] = w["code5"].map(lmap).fillna("")
    w["歸邊"] = w["歸邊"].fillna(0).astype(int)
    w["綜合證據數"] = (w["回購中"] + w["歸邊"] + w["近月上榜"]).astype(int)

    out = w[(w["回購中"] == 1) & (w["歸邊"] == 1)].copy()
    out["近30日上榜"] = out["last_scan"].fillna("")
    out = out.sort_values(["綜合證據數", "rep_ytd_pct_max"], ascending=[False, False])
    out = out[["code5", "name", "rep_n", "rep_last", "rep_ytd_pct_max", "top10",
               "top10_src", "top10_date", "app_n", "last_scan", "L型階段", "綜合證據數"]]
    dest = write_csv(out, REPORTS / "buyback_concentrated_watchlist.csv")
    print(f"[watchlist] 回購中 {int(agg['回購中'].sum())} 隻｜歸邊 {int(top['歸邊'].sum())} 隻｜"
          f"回購×歸邊交集 {len(out)} 隻（近30日上榜 {int(out['last_scan'].notna().sum())} 隻）→ {dest}")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
DUMP_DB = Path(r"C:\Users\klcho\Downloads\ccass251227\webb_extract_panel\webb_subset.db")
# dump 源路徑：舊位（Downloads）被清（09-19 事故）。新 dump 抽完放 _data/ 或設定
# WEBB_DUMP_DAILYLOG 環境變數；冇檔案就自動跳過 dump 源（features 靠 git 存檔版本）
import os as _os
DUMP_CSV = Path(_os.getenv(
    "WEBB_DUMP_DAILYLOG",
    str(ROOT / "_data" / "webb_extract_panel" / "dailylog.csv")))
X0_SHARES = ROOT / "data" / "raw" / "shares_outstanding_panel_X0.csv"
LAG_TRADING_DAYS = 2
RISING_PP = 1.0


def _load_dump_dailylog() -> dict[str, pd.DataFrame]:
    """Webb 17GB dump 抽出嘅 dailylog.csv（已過濾面板 universe）：{code5: df[date, c10]}。

    2025-04-01 → 2025-12-24 逐日；c10 = Top10 CCASS 參與者持股合計（股數）。
    % 口徑用 of-issued（÷ X0 月度已發行股數），唔估 CCASS 總額語義。
    注意：要讀匯出嘅 dailylog.csv（過濾版），唔好讀 db 個 dailylog 表——
    個表入面係全交所 9.6M 行，非 universe issue 嘅 code 欄對照唔可靠。"""
    if not DUMP_CSV.exists():
        print(f"[ccass_feat] dump csv 唔存在，跳過 dump 源：{DUMP_CSV}")
        return {}
    dl = pd.read_csv(DUMP_CSV, dtype={"code": str}, encoding="utf-8-sig")
    dl["code5"] = dl["code"].astype(str).str.zfill(5)
    dl["date"] = dl["atDate"].astype(str)
    dl["c10"] = pd.to_numeric(dl["c10"], errors="coerce")
    out = {}
    for code, g in dl[dl["c10"].notna()].groupby("code5"):
        out[code] = g.sort_values("date")[["date", "c10"]].reset_index(drop=True)
    return out


def _load_x0_shares() -> pd.DataFrame:
    """逐日已發行股數：任務 X1 產出 `RTSS\\codex\\shares_outstanding_daily.csv`
    （671,880 行，2025-05-02→2026-09-01，OK/pre_history/no_data 口徑）。

    逐日股數令 of-issued % 喺合股/拆股前後都一致（c10 同股數同日同口徑），
    汰除單一快照 anchor 嘅污染問題。fallback：universe.csv 單一快照。"""
    daily = Path(r"G:\我的雲端硬碟\RTSS\codex\shares_outstanding_daily.csv")
    if daily.exists():
        s = pd.read_csv(daily, dtype={"code": str}, encoding="utf-8-sig")
        s = s[(s.get("status") == "OK") & s["shares_outstanding"].notna()]
        s["code5"] = s["code"].astype(str).str.zfill(5)
        s["shares"] = pd.to_numeric(s["shares_outstanding"], errors="coerce")
        s = s[s["shares"] > 0]
        return s.set_index(["code5", "date"])["shares"]
    uni = pd.read_csv(ROOT / "data" / "universe.csv", dtype={"code5": str},
                      encoding="utf-8-sig")
    uni = uni[uni["code5"].notna()].copy()
    uni["code5"] = uni["code5"].str.zfill(5)
    uni["shares"] = pd.to_numeric(uni["total_shares"], errors="coerce")
    return uni[["code5", "shares"]].drop_duplicates("code5").set_index("code5")["shares"]


def _issued_for(x0: pd.Series, code: str, scan_date: str):
    """c10 紀錄當日嘅已發行股數（逐日首選；單一快照 fallback 時 scan_date 無關）。"""
    try:
        v = x0.get((code, scan_date))
    except (KeyError, TypeError):
        v = None
    if v is None or pd.isna(v) or v <= 0:
        try:
            v = x0.get(code)  # fallback：Series 無 MultiIndex（單一快照）
        except Exception:
            v = None
    return float(v) if v is not None and pd.notna(v) and v > 0 else None


def _load_gap_events() -> dict[str, list[str]]:
    """events.db CONSOLIDATION/SPLIT 嘅生效日（key_date_1→2→announce fallback），按 code5。"""
    import sqlite3
    db = ROOT / "data" / "events.db"
    if not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT code5, COALESCE(NULLIF(key_date_1,''), NULLIF(key_date_2,''), announce_date) "
        "FROM events WHERE event_type IN ('CONSOLIDATION','SPLIT') "
        "AND COALESCE(NULLIF(key_date_1,''), NULLIF(key_date_2,''), announce_date) IS NOT NULL"
    ).fetchall()
    con.close()
    out: dict[str, list[str]] = {}
    for code, d in rows:
        out.setdefault(str(code).zfill(5), []).append(str(d))
    return out


def trading_cutoffs(scan_dates: list[str]) -> dict[str, str]:
    """scan_date → 2 個交易日之前嘅日子（用面板全局交易日曆）。"""
    cal = sorted(set(scan_dates))
    pos = {d: i for i, d in enumerate(cal)}
    out = {}
    for d in scan_dates:
        i = pos.get(d, -1)
        out[d] = cal[i - LAG_TRADING_DAYS] if i >= LAG_TRADING_DAYS else ""
    return out


def _load_holdings_daily() -> dict[str, dict[str, float]]:
    """Turso `holdings_daily` → {code5: {date: top10%_of_ccass}}。

    自己計：每股每日最大 10 個持倉 ÷ CCASS 總額（of-CCASS 口徑，同 webb
    records 口徑唔同，所以只做參考欄，唔入 predictor bin）。"""
    from stockscan.ccass_turso import _client

    per_code: dict[str, dict[str, float]] = {}
    with _client() as client:
        rs = client.execute(
            "SELECT code, data_date, holding_shares FROM holdings_daily "
            "ORDER BY code, data_date")
        cur_code, cur_date, top10, total = None, None, [], 0.0

        def flush():
            if cur_code and cur_date and total > 0:
                per_code.setdefault(cur_code, {})[cur_date] = round(
                    sum(top10) / total * 100.0, 4)

        for row in rs.rows:
            code, d, shares = str(row[0]), str(row[1]), float(row[2] or 0)
            if (code, d) != (cur_code, cur_date):
                flush()
                cur_code, cur_date, top10, total = code, d, [], 0.0
            top10.append(shares)
            total += shares
        flush()
    return per_code


def build(panel_path: Path = PANEL) -> Path:
    panel = pd.read_csv(panel_path, dtype={"code5": str}, encoding="utf-8-sig")
    panel["code5"] = panel["code5"].str.zfill(5)
    pairs = panel[["code5", "scan_date"]].drop_duplicates().reset_index(drop=True)
    cutoffs = trading_cutoffs(sorted(pairs["scan_date"].unique()))

    codes = sorted(pairs["code5"].unique())
    payloads = fetch_stock_payloads(codes)
    series_by_code = {c: concentration_series(p) for c, p in payloads.items()}
    hd_by_code = _load_holdings_daily()
    dump_by_code = _load_dump_dailylog()
    x0 = _load_x0_shares()
    gap_events = _load_gap_events()
    print(f"[ccass_feat] dump 源：{len(dump_by_code)} 隻有 dailylog；universe 股數 {len(x0)} 隻")

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
            "hd_top10_pct_of_ccass": "", "hd_asof_date": "", "hd_top10_delta": "",
            "dump_asof_date": "", "dump_c10_shares": "", "dump_issued_shares": "",
            "dump_top10_pct_of_issued": "", "dump_top10_pct_of_issued_raw": "",
            "dump_top10_delta_shares": "", "dump_window_days": "",
            "dump_concentration_rising": "", "dump_corp_action_in_window": 0,
            "dump_issued_missing": 0,
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
        # 參考欄：holdings_daily 自己計嘅 of-CCASS top10（口徑唔同，唔入 bin）
        hd = hd_by_code.get(r.code5) or {}
        hd_use = sorted(d for d in hd if cutoff and d <= cutoff)
        if hd_use:
            new, old = hd[hd_use[-1]], hd[hd_use[0]]
            row["hd_asof_date"] = hd_use[-1]
            row["hd_top10_pct_of_ccass"] = new
            if len(hd_use) >= 2:
                row["hd_top10_delta"] = round(new - old, 4)
        # 主力源：Webb dump dailylog（of-issued 口徑，2025-04-01→12-24 逐日）
        dg = dump_by_code.get(r.code5)
        dump_use = dg[dg["date"] <= cutoff] if (dg is not None and cutoff) else None
        if dump_use is not None and len(dump_use):
            last, first = dump_use.iloc[-1], dump_use.iloc[0]
            row["dump_asof_date"] = last["date"]
            row["dump_c10_shares"] = int(last["c10"])
            # 逐日股數（任務 X1）：c10 同股數同日同口徑，合股前後一致
            issued = _issued_for(x0, r.code5, last["date"])
            if issued:
                pct = last["c10"] / issued * 100.0
                row["dump_issued_shares"] = int(issued)
                row["dump_top10_pct_of_issued_raw"] = round(pct, 4)
                if len(dump_use) >= 2 and first["c10"]:
                    row["dump_top10_delta_shares"] = int(last["c10"] - first["c10"])
                    row["dump_window_days"] = len(dump_use)
                    issued0 = _issued_for(x0, r.code5, first["date"])
                    gaps = [d for d in gap_events.get(r.code5, [])
                            if first["date"] < d <= "2026-09-07"]
                    row["dump_corp_action_in_window"] = int(bool(gaps))
                    if issued0 and 0.1 <= pct <= 100.0:
                        pct0 = first["c10"] / issued0 * 100.0
                        row["dump_top10_pct_of_issued"] = round(pct, 4)
                        delta = pct - pct0  # 兩端各自用當日股數，% 直接可比
                        row["dump_concentration_rising"] = (
                            1 if delta > RISING_PP else
                            (0 if delta < -RISING_PP else 0.5))
            else:
                row["dump_issued_missing"] = 1  # 有 c10 冇股數——照列，唔估 %
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

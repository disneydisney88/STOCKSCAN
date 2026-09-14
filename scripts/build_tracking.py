#!/usr/bin/env python
"""P6 追蹤簿：每股由上榜嗰刻起追 t+5/10/20/60 價格變化（規格書 §1–§3）。

簿 A tracking_first.csv——每隻股只計首次上榜；簿 B tracking_each.csv——每個
（code5, scan_date）獨立一筆。入冊價兩個都記：entry_close（面板收市）＋
entry_intraday（暫用同日 close 做 eod_proxy，將來有 daemon 即市數據先補真值）。

有財技 vs 冇財技：events.db 上榜日後 180 日內 GO/供股/配股/合股/CB 任一。
合股／拆股生效日跌喺回報窗口內 → 該 ret 標 _est=1（跳空令 ret 假）；
summary 只對非 _est 行計中位／勝率，_est 行另計 n_est。
缺價格標 price_missing=1，唔准當 0。全部本地計（M2 快取＋events.db）。

輸出 data/reports/tracking_first.csv / tracking_each.csv / tracking_summary.csv。
只列數字，唔落買賣結論。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR  # noqa: E402
from stockscan.io_utils import today_hkt, write_csv  # noqa: E402

EOD_PANEL = DATA_DIR / "eod" / "radar_eod_panel_full.csv"
CACHE_DIR = DATA_DIR / "cache" / "daily"
REPORTS = DATA_DIR / "reports"

HORIZONS = (5, 10, 20, 60)
FU_TYPES = {"GO": "fu_go", "RIGHTS": "fu_rights", "PLACING": "fu_placing",
            "PLACING_AGENT": "fu_placing", "CONSOLIDATION": "fu_consolidation",
            "CB": "fu_cb"}
GAP_TYPES = ("CONSOLIDATION", "SPLIT")


def _effective_date(ev: dict) -> str:
    """跳空用生效日：key_date_1 → key_date_2 → announce_date（後兩者只係 fallback）。"""
    for k in ("key_date_1", "key_date_2", "announce_date"):
        v = str(ev.get(k) or "").strip()
        if v and v != "None":
            return v
    return ""


def load_events_by_code() -> dict[str, list[dict]]:
    """events.db 一次過入 memory（3.5k 行），避免逐股開 DB。"""
    import sqlite3
    with sqlite3.connect(DATA_DIR / "events.db") as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT event_type, code5, name, announce_date, key_date_1,
                      key_date_2, ratio, status
                 FROM events
                WHERE announce_date IS NOT NULL AND announce_date != ''
                ORDER BY code5, announce_date, rowid""").fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["code5"], []).append(dict(r))
    return out


def rets_for_entry(cache: pd.DataFrame | None, scan_date: str,
                   entry_close: float) -> tuple[dict, int, int]:
    """由 entry_close 計收市對收市 ret_tN／max/min_ret_20。

    回傳 (rets, days_available, price_missing)。price_missing=1 表示 entry 日
    唔喺快取（停牌或快取缺口），tN 用 entry 日之後第一個有價格日頂住並已標 flag。
    """
    rets = {f"ret_t{n}": np.nan for n in HORIZONS}
    rets.update({"max_ret_20": np.nan, "min_ret_20": np.nan})
    if cache is None or cache.empty or not np.isfinite(entry_close):
        return rets, 0, 1
    dates = cache["date"].tolist()
    closes = cache["close"].to_numpy(dtype=float)
    i = int(np.searchsorted(dates, scan_date, side="left"))
    price_missing = 0 if (i < len(dates) and dates[i] == scan_date) else 1
    days_available = max(0, len(dates) - 1 - i)
    for n in HORIZONS:
        j = i + n
        if j < len(dates):
            rets[f"ret_t{n}"] = (closes[j] / entry_close - 1.0) * 100.0
    fwd = closes[i + 1:i + 21]
    if len(fwd):
        rets["max_ret_20"] = float((fwd.max() / entry_close - 1.0) * 100.0)
        rets["min_ret_20"] = float((fwd.min() / entry_close - 1.0) * 100.0)
    return rets, days_available, price_missing


def est_flags(events: list[dict], scan_date: str,
              horizon_dates: dict[int, str]) -> dict[str, int]:
    """合股／拆股生效日跌喺（scan_date, tN_date] 窗口 → 該 ret 標 _est=1。"""
    gaps = [(_effective_date(e)) for e in events
            if e["event_type"] in GAP_TYPES]
    flags = {f"ret_t{n}_est": 0 for n in HORIZONS}
    flags.update({"max_ret_20_est": 0, "min_ret_20_est": 0})
    for g in gaps:
        if not g or g <= scan_date:
            continue
        for n in HORIZONS:
            tdate = horizon_dates.get(n, "")
            if tdate and g <= tdate:
                flags[f"ret_t{n}_est"] = 1
        t20 = horizon_dates.get(20, "")
        if t20 and g <= t20:
            flags["max_ret_20_est"] = 1
            flags["min_ret_20_est"] = 1
    return flags


def fu_flags(events: list[dict], scan_date: str,
             window_days: int = 180) -> dict:
    """上榜日後 180 日內 GO/供股/配股/合股/CB 任一 → has_capital_action=1。"""
    from datetime import timedelta
    end = (date.fromisoformat(scan_date) + timedelta(days=window_days)).isoformat()
    win = [e for e in events
           if scan_date <= str(e["announce_date"]) <= end
           and e["event_type"] in FU_TYPES]
    flags = {v: 0 for v in ("fu_go", "fu_rights", "fu_placing",
                            "fu_consolidation", "fu_cb")}
    first_type, first_days = "", ""
    if win:
        for e in win:  # 已按 announce_date, rowid 排序
            flags[FU_TYPES[e["event_type"]]] = 1
        first = win[0]
        first_type = first["event_type"]
        first_days = (date.fromisoformat(str(first["announce_date"]))
                      - date.fromisoformat(scan_date)).days
    return {"has_capital_action": int(bool(win)), **flags,
            "first_action_type": first_type, "first_action_days": first_days}


def build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = pd.read_csv(EOD_PANEL, dtype={"code5": str}, encoding="utf-8-sig")
    panel = panel[panel["code5"].notna()].copy()
    panel["code5"] = panel["code5"].str.zfill(5)
    panel = panel.sort_values(["code5", "scan_date"]).reset_index(drop=True)
    panel["appearance_seq"] = panel.groupby("code5").cumcount() + 1
    first_day = panel.groupby("code5")["scan_date"].transform("min")
    panel["days_since_first"] = (
        pd.to_datetime(panel["scan_date"]) - pd.to_datetime(first_day)).dt.days

    events_by_code = load_events_by_code()
    cache_memo: dict[str, pd.DataFrame | None] = {}

    rows: list[dict] = []
    for r in panel.itertuples(index=False):
        code = r.code5
        scan_date = str(r.scan_date)
        if code not in cache_memo:
            p = CACHE_DIR / f"{code}.csv"
            cache_memo[code] = pd.read_csv(
                p, dtype={"date": str}) if p.exists() else None
        cache = cache_memo[code]

        entry_close = float(r.close) if pd.notna(r.close) else np.nan
        if cache is not None and not np.isfinite(entry_close):
            dates = cache["date"].tolist()
            i = int(np.searchsorted(dates, scan_date, side="left"))
            if i < len(dates) and dates[i] == scan_date:
                entry_close = float(cache["close"].iloc[i])

        evs = events_by_code.get(code, [])
        rets, days_avail, price_missing = rets_for_entry(cache, scan_date, entry_close)

        # 各 horizon 實際用嘅快取日（俾 est 窗口判斷用）
        horizon_dates: dict[int, str] = {}
        if cache is not None and not cache.empty:
            dates = cache["date"].tolist()
            i = int(np.searchsorted(dates, scan_date, side="left"))
            for n in HORIZONS:
                j = i + n
                if j < len(dates):
                    horizon_dates[n] = dates[j]

        row = {
            "code5": code,
            "name": r.name if pd.notna(getattr(r, "name", "")) else "",
            "scan_date": scan_date,
            "appearance_seq": int(r.appearance_seq),
            "days_since_first": int(r.days_since_first),
            "entry_close": round(entry_close, 6) if np.isfinite(entry_close) else "",
            "entry_intraday": round(entry_close, 6) if np.isfinite(entry_close) else "",
            "entry_intraday_note": "eod_proxy",
            "price_missing": price_missing,
            "days_available": days_avail,
            **rets,
        }
        for k, v in rets.items():
            row[k] = round(v, 4) if np.isfinite(v) else ""
        row.update(est_flags(evs, scan_date, horizon_dates))
        row.update(fu_flags(evs, scan_date))
        rows.append(row)

    each = pd.DataFrame(rows)
    first = each[each["appearance_seq"] == 1].copy()
    summary = build_summary(first, each)
    return first, each, summary


def _is_est(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int) == 1


def build_summary(first: pd.DataFrame, each: pd.DataFrame) -> pd.DataFrame:
    out = []
    groups = [("all", lambda d: pd.Series(True, index=d.index)),
              ("with_ca", lambda d: d["has_capital_action"] == 1),
              ("without_ca", lambda d: d["has_capital_action"] == 0),
              ("fu_go", lambda d: d["fu_go"] == 1),
              ("fu_rights", lambda d: d["fu_rights"] == 1),
              ("fu_placing", lambda d: d["fu_placing"] == 1),
              ("fu_consolidation", lambda d: d["fu_consolidation"] == 1),
              ("fu_cb", lambda d: d["fu_cb"] == 1)]
    for book, df in (("first", first), ("each", each)):
        for gname, mask in groups:
            sub = df[mask(df)]
            for n in HORIZONS:
                ret = pd.to_numeric(sub[f"ret_t{n}"], errors="coerce")
                est = _is_est(sub[f"ret_t{n}_est"]) if f"ret_t{n}_est" in sub else pd.Series(False, index=sub.index)
                clean = ret[ret.notna() & ~est]
                out.append({
                    "book": book, "group": gname, "horizon": f"t{n}",
                    "n_total": int(ret.notna().sum()),
                    "n_clean": int(len(clean)),
                    "n_est": int((ret.notna() & est).sum()),
                    "median_ret_pct": round(float(clean.median()), 4) if len(clean) else "",
                    "win_rate": round(float((clean > 0).mean()), 4) if len(clean) else "",
                })
    return pd.DataFrame(out)


def main() -> int:
    first, each, summary = build()
    p1 = write_csv(first, REPORTS / "tracking_first.csv")
    p2 = write_csv(each, REPORTS / "tracking_each.csv")
    p3 = write_csv(summary, REPORTS / "tracking_summary.csv")
    print(f"[tracking] 簿A（首次）{len(first)} 行 → {p1}")
    print(f"[tracking] 簿B（每次）{len(each)} 行 → {p2}")
    print(f"[tracking] 摘要 {len(summary)} 行 → {p3}")
    if not each.empty:
        print(f"[tracking] 最多上榜：{each['code5'].value_counts().head(3).to_dict()}")
    for book in ("first", "each"):
        core = summary[(summary["book"] == book) & (summary["horizon"] == "t20")]
        m = {r["group"]: r["median_ret_pct"] for _, r in core.iterrows()}
        print(f"[tracking] {book} t20 中位：with_ca={m.get('with_ca')}　"
              f"without_ca={m.get('without_ca')}　all={m.get('all')}（%，只計非 _est）")
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

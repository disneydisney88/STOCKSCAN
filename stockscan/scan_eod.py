"""訊號 A：收市爆量榜（倍升RtSS 口徑，門檻全部喺 config.py）。

條件：mcap_total < MCAP_CAP_EOD　且　turnover_day > TURNOVER_MIN
　　且　turnover_day ÷ 前 MA_DAYS 個交易日成交額均值 ≥ RATIO_MIN（均值唔含今日）
輸出 data/eod/radar_eod_YYYYMMDD.csv，按市值由細到大排（照 RTSS）。

P1 起數據層行日線快取（stockscan/kline_cache.py）：
先讀 data/cache/daily/{code5}.csv → 尾支舊過 scan_date 先拉（即市K線端點，獨立配額）→ 計算。
cache_only=True 時零 API（20 日回填用）。
301607（歷史K線 100 標的配額）爆咗就用現有快取繼續計，唔好燒 retry。
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd

from config import (
    EOD_DIR,
    FIXTURE_DIR,
    LOGS_DIR,
    MA_DAYS,
    MCAP_CAP_EOD,
    RATIO_MIN,
    RTSS_FIXTURE_DATE,
    TURNOVER_MIN,
    UNIVERSE_CSV,
    WINDOW_BARS,
)
from stockscan import kline_cache
from stockscan.calendar_hk import trading_days
from stockscan.io_utils import (
    ensure_dirs,
    lb_to_code5,
    log_error,
    read_csv_if_exists,
    today_hkt,
    ts_hkt,
    write_csv,
)

OUT_COLUMNS = [
    "code5", "symbol", "name", "close", "chg_pct", "turnover_day",
    "mcap_total", "mcap_hk", "ma10", "ratio", "turnover_to_mcap",
    "ma10_days_available", "ma_short", "has_domestic_shares", "scan_time",
]


def calc_ma(turnovers: list[float], max_days: int = MA_DAYS) -> tuple[float | None, int]:
    """前 max_days 個交易日成交額均值（唔含今日——傳入 list 已唔含今日）。
    支數不足照計，回傳 (均值, 實際支數)；一支都冇回 (None, 0)。"""
    vals = [t for t in turnovers if t is not None][-max_days:]
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def calc_ratio(turnover_day: float, ma: float | None) -> float | None:
    if ma is None or ma <= 0:
        return None
    return turnover_day / ma


def resolve_scan_date(lb, date_arg: date | None) -> date:
    """日期 snapshot 到最近嘅交易日（週末／假日自動退返上一個交易日）。"""
    d = date_arg or today_hkt()
    days = trading_days(lb, d - timedelta(days=30), d)
    if not days:
        raise ValueError(f"搵唔到 {d} 之前嘅交易日")
    return days[-1]


class _QuotaAbort(Exception):
    """301607 配額爆——即刻收手。"""


def _is_quota_err(e: Exception) -> bool:
    return "301607" in str(e) or "out of limit" in str(e).lower()


def ensure_cache(lb, symbols: list[str], scan_date: date,
                 workers: int = 2, stats: dict | None = None) -> None:
    """快取尾支舊過 scan_date 嘅先拉。resumable：拉得幾多存幾多（{code5}.csv 落地）。"""
    need = []
    for sym in symbols:
        df = kline_cache.load(lb_to_code5(sym))
        if df is None or df["date"].iloc[-1] < scan_date.isoformat():
            need.append(sym)
    if stats is not None:
        stats["api_calls_planned"] = len(need)
    if not need:
        print(f"[cache] 快取全部新鮮（{len(symbols)} 隻），零 API。")
        return

    print(f"[cache] 快取過期／缺失 {len(need)}/{len(symbols)} 隻，"
          f"拉最近 {WINDOW_BARS} 支（{workers} 線程）…")

    def one(sym: str):
        try:
            bars = kline_cache.fetch_window(lb, sym, WINDOW_BARS)
            if stats is not None:
                stats["api_calls"] = stats.get("api_calls", 0) + 1
            if bars:
                kline_cache.merge_save(lb_to_code5(sym), bars)
            return sym, None
        except Exception as e:  # noqa: BLE001
            if stats is not None and ("429" in str(e) or "limit" in str(e).lower()):
                stats["throttled"] = stats.get("throttled", 0) + 1
            if _is_quota_err(e):
                return sym, _QuotaAbort(str(e))
            log_error("cache.fetch", f"{sym}: {e!r}")
            return sym, e

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, s) for s in need]
        for f in as_completed(futs):
            sym, err = f.result()
            done += 1
            if isinstance(err, _QuotaAbort):
                log_error("cache.fetch", f"{sym}: 301607 quota——暫停拉數，用現有快取頂住")
                raise err
            if done % 200 == 0:
                print(f"[cache] 進度 {done}/{len(need)}")
    print(f"[cache] 拉數完成 {done} 隻")


def build_eod(lb, date_arg: date | None = None, cache_only: bool = False,
              codes: list[str] | None = None, workers: int = 2) -> tuple[pd.DataFrame, dict]:
    stats: dict = {"api_calls": 0, "throttled": 0}
    t0 = time.perf_counter()

    uni = read_csv_if_exists(UNIVERSE_CSV)
    if uni.empty:
        raise SystemExit("data/universe.csv 唔存在——先跑 `python -m stockscan.universe`。")
    uni = uni[uni["in_scan"] == 1].copy()
    if codes:
        want = {c.zfill(5) for c in codes}
        uni = uni[uni["code5"].isin(want)]
    shares = dict(zip(uni["symbol_lb"], pd.to_numeric(uni["total_shares"], errors="coerce")))
    hk_sh = dict(zip(uni["symbol_lb"], pd.to_numeric(uni["hk_shares"], errors="coerce")))
    dom = dict(zip(uni["symbol_lb"], uni["has_domestic_shares"].fillna(0).astype(int)))
    names = dict(zip(uni["symbol_lb"], uni["name_hk"].fillna(uni["name_seed"])))

    if cache_only:
        scan_date = date_arg or today_hkt()
    else:
        scan_date = resolve_scan_date(lb, date_arg)
    print(f"[scan_eod] 掃描交易日：{scan_date}，宇宙 {len(uni)} 隻"
          f"{'（純快取模式，零 API）' if cache_only else ''}")

    if not cache_only:
        try:
            ensure_cache(lb, uni["symbol_lb"].tolist(), scan_date,
                         workers=workers, stats=stats)
        except _QuotaAbort:
            print("[scan_eod] ⚠ 配額爆——用現有快取繼續計，缺嘅統計落 no_cache。")

    rows = []
    no_cache = stale = 0
    for sym in uni["symbol_lb"]:
        df = kline_cache.load(lb_to_code5(sym))
        if df is None:
            no_cache += 1
            continue
        win = kline_cache.window_upto(df, scan_date, MA_DAYS + 1)
        if len(win) == 0 or win["date"].iloc[-1] != scan_date.isoformat():
            stale += 1  # scan 日無 bar（停牌／未上市／快取唔夠新）
            continue
        tday = win.iloc[-1]
        prevs = win.iloc[:-1]
        close = float(tday["close"])
        prev_close = float(prevs["close"].iloc[-1]) if len(prevs) else None
        turnover_day = float(tday["turnover"])
        ma, n_avail = calc_ma([float(t) for t in prevs["turnover"]])
        ratio = calc_ratio(turnover_day, ma)
        ts_total = shares.get(sym)
        if not close or not ts_total or ts_total <= 0 or ratio is None:
            continue
        chg = (close / prev_close - 1) * 100 if prev_close else None
        mcap_total = close * ts_total
        hk = hk_sh.get(sym)
        mcap_hk = close * hk if hk and hk > 0 else None
        rows.append({
            "code5": lb_to_code5(sym),
            "symbol": sym,
            "name": names.get(sym, sym),
            "close": round(close, 3),
            "chg_pct": round(chg, 2) if chg is not None else None,
            "turnover_day": round(turnover_day),
            "mcap_total": round(mcap_total),
            "mcap_hk": round(mcap_hk) if mcap_hk else "",
            "ma10": round(ma),
            "ratio": round(ratio, 2),
            "turnover_to_mcap": round(turnover_day / mcap_total * 100, 2),
            "ma10_days_available": n_avail,
            "ma_short": 1 if n_avail < MA_DAYS else 0,
            "has_domestic_shares": dom.get(sym, 0),
            "scan_time": ts_hkt(),
            "_keep": bool(mcap_total < MCAP_CAP_EOD and turnover_day > TURNOVER_MIN
                          and ratio >= RATIO_MIN),
        })

    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_keep"} for r in rows if r["_keep"]],
                      columns=OUT_COLUMNS)
    df = df.sort_values("mcap_total").reset_index(drop=True)  # 市值由細到大（照 RTSS）

    stats.update({
        "scan_date": str(scan_date),
        "universe": int(len(uni)),
        "no_cache": no_cache,
        "no_bar_on_date": stale,
        "hits": int(len(df)),
        "elapsed_s": round(time.perf_counter() - t0, 1),
    })
    _log_run_stats("scan_eod", stats)
    return df, stats


def _log_run_stats(what: str, stats: dict) -> None:
    ensure_dirs()
    p = LOGS_DIR / "run_stats.csv"
    header = not p.exists()
    with open(p, "a", encoding="utf-8") as f:
        if header:
            f.write("ts,what,scan_date,universe,api_calls,throttled,hits,elapsed_s\n")
        f.write(f"{ts_hkt()},{what},{stats.get('scan_date', '')},"
                f"{stats.get('universe', '')},{stats.get('api_calls', 0)},"
                f"{stats.get('throttled', 0)},{stats.get('hits', '')},"
                f"{stats.get('elapsed_s', '')}\n")


def compare_rtss(radar_csv, fixture_date: str = RTSS_FIXTURE_DATE) -> dict:
    """對照 tests/fixtures/rtss_YYYYMMDD.csv（RTSS 手打榜）。"""
    fx_path = FIXTURE_DIR / f"rtss_{fixture_date}.csv"
    ours = read_csv_if_exists(EOD_DIR / radar_csv.name)
    fx = pd.read_csv(fx_path, dtype=str, encoding="utf-8-sig")
    our_codes = set(ours["code5"].astype(str))
    fx_codes = set(fx["code5"].str.zfill(5))
    hits = sorted(our_codes & fx_codes)
    missing = sorted(fx_codes - our_codes)
    extra = sorted(our_codes - fx_codes)
    res = {
        "fixture": fx_path.name,
        "radar": radar_csv.name,
        "n_fixture": len(fx_codes),
        "n_ours": len(our_codes),
        "hits": hits,
        "hit_count": len(hits),
        "missing": missing,
        "extra": extra,
        "hit_rate": round(len(hits) / max(len(fx_codes), 1), 3),
    }
    out = EOD_DIR / f"compare_rtss_{fixture_date}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def run(lb, date_arg: date | None = None, cache_only: bool = False,
        codes: list[str] | None = None, workers: int = 2) -> tuple[pd.DataFrame, dict]:
    ensure_dirs()
    df, meta = build_eod(lb, date_arg, cache_only=cache_only, codes=codes, workers=workers)
    fname = f"radar_eod_{date.fromisoformat(meta['scan_date']):%Y%m%d}.csv"
    path = write_csv(df, EOD_DIR / fname)
    print(f"[scan_eod] 命中 {len(df)} 隻 → {path}"
          f"（API calls {meta.get('api_calls', 0)}，throttled {meta.get('throttled', 0)}，"
          f"耗時 {meta['elapsed_s']}s）")

    if meta["scan_date"].replace("-", "") == RTSS_FIXTURE_DATE:
        res = compare_rtss(path)
        print(f"[scan_eod] RTSS 對照：命中 {res['hit_count']}/{res['n_fixture']}")
        if res["missing"]:
            print(f"[scan_eod] 漏咗：{res['missing']}")
        if res["extra"]:
            print(f"[scan_eod] 多咗：{res['extra']}")
        meta["rtss_compare"] = res
    print("免責聲明：本工具只供學術研究及風險分析，不構成投資建議。")
    return df, meta

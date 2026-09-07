"""訊號 A：收市爆量榜（倍升RtSS 口徑，門檻全部喺 config.py）。

條件：mcap_total < MCAP_CAP_EOD　且　turnover_day > TURNOVER_MIN
　　且　turnover_day ÷ 前 MA_DAYS 個交易日成交額均值 ≥ RATIO_MIN（均值唔含今日）
輸出 data/eod/radar_eod_YYYYMMDD.csv，按市值由細到大排（照 RTSS）。
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd

from config import (
    CANDLE_WORKERS,
    EOD_DIR,
    FIXTURE_DIR,
    MA_DAYS,
    MCAP_CAP_EOD,
    RATIO_MIN,
    RTSS_FIXTURE_DATE,
    TURNOVER_MIN,
    UNIVERSE_CSV,
)
from stockscan.calendar_hk import last_trading_day, trading_days
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
    """前 max_days 個交易日成交額均值（唔含今日——呼叫方傳入嘅 list 已唔含今日）。
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


def _fetch_candles(lb, symbols: list[str], scan_date: date, is_today: bool) -> dict[str, list]:
    """逐隻攞日 K（11 支）。SDK 無批量 kline，用細線程池控制節奏，429 交 lb_client 退避。"""
    out: dict[str, list] = {}
    errors: list[str] = []

    def one(sym: str):
        try:
            if is_today:
                return sym, lb.candles_today(sym, MA_DAYS + 1)
            return sym, lb.candles_by_date(sym, scan_date, MA_DAYS + 1)
        except Exception as e:  # noqa: BLE001
            errors.append(sym)
            log_error("eod.candles", f"{sym}: {e!r}")
            return sym, None

    with ThreadPoolExecutor(max_workers=CANDLE_WORKERS) as ex:
        futs = [ex.submit(one, s) for s in symbols]
        for i, f in enumerate(as_completed(futs), 1):
            sym, rows = f.result()
            if rows:
                out[sym] = rows
            if i % 200 == 0:
                print(f"[scan_eod] 日 K 進度 {i}/{len(symbols)}，失敗 {len(errors)}")
    if errors:
        print(f"[scan_eod] 日 K 失敗共 {len(errors)} 隻（詳情 logs/）")
    return out


def build_eod(lb, date_arg: date | None = None) -> tuple[pd.DataFrame, dict]:
    uni = read_csv_if_exists(UNIVERSE_CSV)
    if uni.empty:
        raise SystemExit("data/universe.csv 唔存在——先跑 `python -m stockscan.universe`。")
    uni = uni[uni["in_scan"] == 1].copy()
    shares = dict(zip(uni["symbol_lb"], pd.to_numeric(uni["total_shares"], errors="coerce")))
    hk_sh = dict(zip(uni["symbol_lb"], pd.to_numeric(uni["hk_shares"], errors="coerce")))
    dom = dict(zip(uni["symbol_lb"], uni["has_domestic_shares"].fillna(0).astype(int)))
    names = dict(zip(uni["symbol_lb"], uni["name_hk"].fillna(uni["name_seed"])))

    scan_date = resolve_scan_date(lb, date_arg)
    is_today = scan_date == today_hkt()
    print(f"[scan_eod] 掃描交易日：{scan_date}（{'今日即市 bar' if is_today else '歷史 by_date'}），"
          f"宇宙 {len(uni)} 隻")

    candles = _fetch_candles(lb, uni["symbol_lb"].tolist(), scan_date, is_today)

    rows = []
    stale = 0
    for sym, bars in candles.items():
        if not bars:
            continue
        if bars[-1].timestamp.date() != scan_date:
            stale += 1  # 最後一支唔係 scan_date（停牌／新上市等）——照用最後一支，記數
        tday = bars[-1]
        prevs = bars[:-1]
        close = float(tday.close)
        prev_close = float(prevs[-1].close) if prevs else None
        turnover_day = float(tday.turnover)
        ma, n_avail = calc_ma([float(b.turnover) for b in prevs])
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

    meta = {
        "scan_date": str(scan_date),
        "universe": int(len(uni)),
        "with_candles": int(len(candles)),
        "stale_last_bar": stale,
        "hits": int(len(df)),
        "scan_time": ts_hkt(),
        "thresholds": {
            "mcap_cap": MCAP_CAP_EOD, "turnover_min": TURNOVER_MIN,
            "ma_days": MA_DAYS, "ratio_min": RATIO_MIN,
        },
    }
    return df, meta


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


def run(lb, date_arg: date | None = None) -> tuple[pd.DataFrame, dict]:
    ensure_dirs()
    df, meta = build_eod(lb, date_arg)
    fname = f"radar_eod_{date.fromisoformat(meta['scan_date']):%Y%m%d}.csv"
    path = write_csv(df, EOD_DIR / fname)
    print(f"[scan_eod] 命中 {len(df)} 隻 → {path}")

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

"""訊號 B：即市異動（P3 升級版）——兩種觸發，各自計「當日第 N 次」。

SURGE（急升，原訊號 B）：mcap_now < MCAP_CAP_INTRA　且　turnover_intraday ≥ INTRA_TURNOVER_MIN
　　且　chg_pct ≥ INTRA_FIRST_PCT；之後每多升 INTRA_STEP_PCT 再發（級距 floor(chg/20)×20）。
VOLUME（即市爆量，P3 新增，＝A 嘅邏輯搬上即市）：同上門檻
　　且　turnover_intraday ÷ ma10 ≥ INTRA_VOL_FIRST；每多 INTRA_VOL_STEP 倍再發。

ma10 由 P1 日線快取取（嚴格取 scan 日之前 10 個交易日，收市後先更新到當日）。
預篩：min(prev_close, last_done) × total_shares < MCAP_CAP_INTRA（一輪 quote 過晒）。
狀態檔 state/intraday_state_YYYYMMDD.json：
    {symbol: {"SURGE": {...}, "VOLUME": {...},
              "first_seen_price": x, "first_seen_turnover": y, "first_seen_ts": "..."}}
"""
from __future__ import annotations

import math
import time
from datetime import date

import pandas as pd

from config import (
    INTRA_FIRST_PCT,
    INTRA_POLL_SEC,
    INTRA_STEP_PCT,
    INTRA_TURNOVER_MIN,
    INTRA_VOL_FIRST,
    INTRA_VOL_STEP,
    LOGS_DIR,
    MA_DAYS,
    MCAP_CAP_INTRA,
    UNIVERSE_CSV,
)
from stockscan import kline_cache
from stockscan.calendar_hk import in_scan_session
from stockscan.events import action_prev_close, corporate_action_on
from stockscan.io_utils import (
    append_csv,
    ensure_dirs,
    lb_to_code5,
    load_state,
    now_hkt,
    read_csv_if_exists,
    save_state,
    ts_hkt,
)

ALERT_COLUMNS = [
    "ts", "code5", "symbol", "name", "alert_type", "count_today",
    "level_from", "level_to", "chg_pct", "last_done",
    "turnover_intraday", "mcap_now", "ratio_intraday", "off_hours",
    "corp_action_suspect",
]


def level_of(value: float, first: float, step: float) -> int:
    """級距：value ≥ first 先有級；之後每 step 一級（20→20、41→40、10x→10、25x→20）。"""
    if value < first:
        return 0
    return int(first) + int(math.floor((value - first) / step)) * int(step)


def decide_alert(rec: dict | None, value: float, first: float, step: float) -> tuple[bool, int, int]:
    """狀態機：無紀錄且 value≥first → 出；有紀錄且新級距 > 已記級距 → 出。
    回傳 (要唔要 alert, level_from, level_to)。rec 係該 alert_type 嘅舊狀態。"""
    if value < first:
        return False, 0, 0
    new_level = level_of(value, first, step)
    old_level = int(rec.get("level", 0)) if rec else 0
    if new_level > old_level:
        return True, old_level, new_level
    return False, 0, 0


def _load_universe() -> pd.DataFrame:
    uni = read_csv_if_exists(UNIVERSE_CSV)
    if uni.empty:
        raise SystemExit("data/universe.csv 唔存在——先跑 `python -m stockscan.universe`。")
    uni = uni[uni["in_scan"] == 1].copy()
    uni["total_shares"] = pd.to_numeric(uni["total_shares"], errors="coerce")
    return uni


def ma10_from_cache(code5: str, scan_date: date) -> float | None:
    """快取入面 scan_date 之前 10 個交易日成交額均值（唔含 scan 日／即市）。"""
    df = kline_cache.load(code5)
    if df is None:
        return None
    prev = df[df["date"] < scan_date.isoformat()].tail(MA_DAYS)
    if prev.empty:
        return None
    vals = [float(t) for t in prev["turnover"] if pd.notna(t)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def calc_ratio_intraday(turnover: float, ma10: float | None) -> float | None:
    """Actual intraday turnover ratio used by both SURGE and VOLUME alerts."""
    if ma10 is None or ma10 <= 0:
        return None
    return turnover / ma10


def scan_once(lb, scan_date: date | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """掃一次即市。回傳 (alerts_df, 近門檻榜 near_df, meta)。alert 追加寫 CSV＋更新狀態檔。"""
    ensure_dirs()
    t0 = time.perf_counter()
    d = scan_date or now_hkt().date()
    uni = _load_universe()
    shares = dict(zip(uni["symbol_lb"], uni["total_shares"]))
    names = dict(zip(uni["symbol_lb"], uni["name_hk"].fillna(uni["name_seed"])))
    symbols = uni["symbol_lb"].tolist()

    quotes = lb.quote_batch(symbols)
    pool: dict = {}
    for sym, q in quotes.items():
        ts_total = shares.get(sym)
        prev = float(q.prev_close or 0)
        last = float(q.last_done or 0)
        if (prev <= 0 or last <= 0 or ts_total is None
                or pd.isna(ts_total) or ts_total <= 0):
            continue  # NaN total_shares（static_missing）都擋埋
        if min(prev, last) * ts_total >= MCAP_CAP_INTRA:
            continue  # 預篩：唔會走漏任何可能合資格嘅
        pool[sym] = {
            "prev_close": prev, "last_done": last,
            "turnover": float(q.turnover or 0),
            "chg_pct": (last / prev - 1) * 100,
            "mcap_now": last * ts_total,
        }
        event = corporate_action_on(lb_to_code5(sym), d)
        p_prev, suspect = action_prev_close(prev, event)
        pool[sym]["prev_close"] = p_prev
        pool[sym]["corp_action_suspect"] = suspect
        pool[sym]["chg_pct"] = (last / p_prev - 1) * 100 if p_prev > 0 else 0.0

    state = load_state(d)
    off_hours = 0 if in_scan_session() else 1
    alerts: list[dict] = []
    for sym, p in sorted(pool.items(), key=lambda kv: -kv[1]["chg_pct"]):
        if p["corp_action_suspect"]:
            continue
        turnover = p["turnover"]
        if turnover < INTRA_TURNOVER_MIN:
            continue
        rec_all = state.get(sym, {})
        code5 = lb_to_code5(sym)
        ma10 = ma10_from_cache(code5, d)
        ratio = calc_ratio_intraday(turnover, ma10)

        # SURGE（急升）
        fire, lv_from, lv_to = decide_alert(rec_all.get("SURGE"), p["chg_pct"],
                                            INTRA_FIRST_PCT, INTRA_STEP_PCT)
        if fire:
            alerts.append(_mk_alert(sym, code5, names, "SURGE", rec_all, p,
                                    lv_from, lv_to, ratio, off_hours))
        # VOLUME（即市爆量）
        if ratio is not None:
            fire, lv_from, lv_to = decide_alert(rec_all.get("VOLUME"), ratio,
                                                INTRA_VOL_FIRST, INTRA_VOL_STEP)
            if fire:
                alerts.append(_mk_alert(sym, code5, names, "VOLUME", rec_all, p,
                                        lv_from, lv_to, ratio, off_hours))

    if alerts:
        for a in alerts:  # 更新狀態（count 遞增已喺 _mk_alert 計好）
            st = state.setdefault(a["symbol"], {})
            st[a["alert_type"]] = {
                "level": a["level_to"], "count": a["count_today"],
                "last_alert": a["ts"].split(" ")[1],
            }
            st.setdefault("first_seen_price", a["last_done"])
            st.setdefault("first_seen_turnover", a["turnover_intraday"])
            st.setdefault("first_seen_ts", a["ts"])
        save_state(d, state)
        append_csv(pd.DataFrame(alerts, columns=ALERT_COLUMNS), _alerts_path(d))

    near = pd.DataFrame([
        {"code5": lb_to_code5(s), "name": names.get(s, s),
         "chg_pct": round(p["chg_pct"], 2), "last_done": p["last_done"],
         "turnover_intraday": round(p["turnover"]), "mcap_now": round(p["mcap_now"])}
        for s, p in pool.items()
    ]).sort_values("chg_pct", ascending=False).head(20).reset_index(drop=True)

    meta = {
        "quoted": len(quotes), "pool": len(pool),
        "alerts": len(alerts), "off_hours": off_hours,
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "scan_time": ts_hkt(),
    }
    _log_intraday_stats(meta)
    return pd.DataFrame(alerts, columns=ALERT_COLUMNS), near, meta


def _mk_alert(sym, code5, names, alert_type, rec_all, p, lv_from, lv_to, ratio, off_hours):
    t = now_hkt()
    return {
        "ts": t.strftime("%Y-%m-%d %H:%M:%S"),
        "code5": code5,
        "symbol": sym,
        "name": names.get(sym, sym),
        "alert_type": alert_type,
        "count_today": int((rec_all.get(alert_type) or {}).get("count", 0)) + 1,
        "level_from": lv_from,
        "level_to": lv_to,
        "chg_pct": round(p["chg_pct"], 2),
        "last_done": p["last_done"],
        "turnover_intraday": round(p["turnover"]),
        "mcap_now": round(p["mcap_now"]),
        "ratio_intraday": round(ratio, 2) if ratio is not None else "",
        "off_hours": off_hours,
        "corp_action_suspect": 0,
    }


def _alerts_path(d: date):
    from config import INTRADAY_DIR

    return INTRADAY_DIR / f"alerts_{d:%Y%m%d}.csv"


def _log_intraday_stats(meta: dict) -> None:
    ensure_dirs()
    p = LOGS_DIR / "intraday_stats.csv"
    header = not p.exists()
    with open(p, "a", encoding="utf-8") as f:
        if header:
            f.write("ts,quoted,pool,alerts,off_hours,elapsed_s\n")
        f.write(f"{meta['scan_time']},{meta['quoted']},{meta['pool']},"
                f"{meta['alerts']},{meta['off_hours']},{meta['elapsed_s']}\n")
